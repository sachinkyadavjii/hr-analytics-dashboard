"""
attrition_model.py
-------------------
Attrition risk prediction using scikit-learn.

IMPORTANT DESIGN RULES (enforced in code, not just documented):
  - The model only trains when there is genuinely enough labeled data.
    If not, every caller gets a clear "unavailable" result instead of a
    fabricated probability.
  - Output is a PREDICTION (a correlation-based probability), never a
    statement of causation or a guaranteed outcome. Wording in the UI
    reflects that.
  - "Contributing factors" are reported as model feature importances /
    coefficients, which indicate association only.

Minimum data requirements before we will train at all:
  - >= 40 employees with usable features
  - >= 8 leavers AND >= 8 stayers (both classes meaningfully represented)
"""
from datetime import date

import numpy as np
import pandas as pd

from extensions import db
from models import Employee, Department, Attendance, LeaveRequest, PerformanceReview

MIN_ROWS = 40
MIN_PER_CLASS = 8

UNAVAILABLE_MESSAGE = (
    "Attrition prediction unavailable because the current dataset does not "
    "contain sufficient labeled data."
)

# Training takes ~1s, which is too slow to repeat on every page view (the
# employee profile needs a single employee's score). Results are cached for a
# short period and invalidated automatically when the cache expires.
_CACHE = {"key": None, "result": None, "expires_at": 0}
_CACHE_TTL_SECONDS = 300


def _cached_predict(model_name):
    import time
    now = time.time()
    if _CACHE["key"] == model_name and _CACHE["expires_at"] > now:
        return _CACHE["result"]
    result = _train_and_predict_uncached(model_name)
    _CACHE.update({"key": model_name, "result": result,
                    "expires_at": now + _CACHE_TTL_SECONDS})
    return result


def invalidate_cache():
    """Call after bulk data changes so the next request retrains."""
    _CACHE.update({"key": None, "result": None, "expires_at": 0})


def _build_feature_frame():
    """Assembles one row per employee with the features we can reliably
    derive from the production database."""
    employees = Employee.query.all()
    if not employees:
        return pd.DataFrame()

    today = pd.Timestamp(date.today())

    # Pre-aggregate attendance and leave so we don't issue N queries
    att_rows = db.session.query(Attendance.employee_id, Attendance.status).all()
    att_df = pd.DataFrame(att_rows, columns=["employee_id", "status"])
    if not att_df.empty:
        att_df["present"] = att_df["status"].isin(["Present", "Late", "Half Day"])
        att_agg = att_df.groupby("employee_id").agg(
            attendance_total=("status", "count"), attendance_present=("present", "sum"))
        att_agg["attendance_rate"] = (
            att_agg["attendance_present"] / att_agg["attendance_total"] * 100).round(1)
    else:
        att_agg = pd.DataFrame(columns=["attendance_rate"])

    leave_rows = LeaveRequest.query.filter(LeaveRequest.status == "Approved").all()
    leave_map = {}
    for l in leave_rows:
        leave_map[l.employee_id] = leave_map.get(l.employee_id, 0) + l.days

    perf_rows = db.session.query(
        PerformanceReview.employee_id, PerformanceReview.overall_rating).all()
    perf_df = pd.DataFrame(perf_rows, columns=["employee_id", "rating"])
    perf_map = perf_df.groupby("employee_id")["rating"].mean().to_dict() if not perf_df.empty else {}

    rows = []
    for e in employees:
        joining = pd.Timestamp(e.joining_date) if e.joining_date else pd.NaT
        dob = pd.Timestamp(e.date_of_birth) if e.date_of_birth else pd.NaT
        rows.append({
            "employee_id": e.id,
            "name": e.full_name,
            "employee_code": e.employee_code,
            "profile_picture": e.profile_picture,
            "department": e.department.name if e.department else "Unassigned",
            "job_title": e.job_title or "Unknown",
            "employment_type": e.employment_type or "Unknown",
            "gender": e.gender or "Unknown",
            "salary": e.salary or np.nan,
            "age": round((today - dob).days / 365.25, 1) if pd.notna(dob) else np.nan,
            "tenure_years": round((today - joining).days / 365.25, 2) if pd.notna(joining) else np.nan,
            "attendance_rate": att_agg["attendance_rate"].get(e.id, np.nan)
                                if "attendance_rate" in att_agg else np.nan,
            "leave_days": leave_map.get(e.id, 0),
            "performance": perf_map.get(e.id, np.nan),
            "status": e.status,
            "is_leaver": 1 if e.status in ("Resigned", "Terminated") else 0,
        })

    return pd.DataFrame(rows)


def check_data_sufficiency():
    """Returns (is_sufficient: bool, info: dict) without training anything."""
    df = _build_feature_frame()
    if df.empty:
        return False, {"reason": "No employee data available.", "rows": 0,
                        "leavers": 0, "stayers": 0}

    leavers = int(df["is_leaver"].sum())
    stayers = int((df["is_leaver"] == 0).sum())
    rows = len(df)

    reasons = []
    if rows < MIN_ROWS:
        reasons.append(f"only {rows} employees (need at least {MIN_ROWS})")
    if leavers < MIN_PER_CLASS:
        reasons.append(f"only {leavers} recorded leavers (need at least {MIN_PER_CLASS})")
    if stayers < MIN_PER_CLASS:
        reasons.append(f"only {stayers} current employees (need at least {MIN_PER_CLASS})")

    info = {"rows": rows, "leavers": leavers, "stayers": stayers,
            "reason": "; ".join(reasons) if reasons else None}
    return (not reasons), info


def train_and_predict(model_name="random_forest"):
    """Public entry point — returns cached results when available."""
    return _cached_predict(model_name)


def _train_and_predict_uncached(model_name="random_forest"):
    """Trains on the labeled data and scores every currently-active employee.

    Returns a dict:
      {available: bool, message: str, ...}
    When available, also includes: predictions, metrics, factors, model_name.
    """
    sufficient, info = check_data_sufficiency()
    if not sufficient:
        return {
            "available": False,
            "message": UNAVAILABLE_MESSAGE,
            "detail": info.get("reason"),
            "info": info,
        }

    # Imported lazily so the rest of the app still works if sklearn is missing
    try:
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.linear_model import LogisticRegression
        from sklearn.tree import DecisionTreeClassifier
        from sklearn.model_selection import train_test_split
        from sklearn.metrics import roc_auc_score, accuracy_score
        from sklearn.preprocessing import StandardScaler
    except ImportError:
        return {
            "available": False,
            "message": "Attrition prediction unavailable because scikit-learn is not installed.",
            "detail": "Install it with: pip install scikit-learn",
            "info": info,
        }

    df = _build_feature_frame()

    numeric_features = ["salary", "age", "tenure_years", "attendance_rate", "leave_days", "performance"]
    categorical_features = ["department", "employment_type", "gender"]

    # Keep only numeric features that actually have data
    usable_numeric = [c for c in numeric_features if df[c].notna().sum() >= len(df) * 0.5]
    if len(usable_numeric) < 2:
        return {
            "available": False,
            "message": UNAVAILABLE_MESSAGE,
            "detail": "Too few usable numeric features (salary, age, tenure, attendance, leave, performance).",
            "info": info,
        }

    work = df.copy()

    # --- LEAKAGE GUARD ---------------------------------------------------
    # If a feature is present for one class but almost entirely missing for
    # the other, the model can "cheat" by learning missingness instead of
    # real signal (e.g. if attendance is only ever recorded for current
    # employees). Such features are dropped before training.
    leaked = []
    for col in list(usable_numeric):
        present_by_class = work.groupby("is_leaver")[col].apply(lambda s: s.notna().mean())
        if len(present_by_class) == 2:
            gap = abs(present_by_class.get(0, 0) - present_by_class.get(1, 0))
            if gap > 0.5:
                leaked.append(col)
    if leaked:
        usable_numeric = [c for c in usable_numeric if c not in leaked]

    if len(usable_numeric) < 2:
        return {
            "available": False,
            "message": UNAVAILABLE_MESSAGE,
            "detail": ("After removing features that are only recorded for current employees "
                        f"({', '.join(leaked)}), too few usable features remain to train a "
                        "trustworthy model. Record attendance/performance history for past "
                        "employees to enable prediction."),
            "info": info,
        }

    for col in usable_numeric:
        work[col] = work[col].fillna(work[col].median())

    X = work[usable_numeric].copy()
    feature_names = list(usable_numeric)

    for cat in categorical_features:
        if work[cat].nunique() > 1 and work[cat].nunique() <= 20:
            dummies = pd.get_dummies(work[cat], prefix=cat, drop_first=True)
            X = pd.concat([X, dummies], axis=1)
            feature_names.extend(dummies.columns.tolist())

    y = work["is_leaver"].values
    X_values = X.values.astype(float)

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X_values)

    # Hold out a test split to report honest metrics
    try:
        X_train, X_test, y_train, y_test = train_test_split(
            X_scaled, y, test_size=0.25, random_state=42, stratify=y)
    except ValueError:
        X_train, X_test, y_train, y_test = X_scaled, X_scaled, y, y

    models = {
        "random_forest": RandomForestClassifier(n_estimators=150, max_depth=8,
                                                 random_state=42, class_weight="balanced"),
        "logistic_regression": LogisticRegression(max_iter=1000, class_weight="balanced"),
        "decision_tree": DecisionTreeClassifier(max_depth=5, random_state=42,
                                                 class_weight="balanced"),
    }
    model = models.get(model_name, models["random_forest"])
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    try:
        y_proba = model.predict_proba(X_test)[:, 1]
        auc = round(float(roc_auc_score(y_test, y_proba)), 3)
    except (ValueError, IndexError):
        auc = None
    accuracy = round(float(accuracy_score(y_test, y_pred)), 3)

    # Contributing factors (association, NOT causation)
    factors = []
    if hasattr(model, "feature_importances_"):
        importances = model.feature_importances_
        order = np.argsort(importances)[::-1][:8]
        factors = [{"feature": feature_names[i].replace("_", " ").title(),
                     "weight": round(float(importances[i]), 3)} for i in order
                    if importances[i] > 0]
    elif hasattr(model, "coef_"):
        coefs = model.coef_[0]
        order = np.argsort(np.abs(coefs))[::-1][:8]
        factors = [{"feature": feature_names[i].replace("_", " ").title(),
                     "weight": round(float(coefs[i]), 3)} for i in order]

    # Score only employees who are still here — predicting risk for someone
    # who already left would be meaningless.
    active_mask = work["status"].isin(["Active", "On Leave"]).values
    active_idx = np.where(active_mask)[0]

    predictions = []
    if len(active_idx):
        probabilities = model.predict_proba(X_scaled[active_idx])[:, 1]
        for pos, idx in enumerate(active_idx):
            prob = float(probabilities[pos])
            row = work.iloc[idx]
            predictions.append({
                "employee_id": int(row["employee_id"]),
                "name": row["name"],
                "employee_code": row["employee_code"],
                "profile_picture": row["profile_picture"],
                "department": row["department"],
                "job_title": row["job_title"],
                "risk_probability": round(prob * 100, 1),
                "risk_level": ("HIGH" if prob >= 0.65 else
                                "MEDIUM" if prob >= 0.35 else "LOW"),
                "tenure_years": None if pd.isna(row["tenure_years"]) else float(row["tenure_years"]),
                "performance": None if pd.isna(row["performance"]) else round(float(row["performance"]), 1),
                "attendance_rate": None if pd.isna(row["attendance_rate"]) else float(row["attendance_rate"]),
            })
        predictions.sort(key=lambda p: p["risk_probability"], reverse=True)

    return {
        "available": True,
        "message": None,
        "model_name": model_name,
        "predictions": predictions,
        "metrics": {
            "accuracy": accuracy,
            "roc_auc": auc,
            "training_rows": int(len(y_train)),
            "test_rows": int(len(y_test)),
            "leavers": info["leavers"],
            "stayers": info["stayers"],
            "features_used": feature_names,
            "excluded_features": leaked,
        },
        "factors": factors,
        "info": info,
    }

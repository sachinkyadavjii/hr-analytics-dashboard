"""
dataset_analytics.py
----------------------
Everything needed to turn an arbitrary, messy HR CSV/Excel upload into
validated, cleaned, analyzable data — completely isolated from the
production Employee database.

Pipeline: detect_columns() -> validate_dataset() -> clean_dataset() ->
compute_kpis() / attrition / workforce / salary / performance / attendance
analytics -> generate_insights().

Every function is defensive: messy/missing data degrades gracefully to
"Not available" rather than crashing or fabricating numbers.
"""
import re
import numpy as np
import pandas as pd
from datetime import date

# ---------------------------------------------------------------------------
# 1. COLUMN AUTO-DETECTION
# ---------------------------------------------------------------------------

COLUMN_ALIASES = {
    "employee_id": ["employee_id", "employeeid", "emp_id", "empid", "employee_code", "employee code",
                     "emp_code", "empcode", "emp code", "id"],
    "name": ["name", "full_name", "employee_name", "emp_name"],
    "department": ["department", "dept", "department_name", "team"],
    "job_title": ["job_title", "designation", "title", "role", "position"],
    "salary": ["salary", "annual_salary", "base_salary", "income", "monthly_salary", "pay", "compensation"],
    "joining_date": ["joining_date", "join_date", "date_joined", "hire_date", "doj", "date_of_joining"],
    "exit_date": ["exit_date", "resignation_date", "termination_date", "date_of_leaving", "leaving_date"],
    "status": ["status", "employee_status", "employment_status"],
    "gender": ["gender", "sex"],
    "age": ["age", "employee_age"],
    "performance": ["performance", "performance_rating", "rating", "overall_rating", "performance_score"],
    "attendance": ["attendance", "attendance_rate", "attendance_percentage", "attendance_pct"],
    "employment_type": ["employment_type", "emp_type", "job_type", "contract_type"],
    "location": ["location", "office", "city", "work_location"],
    "exit_reason": ["exit_reason", "reason_for_leaving", "leaving_reason", "reason"],
    "manager": ["manager", "manager_name", "reporting_manager", "supervisor"],
    "experience": ["experience", "experience_years", "years_experience", "tenure"],
}

REQUIRED_FOR_ANALYTICS = ["employee_id"]  # bare minimum to do anything meaningful


def _normalize(col_name):
    return re.sub(r"[^a-z0-9]", "", str(col_name).lower())


def detect_columns(columns):
    """Given the actual column names from an uploaded file, map each
    canonical field to the best-matching actual column, or None if no
    confident match is found.

    Returns: (mapping: dict[str, str|None], uncertain: list[str])
      - mapping: canonical_field -> actual column name (or None)
      - uncertain: canonical fields where more than one column looked like a
        plausible match (ambiguous — must be confirmed manually)
    """
    normalized_lookup = {_normalize(c): c for c in columns}
    mapping = {}
    uncertain = []

    for canonical, aliases in COLUMN_ALIASES.items():
        normalized_aliases = {_normalize(a) for a in aliases}
        matches = [normalized_lookup[n] for n in normalized_lookup if n in normalized_aliases]

        if len(matches) == 1:
            mapping[canonical] = matches[0]
        elif len(matches) > 1:
            mapping[canonical] = matches[0]
            uncertain.append(canonical)
        else:
            # fallback: substring match (e.g. "emp_salary_2024" contains "salary")
            substring_matches = [
                normalized_lookup[n] for n in normalized_lookup
                if any(alias in n for alias in normalized_aliases if len(alias) >= 4)
            ]
            if len(substring_matches) == 1:
                mapping[canonical] = substring_matches[0]
                uncertain.append(canonical)  # substring matches are always confirmed manually
            else:
                mapping[canonical] = None

    return mapping, uncertain


# ---------------------------------------------------------------------------
# 2. FILE LOADING
# ---------------------------------------------------------------------------

class DatasetLoadError(Exception):
    pass


def load_dataframe(filepath, file_type):
    try:
        if file_type == "csv":
            df = pd.read_csv(filepath)
        else:
            df = pd.read_excel(filepath)
    except Exception as e:
        raise DatasetLoadError(f"Could not read the file: {e}")

    if df.empty or len(df.columns) == 0:
        raise DatasetLoadError("The uploaded file has no data or no columns.")

    return df


# ---------------------------------------------------------------------------
# 3. DATA QUALITY / VALIDATION (operates on the RAW dataframe, read-only)
# ---------------------------------------------------------------------------

def validate_dataset(df, mapping):
    """Produces a data-quality report. Never modifies df."""
    report = {
        "rows": int(len(df)),
        "columns": int(len(df.columns)),
        "duplicate_rows": int(df.duplicated().sum()),
        "missing_values_total": int(df.isna().sum().sum()),
        "missing_by_column": {c: int(n) for c, n in df.isna().sum().items() if n > 0},
        "empty_columns": [c for c in df.columns if df[c].isna().all()],
        "issues": [],
    }

    emp_id_col = mapping.get("employee_id")
    if emp_id_col and emp_id_col in df.columns:
        missing_ids = int(df[emp_id_col].isna().sum())
        if missing_ids:
            report["issues"].append(f"{missing_ids} row(s) missing Employee ID.")
        dup_ids = int(df[emp_id_col].dropna().duplicated().sum())
        if dup_ids:
            report["issues"].append(f"{dup_ids} duplicate Employee ID value(s) found.")
        report["duplicate_employee_ids"] = dup_ids
    else:
        report["duplicate_employee_ids"] = None
        report["issues"].append("No Employee ID column detected — row-level identity checks skipped.")

    salary_col = mapping.get("salary")
    invalid_dates = 0
    if salary_col and salary_col in df.columns:
        numeric_salary = pd.to_numeric(df[salary_col], errors="coerce")
        negative = int((numeric_salary < 0).sum())
        zero = int((numeric_salary == 0).sum())
        non_numeric = int(numeric_salary.isna().sum() - df[salary_col].isna().sum())
        if negative:
            report["issues"].append(f"{negative} row(s) have a negative salary.")
        if non_numeric:
            report["issues"].append(f"{non_numeric} row(s) have a non-numeric salary value.")
        report["negative_salaries"] = negative
        report["zero_salaries"] = zero

    age_col = mapping.get("age")
    if age_col and age_col in df.columns:
        numeric_age = pd.to_numeric(df[age_col], errors="coerce")
        impossible = int(((numeric_age < 16) | (numeric_age > 100)).sum())
        if impossible:
            report["issues"].append(f"{impossible} row(s) have an implausible age (<16 or >100).")
        report["implausible_ages"] = impossible

    join_col, exit_col = mapping.get("joining_date"), mapping.get("exit_date")
    if join_col and exit_col and join_col in df.columns and exit_col in df.columns:
        joined = pd.to_datetime(df[join_col], errors="coerce")
        exited = pd.to_datetime(df[exit_col], errors="coerce")
        invalid_dates = int((joined.notna() & exited.notna() & (exited < joined)).sum())
        if invalid_dates:
            report["issues"].append(f"{invalid_dates} row(s) have an exit date before the joining date.")
    report["invalid_dates"] = invalid_dates

    if join_col and join_col in df.columns:
        bad_join = pd.to_datetime(df[join_col], errors="coerce").isna().sum() - df[join_col].isna().sum()
        if bad_join > 0:
            report["issues"].append(f"{int(bad_join)} row(s) have an unparseable joining date.")

    status_col = mapping.get("status")
    if status_col and status_col in df.columns:
        known_statuses = {"active", "onleave", "on leave", "inactive", "resigned", "terminated"}
        unknown = df[status_col].dropna().apply(lambda v: _normalize(v) not in {_normalize(s) for s in known_statuses})
        n_unknown = int(unknown.sum())
        if n_unknown:
            report["issues"].append(f"{n_unknown} row(s) have an unrecognized status value.")
        report["unknown_statuses"] = n_unknown

    if report["duplicate_rows"]:
        report["issues"].append(f"{report['duplicate_rows']} fully duplicate row(s) found.")
    if report["empty_columns"]:
        report["issues"].append(f"{len(report['empty_columns'])} column(s) are completely empty: "
                                 + ", ".join(report["empty_columns"]))

    report["is_analyzable"] = mapping.get("employee_id") is not None

    return report


# ---------------------------------------------------------------------------
# 4. CLEANING PIPELINE — produces a NEW analytical DataFrame.
#    The original uploaded file on disk is never touched.
# ---------------------------------------------------------------------------

def age_bucket(age):
    if pd.isna(age):
        return "Unknown"
    if age < 25: return "18-24"
    if age < 30: return "25-29"
    if age < 35: return "30-34"
    if age < 45: return "35-44"
    if age < 55: return "45-54"
    return "55+"


def tenure_bucket(years):
    if pd.isna(years):
        return "Unknown"
    if years < 1: return "<1 yr"
    if years < 2: return "1-2 yrs"
    if years < 5: return "2-5 yrs"
    return "5+ yrs"


def salary_band(salary):
    if pd.isna(salary):
        return "Unknown"
    if salary < 30000: return "<30k"
    if salary < 50000: return "30k-50k"
    if salary < 80000: return "50k-80k"
    return "80k+"


LEAVER_STATUSES = {"resigned", "terminated"}

# Department/type names that are acronyms and should stay uppercase rather
# than being mangled by .title() (e.g. "IT" -> "It").
KNOWN_ACRONYMS = {"IT", "HR", "QA", "RD", "R&D", "BD", "PR", "IS", "MIS", "SEO", "UX", "UI"}


def _smart_title(value):
    """Title-cases a label but keeps known acronyms uppercase."""
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if not stripped:
        return np.nan
    if stripped.upper() in KNOWN_ACRONYMS:
        return stripped.upper()
    # Title-case each word, but keep any word that is a known acronym upper
    words = []
    for word in stripped.split():
        words.append(word.upper() if word.upper() in KNOWN_ACRONYMS else word.capitalize())
    return " ".join(words)


def clean_dataset(df, mapping):
    """Returns (cleaned_df, cleaning_log: list[str]).
    cleaned_df uses CANONICAL column names (employee_id, department, salary,
    etc.) so downstream analytics functions don't need to know the original
    messy header names."""
    log = []
    clean = pd.DataFrame(index=df.index)

    # Normalize column names note (informational — we work off `mapping`,
    # which was already computed against normalized names)
    log.append("Normalized column headers for matching (case/spacing-insensitive).")

    for canonical, actual_col in mapping.items():
        if actual_col is None or actual_col not in df.columns:
            continue
        series = df[actual_col]
        if series.dtype == object:
            series = series.astype(str).str.strip()
            series = series.replace({"nan": np.nan, "None": np.nan, "": np.nan})
        clean[canonical] = series

    if "employee_id" in clean:
        before = len(clean)
        clean = clean.drop_duplicates(subset=["employee_id"], keep="first")
        removed = before - len(clean)
        if removed:
            log.append(f"Removed {removed} duplicate row(s) by Employee ID (kept first occurrence).")

    if "salary" in clean:
        numeric = pd.to_numeric(clean["salary"], errors="coerce")
        bad = int(numeric.isna().sum() - clean["salary"].isna().sum())
        if bad:
            log.append(f"{bad} salary value(s) could not be parsed as numbers and were set to missing.")
        clean["salary"] = numeric
        neg = int((clean["salary"] < 0).sum())
        if neg:
            clean.loc[clean["salary"] < 0, "salary"] = np.nan
            log.append(f"{neg} negative salary value(s) treated as invalid and set to missing.")

    if "age" in clean:
        numeric = pd.to_numeric(clean["age"], errors="coerce")
        clean["age"] = numeric
        implausible = (clean["age"] < 16) | (clean["age"] > 100)
        n_impl = int(implausible.sum())
        if n_impl:
            clean.loc[implausible, "age"] = np.nan
            log.append(f"{n_impl} implausible age value(s) (outside 16-100) set to missing.")
        clean["age_group"] = clean["age"].apply(age_bucket)

    for date_field in ["joining_date", "exit_date"]:
        if date_field in clean:
            parsed = pd.to_datetime(clean[date_field], errors="coerce")
            bad = int(parsed.isna().sum() - clean[date_field].isna().sum())
            if bad:
                log.append(f"{bad} unparseable value(s) in {date_field.replace('_', ' ')} set to missing.")
            clean[date_field] = parsed

    if "joining_date" in clean:
        today = pd.Timestamp(date.today())
        clean["tenure_years"] = ((today - clean["joining_date"]).dt.days / 365.25).round(2)
        clean["tenure_group"] = clean["tenure_years"].apply(tenure_bucket)

    if "salary" in clean:
        clean["salary_band"] = clean["salary"].apply(salary_band)

    if "status" in clean:
        clean["status_normalized"] = clean["status"].apply(
            lambda v: v.strip().title() if isinstance(v, str) else v)
        clean["is_leaver"] = clean["status_normalized"].apply(
            lambda v: isinstance(v, str) and v.lower() in LEAVER_STATUSES)
        log.append("Standardized status values to title case and derived is_leaver flag.")
    elif "exit_date" in clean:
        clean["is_leaver"] = clean["exit_date"].notna()
        log.append("No status column found — derived is_leaver from presence of an exit date.")

    if "department" in clean:
        clean["department"] = clean["department"].apply(_smart_title)
    if "gender" in clean:
        clean["gender"] = clean["gender"].astype(str).str.strip().str.title().replace(
            {"M": "Male", "F": "Female"})
    if "employment_type" in clean:
        clean["employment_type"] = clean["employment_type"].apply(_smart_title)

    if "performance" in clean:
        clean["performance"] = pd.to_numeric(clean["performance"], errors="coerce")
    if "attendance" in clean:
        clean["attendance"] = pd.to_numeric(clean["attendance"], errors="coerce")

    log.append(f"Final cleaned dataset: {len(clean)} rows, {len(clean.columns)} columns "
               f"(including derived fields).")

    return clean, log


# ---------------------------------------------------------------------------
# 5. KPIs & ANALYTICS — every metric checks column availability first.
# ---------------------------------------------------------------------------

NA = "Not available — required column not found."


def compute_kpis(clean):
    kpis = {}
    kpis["total_employees"] = len(clean) if "employee_id" in clean else NA

    if "status_normalized" in clean or "is_leaver" in clean:
        if "status_normalized" in clean:
            kpis["active_employees"] = int((clean["status_normalized"].str.lower() == "active").sum())
        else:
            kpis["active_employees"] = NA
        kpis["leavers"] = int(clean["is_leaver"].sum()) if "is_leaver" in clean else NA
        if "is_leaver" in clean and len(clean):
            kpis["attrition_rate"] = round(clean["is_leaver"].sum() / len(clean) * 100, 1)
        else:
            kpis["attrition_rate"] = NA
    else:
        kpis["active_employees"] = NA
        kpis["leavers"] = NA
        kpis["attrition_rate"] = NA

    if "salary" in clean and clean["salary"].notna().any():
        kpis["average_salary"] = round(float(clean["salary"].mean()), 0)
        kpis["median_salary"] = round(float(clean["salary"].median()), 0)
        kpis["min_salary"] = round(float(clean["salary"].min()), 0)
        kpis["max_salary"] = round(float(clean["salary"].max()), 0)
    else:
        kpis["average_salary"] = kpis["median_salary"] = kpis["min_salary"] = kpis["max_salary"] = NA

    if "attendance" in clean and clean["attendance"].notna().any():
        kpis["attendance_rate"] = round(float(clean["attendance"].mean()), 1)
    else:
        kpis["attendance_rate"] = NA

    if "performance" in clean and clean["performance"].notna().any():
        kpis["average_performance"] = round(float(clean["performance"].mean()), 2)
    else:
        kpis["average_performance"] = NA

    if "joining_date" in clean:
        thirty_days_ago = pd.Timestamp(date.today()) - pd.Timedelta(days=30)
        kpis["new_hires"] = int((clean["joining_date"] >= thirty_days_ago).sum())
    else:
        kpis["new_hires"] = NA

    return kpis


def _labels_data(series):
    return {"labels": series.index.astype(str).tolist(), "data": [float(v) for v in series.values]}


def attrition_breakdown(clean):
    if "is_leaver" not in clean:
        return None
    results = {}
    dims = {
        "by_department": "department", "by_gender": "gender", "by_age": "age_group",
        "by_experience": "tenure_group", "by_salary": "salary_band",
        "by_employment_type": "employment_type", "by_location": "location",
    }
    for key, col in dims.items():
        if col in clean:
            grouped = clean.groupby(col).agg(total=("is_leaver", "count"), leavers=("is_leaver", "sum"))
            grouped = grouped[grouped["total"] > 0]
            grouped["rate"] = (grouped["leavers"] / grouped["total"] * 100).round(1)
            results[key] = {"labels": grouped.index.astype(str).tolist(), "data": grouped["rate"].tolist()}
        else:
            results[key] = None

    if "exit_reason" in clean:
        counts = clean.loc[clean["is_leaver"], "exit_reason"].dropna().value_counts()
        results["exit_reasons"] = _labels_data(counts) if not counts.empty else None
    else:
        results["exit_reasons"] = None

    return results


def workforce_breakdown(clean):
    out = {}
    if "department" in clean:
        out["headcount_by_department"] = _labels_data(clean["department"].value_counts())
    if "location" in clean:
        out["headcount_by_location"] = _labels_data(clean["location"].value_counts())
    if "gender" in clean:
        out["gender_distribution"] = _labels_data(clean["gender"].value_counts())
    if "age_group" in clean:
        order = ["18-24", "25-29", "30-34", "35-44", "45-54", "55+"]
        counts = clean["age_group"].value_counts().reindex(order).dropna()
        out["age_distribution"] = _labels_data(counts)
    if "employment_type" in clean:
        out["employment_type_distribution"] = _labels_data(clean["employment_type"].value_counts())
    if "status_normalized" in clean:
        out["status_distribution"] = _labels_data(clean["status_normalized"].value_counts())
    if "joining_date" in clean:
        monthly = clean.groupby(clean["joining_date"].dt.to_period("M")).size().sort_index().tail(12)
        out["hiring_trend"] = {"labels": [str(p) for p in monthly.index], "data": monthly.values.tolist()}
    return out


def salary_breakdown(clean):
    if "salary" not in clean or not clean["salary"].notna().any():
        return None
    out = {}
    if "department" in clean:
        avg = clean.groupby("department")["salary"].mean().round(0).sort_values(ascending=False)
        out["by_department"] = _labels_data(avg)
    if "job_title" in clean:
        avg = clean.groupby("job_title")["salary"].mean().round(0).sort_values(ascending=False).head(10)
        out["by_job_title"] = _labels_data(avg)
    if "experience" in clean:
        exp_numeric = pd.to_numeric(clean["experience"], errors="coerce")
        valid = exp_numeric.notna() & clean["salary"].notna()
        if valid.sum() >= 3:
            out["by_experience_scatter"] = {
                "points": [{"x": float(x), "y": float(y)} for x, y in
                           zip(exp_numeric[valid], clean["salary"][valid])]
            }
    out["salary_bands"] = _labels_data(clean["salary_band"].value_counts()) if "salary_band" in clean else None
    return out


def performance_breakdown(clean):
    if "performance" not in clean or not clean["performance"].notna().any():
        return None
    out = {}
    valid = clean["performance"].dropna()
    bins = pd.cut(valid, bins=[0, 1, 2, 3, 4, 5], labels=["1", "2", "3", "4", "5"])
    out["distribution"] = _labels_data(bins.value_counts().sort_index())
    if "department" in clean:
        avg = clean.groupby("department")["performance"].mean().round(2).sort_values(ascending=False)
        out["by_department"] = _labels_data(avg)
    if "job_title" in clean:
        avg = clean.groupby("job_title")["performance"].mean().round(2).sort_values(ascending=False).head(10)
        out["by_job_title"] = _labels_data(avg)
    if "is_leaver" in clean:
        avg = clean.groupby("is_leaver")["performance"].mean().round(2)
        out["vs_attrition"] = {"labels": ["Stayed", "Left"],
                                "data": [float(avg.get(False, 0)), float(avg.get(True, 0))]}
    if "salary" in clean:
        valid2 = clean["performance"].notna() & clean["salary"].notna()
        if valid2.sum() >= 3:
            out["vs_salary_scatter"] = {
                "points": [{"x": float(p), "y": float(s)} for p, s in
                           zip(clean["performance"][valid2], clean["salary"][valid2])]
            }
    return out


def attendance_breakdown(clean):
    if "attendance" not in clean or not clean["attendance"].notna().any():
        return None
    out = {"overall_rate": round(float(clean["attendance"].mean()), 1)}
    if "department" in clean:
        avg = clean.groupby("department")["attendance"].mean().round(1).sort_values(ascending=False)
        out["by_department"] = _labels_data(avg)
    if "is_leaver" in clean:
        avg = clean.groupby("is_leaver")["attendance"].mean().round(1)
        out["vs_attrition"] = {"labels": ["Stayed", "Left"],
                                "data": [float(avg.get(False, 0)), float(avg.get(True, 0))]}
    return out


# ---------------------------------------------------------------------------
# 6. AUTOMATIC BUSINESS INSIGHTS — only from data actually present.
# ---------------------------------------------------------------------------

def generate_insights(clean):
    insights = []
    if clean.empty:
        return ["No usable rows in this dataset yet."]

    if "is_leaver" in clean and "department" in clean:
        grouped = clean.groupby("department").agg(total=("is_leaver", "count"), leavers=("is_leaver", "sum"))
        grouped = grouped[grouped["total"] >= 3]
        if not grouped.empty:
            grouped["rate"] = grouped["leavers"] / grouped["total"] * 100
            top = grouped["rate"].idxmax()
            if grouped["rate"].max() > 0:
                insights.append(f"{top} has the highest attrition rate at {grouped['rate'].max():.1f}%.")

    if "salary" in clean and "department" in clean and clean["salary"].notna().any():
        avg = clean.groupby("department")["salary"].mean().dropna()
        if not avg.empty:
            insights.append(f"{avg.idxmax()} has the highest average salary at \u20b9{avg.max():,.0f}.")

    if "is_leaver" in clean and "tenure_group" in clean:
        grouped = clean.groupby("tenure_group").agg(total=("is_leaver", "count"), leavers=("is_leaver", "sum"))
        overall_rate = clean["is_leaver"].sum() / len(clean) * 100
        if "<1 yr" in grouped.index and grouped.loc["<1 yr", "total"] > 0:
            new_rate = grouped.loc["<1 yr", "leavers"] / grouped.loc["<1 yr", "total"] * 100
            if new_rate > overall_rate:
                insights.append(
                    f"Employees with less than one year of tenure have higher attrition ({new_rate:.1f}%) "
                    f"than the company average ({overall_rate:.1f}%)."
                )

    if "attendance" in clean and clean["attendance"].notna().any():
        avg_att = clean["attendance"].mean()
        if avg_att < 85:
            insights.append(f"Overall attendance rate is {avg_att:.1f}%, below the healthy 85% benchmark.")

    if "gender" in clean:
        counts = clean["gender"].value_counts(normalize=True) * 100
        if not counts.empty:
            insights.append(f"{counts.idxmax()} employees make up {counts.max():.0f}% of this dataset.")

    if "performance" in clean and "is_leaver" in clean and clean["performance"].notna().any():
        avg = clean.groupby("is_leaver")["performance"].mean()
        if True in avg.index and False in avg.index and avg[True] < avg[False]:
            insights.append("Employees who left tend to have lower average performance scores than those who stayed.")

    if not insights:
        insights.append("Not enough structured data was found to generate reliable insights. "
                         "Try uploading a dataset with department, salary, and status columns.")

    return insights

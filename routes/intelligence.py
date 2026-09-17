from flask import Blueprint, render_template, request
from auth_utils import login_required, permission_required
from models import Department
import hr_intelligence as hi
import attrition_model as am
import hr_assistant as ha

intelligence_bp = Blueprint("intelligence", __name__, url_prefix="/hr-intelligence")


@intelligence_bp.route("/alerts")
@permission_required("view_analytics")
def alerts():
    # Thresholds are configurable from the UI via query params so HR can
    # tune sensitivity without code changes.
    overrides = {}
    for key in hi.DEFAULT_THRESHOLDS:
        raw = request.args.get(key)
        if raw not in (None, ""):
            try:
                overrides[key] = float(raw)
            except ValueError:
                pass

    thresholds = dict(hi.DEFAULT_THRESHOLDS)
    thresholds.update(overrides)

    alert_list = hi.generate_alerts(thresholds)
    warnings = [a for a in alert_list if a["level"] == "warning"]
    infos = [a for a in alert_list if a["level"] != "warning"]

    return render_template("intelligence/alerts.html", alerts=alert_list,
                            warnings=warnings, infos=infos, thresholds=thresholds)


@intelligence_bp.route("/top-performers")
@login_required
def top_performers():
    # Managers can see rankings for their team context; HR/Admin see everything.
    department = request.args.get("department", "")
    months = request.args.get("months", "")
    limit = request.args.get("limit", 10, type=int)

    performers = hi.top_performers(
        department=department or None,
        limit=min(limit, 50),
        months=int(months) if months else None,
    )
    departments = Department.query.order_by(Department.name).all()

    return render_template("intelligence/top_performers.html", performers=performers,
                            departments=departments,
                            filters={"department": department, "months": months, "limit": limit})


@intelligence_bp.route("/attrition-risk")
@permission_required("view_analytics")
def attrition_risk():
    model_name = request.args.get("model", "random_forest")
    if model_name not in ("random_forest", "logistic_regression", "decision_tree"):
        model_name = "random_forest"

    result = am.train_and_predict(model_name)

    level_filter = request.args.get("level", "")
    predictions = result.get("predictions", []) or []
    if level_filter:
        predictions = [p for p in predictions if p["risk_level"] == level_filter]

    counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for p in (result.get("predictions") or []):
        counts[p["risk_level"]] = counts.get(p["risk_level"], 0) + 1

    return render_template("intelligence/attrition_risk.html", result=result,
                            predictions=predictions[:100], counts=counts,
                            model_name=model_name, level_filter=level_filter)


@intelligence_bp.route("/assistant", methods=["GET", "POST"])
@login_required
def assistant():
    from flask import session
    question = ""
    response = None
    if request.method == "POST":
        question = request.form.get("question", "")
        response = ha.ask(question, session.get("role"))

    return render_template("intelligence/assistant.html", question=question,
                            response=response, suggestions=ha.SUGGESTED_QUESTIONS,
                            llm_configured=ha.llm_configured())

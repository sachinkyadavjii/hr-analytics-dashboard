from datetime import datetime
from flask import Blueprint, render_template, request
from extensions import db
from auth_utils import permission_required
from models import Department, Employee
import analytics_engine as ae

analytics_bp = Blueprint("analytics", __name__, url_prefix="/analytics")


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


@analytics_bp.route("/")
@permission_required("view_analytics")
def index():
    department = request.args.get("department", "")
    location = request.args.get("location", "")
    employment_type = request.args.get("employment_type", "")
    gender = request.args.get("gender", "")
    start_date = _parse_date(request.args.get("start_date"))
    end_date = _parse_date(request.args.get("end_date"))

    df = ae.employees_dataframe(department=department or None, location=location or None,
                                 employment_type=employment_type or None, gender=gender or None,
                                 start_date=start_date, end_date=end_date)

    kpis = ae.kpi_summary(df)
    if not df.empty:
        kpis["average_tenure"] = round(df["tenure_years"].mean(), 1)
    else:
        kpis["average_tenure"] = 0.0

    charts = {
        "headcount_by_department": ae.headcount_by_department(df),
        "growth": ae.employee_growth(df),
        "attrition_by_department": ae.attrition_by(df, "department") if not df.empty else {"labels": [], "data": []},
        "attrition_by_experience": ae.attrition_by(df.assign(tenure_group=df["tenure_years"].apply(ae.tenure_bucket)) if not df.empty else df, "tenure_group") if not df.empty else {"labels": [], "data": []},
        "salary_by_department": ae.salary_by_department(df),
        "gender": ae.gender_distribution(df),
        "age": ae.age_distribution(df),
        "performance_distribution": ae.performance_distribution(),
        "attendance_trend": ae.attendance_trend(),
        "hiring_trend": ae.hiring_trend(df),
    }

    insights = ae.generate_insights(df)

    departments = Department.query.order_by(Department.name).all()
    locations = [r[0] for r in db.session.query(Employee.location).distinct() if r[0]]

    return render_template(
        "analytics/index.html", kpis=kpis, charts=charts, insights=insights,
        departments=departments, locations=locations,
        filters={"department": department, "location": location, "employment_type": employment_type,
                 "gender": gender, "start_date": request.args.get("start_date", ""),
                 "end_date": request.args.get("end_date", "")},
    )


@analytics_bp.route("/attrition")
@permission_required("view_analytics")
def attrition():
    df = ae.employees_dataframe()
    breakdown = ae.attrition_breakdown(df)
    reasons = ae.exit_reasons(df)
    kpis = ae.kpi_summary(df)
    return render_template("analytics/attrition.html", breakdown=breakdown, reasons=reasons, kpis=kpis)

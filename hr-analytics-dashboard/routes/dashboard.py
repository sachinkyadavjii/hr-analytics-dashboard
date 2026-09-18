from flask import Blueprint, render_template
from auth_utils import login_required
from models import Employee, Department, LeaveRequest
import analytics_engine as ae

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/dashboard")
@login_required
def index():
    df = ae.employees_dataframe()
    kpis = ae.kpi_summary(df)

    charts = {
        "growth": ae.employee_growth(df),
        "departments": ae.headcount_by_department(df),
        "gender": ae.gender_distribution(df),
        "status": ae.status_distribution(df),
        "hiring": ae.hiring_trend(df),
        "attrition": ae.attrition_trend(df),
    }

    recent_employees = Employee.query.order_by(Employee.joining_date.desc()).limit(6).all()
    upcoming_leave = LeaveRequest.query.filter(LeaveRequest.status == "Pending") \
        .order_by(LeaveRequest.start_date.asc()).limit(6).all()

    return render_template(
        "dashboard.html",
        kpis=kpis,
        charts=charts,
        recent_employees=recent_employees,
        upcoming_leave=upcoming_leave,
    )

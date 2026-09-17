from flask import Blueprint, render_template, request, redirect, url_for, flash
from extensions import db
from auth_utils import permission_required
from models import CompanySettings, Department, User

settings_bp = Blueprint("settings", __name__, url_prefix="/settings")


@settings_bp.route("/")
@permission_required("manage_settings")
def index():
    settings = CompanySettings.get()
    departments = Department.query.order_by(Department.name).all()
    users = User.query.order_by(User.name).all()
    return render_template("settings/index.html", settings=settings, departments=departments, users=users)


@settings_bp.route("/company", methods=["POST"])
@permission_required("manage_settings")
def update_company():
    settings = CompanySettings.get()
    form = request.form
    settings.company_name = form.get("company_name", settings.company_name)
    settings.company_email = form.get("company_email", settings.company_email)
    settings.company_phone = form.get("company_phone", settings.company_phone)
    settings.company_address = form.get("company_address", settings.company_address)
    settings.working_days = form.get("working_days", settings.working_days)
    db.session.commit()
    flash("Company settings updated.", "success")
    return redirect(url_for("settings.index"))


@settings_bp.route("/leave-policy", methods=["POST"])
@permission_required("manage_settings")
def update_leave_policy():
    settings = CompanySettings.get()
    form = request.form
    settings.casual_leave_days = form.get("casual_leave_days", type=int) or settings.casual_leave_days
    settings.sick_leave_days = form.get("sick_leave_days", type=int) or settings.sick_leave_days
    settings.earned_leave_days = form.get("earned_leave_days", type=int) or settings.earned_leave_days
    settings.emergency_leave_days = form.get("emergency_leave_days", type=int) or settings.emergency_leave_days
    db.session.commit()
    flash("Leave policy updated.", "success")
    return redirect(url_for("settings.index"))

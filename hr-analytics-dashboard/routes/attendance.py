from datetime import datetime, date, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash
from extensions import db
from auth_utils import login_required, permission_required
from models import Attendance, Employee
import analytics_engine as ae

attendance_bp = Blueprint("attendance", __name__, url_prefix="/attendance")


@attendance_bp.route("/")
@login_required
def list_attendance():
    selected_date = request.args.get("date") or date.today().isoformat()
    try:
        day = datetime.strptime(selected_date, "%Y-%m-%d").date()
    except ValueError:
        day = date.today()

    records = Attendance.query.filter_by(date=day).join(Employee).order_by(Employee.first_name).all()
    marked_ids = {r.employee_id for r in records}
    unmarked = Employee.query.filter(Employee.status == "Active", ~Employee.id.in_(marked_ids)).all() \
        if marked_ids else Employee.query.filter(Employee.status == "Active").all()

    total = len(records)
    present = sum(1 for r in records if r.status in ("Present", "Late", "Half Day"))
    absent = sum(1 for r in records if r.status == "Absent")
    late = sum(1 for r in records if r.status == "Late")
    on_leave = sum(1 for r in records if r.status == "Leave")
    rate = round(present / total * 100, 1) if total else 0

    charts = {
        "monthly": ae.attendance_trend(),
        "department": ae.department_attendance(),
    }

    return render_template(
        "attendance/list.html",
        records=records, unmarked=unmarked, selected_date=day,
        stats={"total": total, "present": present, "absent": absent, "late": late,
               "on_leave": on_leave, "rate": rate},
        charts=charts,
    )


@attendance_bp.route("/mark", methods=["POST"])
@permission_required("manage_attendance")
def mark_attendance():
    employee_id = request.form.get("employee_id", type=int)
    day_str = request.form.get("date")
    status = request.form.get("status", "Present")
    check_in = request.form.get("check_in") or None
    check_out = request.form.get("check_out") or None

    try:
        day = datetime.strptime(day_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        day = date.today()

    existing = Attendance.query.filter_by(employee_id=employee_id, date=day).first()
    if existing:
        existing.status = status
        existing.check_in = check_in
        existing.check_out = check_out
    else:
        db.session.add(Attendance(employee_id=employee_id, date=day, status=status,
                                   check_in=check_in, check_out=check_out))
    db.session.commit()
    flash("Attendance recorded.", "success")
    return redirect(url_for("attendance.list_attendance", date=day.isoformat()))

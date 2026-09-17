from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from extensions import db
from auth_utils import login_required, permission_required
from models import LeaveRequest, Employee, Notification

leave_bp = Blueprint("leave", __name__, url_prefix="/leave")

LEAVE_TYPES = ["Casual Leave", "Sick Leave", "Earned Leave", "Emergency Leave"]


@leave_bp.route("/")
@login_required
def list_leave():
    status = request.args.get("status", "")
    query = LeaveRequest.query.join(Employee)
    if status:
        query = query.filter(LeaveRequest.status == status)
    requests_ = query.order_by(LeaveRequest.applied_on.desc()).all()
    employees = Employee.query.filter(Employee.status != "Inactive").order_by(Employee.first_name).all()
    return render_template("leave/list.html", requests=requests_, employees=employees,
                            leave_types=LEAVE_TYPES, status_filter=status)


@leave_bp.route("/apply", methods=["POST"])
@login_required
def apply_leave():
    employee_id = request.form.get("employee_id", type=int)
    leave_type = request.form.get("leave_type")
    start_date = datetime.strptime(request.form.get("start_date"), "%Y-%m-%d").date()
    end_date = datetime.strptime(request.form.get("end_date"), "%Y-%m-%d").date()
    reason = request.form.get("reason", "")

    if end_date < start_date:
        flash("End date cannot be before start date.", "danger")
        return redirect(url_for("leave.list_leave"))

    leave_req = LeaveRequest(employee_id=employee_id, leave_type=leave_type,
                              start_date=start_date, end_date=end_date, reason=reason, status="Pending")
    db.session.add(leave_req)

    employee = Employee.query.get(employee_id)
    if employee:
        db.session.add(Notification(
            message=f"New leave request from {employee.full_name} ({leave_type})", category="leave"))

    db.session.commit()
    flash("Leave request submitted.", "success")
    return redirect(url_for("leave.list_leave"))


@leave_bp.route("/<int:leave_id>/approve", methods=["POST"])
@permission_required("approve_leave")
def approve_leave(leave_id):
    leave_req = LeaveRequest.query.get_or_404(leave_id)
    leave_req.status = "Approved"
    leave_req.decided_by = session.get("name")
    db.session.add(Notification(
        message=f"Leave approved for {leave_req.employee.full_name} ({leave_req.leave_type})", category="leave"))
    db.session.commit()
    flash("Leave request approved.", "success")
    return redirect(url_for("leave.list_leave"))


@leave_bp.route("/<int:leave_id>/reject", methods=["POST"])
@permission_required("approve_leave")
def reject_leave(leave_id):
    leave_req = LeaveRequest.query.get_or_404(leave_id)
    leave_req.status = "Rejected"
    leave_req.decided_by = session.get("name")
    db.session.add(Notification(
        message=f"Leave rejected for {leave_req.employee.full_name} ({leave_req.leave_type})", category="leave"))
    db.session.commit()
    flash("Leave request rejected.", "info")
    return redirect(url_for("leave.list_leave"))

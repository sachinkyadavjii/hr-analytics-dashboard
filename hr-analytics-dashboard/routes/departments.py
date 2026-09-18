from flask import Blueprint, render_template, request, redirect, url_for, flash
from extensions import db
from auth_utils import permission_required, login_required
from models import Department, Employee

departments_bp = Blueprint("departments", __name__, url_prefix="/departments")


@departments_bp.route("/")
@login_required
def list_departments():
    departments = Department.query.order_by(Department.name).all()
    rows = []
    for dept in departments:
        emp_count = dept.employees.filter(Employee.status != "Inactive").count()
        active_emps = dept.employees.all()
        avg_salary = round(sum(e.salary or 0 for e in active_emps) / emp_count, 0) if emp_count else 0
        leavers = dept.employees.filter(Employee.status.in_(["Resigned", "Terminated"])).count()
        total_ever = dept.employees.count()
        attrition = round(leavers / total_ever * 100, 1) if total_ever else 0
        rows.append({
            "department": dept, "employee_count": emp_count,
            "avg_salary": avg_salary, "attrition_rate": attrition,
        })
    return render_template("departments/list.html", rows=rows)


@departments_bp.route("/add", methods=["POST"])
@permission_required("manage_departments")
def add_department():
    name = request.form.get("name", "").strip()
    manager_name = request.form.get("manager_name", "").strip()
    if not name:
        flash("Department name is required.", "danger")
    elif Department.query.filter_by(name=name).first():
        flash("A department with that name already exists.", "danger")
    else:
        db.session.add(Department(name=name, manager_name=manager_name, status="Active"))
        db.session.commit()
        flash(f"Department '{name}' added.", "success")
    return redirect(url_for("departments.list_departments"))


@departments_bp.route("/<int:dept_id>/edit", methods=["POST"])
@permission_required("manage_departments")
def edit_department(dept_id):
    dept = Department.query.get_or_404(dept_id)
    dept.name = request.form.get("name", dept.name).strip()
    dept.manager_name = request.form.get("manager_name", dept.manager_name)
    db.session.commit()
    flash(f"Department '{dept.name}' updated.", "success")
    return redirect(url_for("departments.list_departments"))


@departments_bp.route("/<int:dept_id>/deactivate", methods=["POST"])
@permission_required("manage_departments")
def deactivate_department(dept_id):
    dept = Department.query.get_or_404(dept_id)
    dept.status = "Inactive" if dept.status == "Active" else "Active"
    db.session.commit()
    flash(f"Department '{dept.name}' status set to {dept.status}.", "info")
    return redirect(url_for("departments.list_departments"))

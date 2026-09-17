from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash
from extensions import db
from auth_utils import login_required, permission_required
from models import SalaryRecord, Employee
import analytics_engine as ae

payroll_bp = Blueprint("payroll", __name__, url_prefix="/payroll")


@payroll_bp.route("/")
@login_required
def list_payroll():
    df = ae.employees_dataframe()
    records = SalaryRecord.query.join(Employee).order_by(SalaryRecord.effective_date.desc()).limit(100).all()
    employees = Employee.query.filter(Employee.status != "Inactive").order_by(Employee.first_name).all()

    stats = {}
    if not df.empty:
        stats = {
            "average": round(df["salary"].mean(), 0),
            "highest": round(df["salary"].max(), 0),
            "lowest": round(df["salary"].min(), 0),
        }

    charts = {
        "by_department": ae.salary_by_department(df),
        "by_designation": ae.salary_by_designation(df),
    }

    return render_template("payroll/list.html", records=records, employees=employees,
                            stats=stats, charts=charts)


@payroll_bp.route("/add", methods=["POST"])
@permission_required("manage_payroll")
def add_salary_record():
    form = request.form
    employee_id = form.get("employee_id", type=int)
    base_salary = float(form.get("base_salary") or 0)
    bonus = float(form.get("bonus") or 0)
    deduction = float(form.get("deduction") or 0)
    effective_date = datetime.strptime(form.get("effective_date"), "%Y-%m-%d").date()

    record = SalaryRecord(employee_id=employee_id, base_salary=base_salary,
                           bonus=bonus, deduction=deduction, effective_date=effective_date)
    db.session.add(record)

    employee = Employee.query.get(employee_id)
    if employee:
        employee.salary = base_salary

    db.session.commit()
    flash("Salary record added.", "success")
    return redirect(url_for("payroll.list_payroll"))

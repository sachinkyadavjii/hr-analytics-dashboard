import io
from datetime import datetime
from flask import Blueprint, render_template, send_file, request
import pandas as pd
from extensions import db
from auth_utils import permission_required
from models import Employee, Attendance, LeaveRequest, PerformanceReview, SalaryRecord, Department

reports_bp = Blueprint("reports", __name__, url_prefix="/reports")

REPORT_TYPES = {
    "employee": "Employee Report",
    "attendance": "Attendance Report",
    "leave": "Leave Report",
    "performance": "Performance Report",
    "salary": "Salary Report",
    "attrition": "Attrition Report",
}


def _build_dataframe(report_type):
    if report_type == "employee":
        rows = []
        for e in Employee.query.all():
            rows.append({
                "Employee ID": e.employee_code, "Name": e.full_name, "Email": e.email,
                "Department": e.department.name if e.department else "", "Designation": e.job_title,
                "Joining Date": e.joining_date, "Employment Type": e.employment_type,
                "Status": e.status, "Salary": e.salary,
            })
        return pd.DataFrame(rows)

    if report_type == "attendance":
        rows = []
        for a in Attendance.query.join(Employee).all():
            rows.append({
                "Employee": a.employee.full_name, "Date": a.date, "Status": a.status,
                "Check In": a.check_in, "Check Out": a.check_out,
            })
        return pd.DataFrame(rows)

    if report_type == "leave":
        rows = []
        for l in LeaveRequest.query.join(Employee).all():
            rows.append({
                "Employee": l.employee.full_name, "Type": l.leave_type, "Start Date": l.start_date,
                "End Date": l.end_date, "Days": l.days, "Status": l.status, "Reason": l.reason,
            })
        return pd.DataFrame(rows)

    if report_type == "performance":
        rows = []
        for r in PerformanceReview.query.join(Employee).all():
            rows.append({
                "Employee": r.employee.full_name, "Review Date": r.review_date, "Reviewer": r.reviewer,
                "Overall Rating": r.overall_rating, "Technical": r.technical_skills,
                "Communication": r.communication, "Teamwork": r.teamwork,
                "Leadership": r.leadership, "Problem Solving": r.problem_solving,
            })
        return pd.DataFrame(rows)

    if report_type == "salary":
        rows = []
        for s in SalaryRecord.query.join(Employee).all():
            rows.append({
                "Employee": s.employee.full_name, "Base Salary": s.base_salary, "Bonus": s.bonus,
                "Deduction": s.deduction, "Net Salary": s.net_salary, "Effective Date": s.effective_date,
            })
        return pd.DataFrame(rows)

    if report_type == "attrition":
        rows = []
        for e in Employee.query.filter(Employee.status.in_(["Resigned", "Terminated"])).all():
            rows.append({
                "Employee ID": e.employee_code, "Name": e.full_name,
                "Department": e.department.name if e.department else "",
                "Joining Date": e.joining_date, "Exit Date": e.exit_date,
                "Exit Reason": e.exit_reason, "Status": e.status,
            })
        return pd.DataFrame(rows)

    return pd.DataFrame()


@reports_bp.route("/")
@permission_required("view_reports")
def index():
    return render_template("reports/index.html", report_types=REPORT_TYPES)


@reports_bp.route("/export/<report_type>/<fmt>")
@permission_required("view_reports")
def export_report(report_type, fmt):
    if report_type not in REPORT_TYPES:
        return "Unknown report type", 404

    df = _build_dataframe(report_type)
    filename_base = f"{report_type}_report_{datetime.utcnow().strftime('%Y%m%d')}"

    if fmt == "csv":
        buffer = io.StringIO()
        df.to_csv(buffer, index=False)
        mem = io.BytesIO(buffer.getvalue().encode("utf-8"))
        return send_file(mem, mimetype="text/csv", as_attachment=True,
                          download_name=f"{filename_base}.csv")

    if fmt == "excel":
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name=REPORT_TYPES[report_type][:30])
        buffer.seek(0)
        return send_file(buffer,
                          mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                          as_attachment=True, download_name=f"{filename_base}.xlsx")

    return "Unsupported format", 400

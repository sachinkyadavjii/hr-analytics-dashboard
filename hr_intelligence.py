"""
hr_intelligence.py
-------------------
Higher-level HR intelligence computed from the MAIN production database:
  - salary benchmarking (employee vs department vs job-title averages)
  - Smart HR Alerts (threshold-based conditions detected from real data)
  - performance ranking / top performers

All thresholds are configurable via the `thresholds` argument so HR can tune
them without code changes. Every function returns only what the data
supports — no fabricated numbers.
"""
from datetime import date, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import func, case

from extensions import db
from models import Employee, Department, Attendance, LeaveRequest, PerformanceReview

DEFAULT_THRESHOLDS = {
    "high_attrition_pct": 15.0,      # department attrition above this triggers an alert
    "low_attendance_pct": 80.0,      # individual attendance below this is flagged
    "low_performance_rating": 2.5,   # rating below this is flagged
    "high_leave_days": 20,           # approved leave days in last 12 months
    "probation_days": 180,           # probation period length
    "probation_window_days": 30,     # alert when completion is within this window
    "salary_outlier_z": 2.5,         # |z-score| beyond this within a job title
}


# ---------------------------------------------------------------------------
# SALARY BENCHMARKING
# ---------------------------------------------------------------------------

def benchmark_salary(employee):
    """Compares one employee's salary against their department average and
    job-title average. Returns None if there's no salary to compare."""
    if not employee.salary:
        return None

    result = {"employee_salary": employee.salary, "department": None, "job_title": None}

    if employee.department_id:
        dept_avg = db.session.query(func.avg(Employee.salary)).filter(
            Employee.department_id == employee.department_id,
            Employee.salary > 0,
            Employee.status.notin_(["Resigned", "Terminated"]),
        ).scalar()
        if dept_avg:
            diff_pct = (employee.salary - dept_avg) / dept_avg * 100
            result["department"] = {
                "label": employee.department.name if employee.department else "Department",
                "average": round(float(dept_avg), 0),
                "difference_pct": round(diff_pct, 1),
                "position": _position_label(diff_pct),
            }

    if employee.job_title:
        title_avg = db.session.query(func.avg(Employee.salary)).filter(
            Employee.job_title == employee.job_title,
            Employee.salary > 0,
            Employee.status.notin_(["Resigned", "Terminated"]),
        ).scalar()
        title_count = db.session.query(func.count(Employee.id)).filter(
            Employee.job_title == employee.job_title,
            Employee.salary > 0,
            Employee.status.notin_(["Resigned", "Terminated"]),
        ).scalar()
        # Only meaningful if there are peers to compare against
        if title_avg and title_count and title_count >= 2:
            diff_pct = (employee.salary - title_avg) / title_avg * 100
            result["job_title"] = {
                "label": employee.job_title,
                "average": round(float(title_avg), 0),
                "difference_pct": round(diff_pct, 1),
                "position": _position_label(diff_pct),
                "peer_count": int(title_count),
            }

    if not result["department"] and not result["job_title"]:
        return None
    return result


def _position_label(diff_pct):
    """Neutral business language, no judgemental phrasing."""
    if diff_pct < -5:
        return "Below average"
    if diff_pct > 5:
        return "Above average"
    return "Around average"


# ---------------------------------------------------------------------------
# EMPLOYEE ATTENDANCE / LEAVE SUMMARIES (used by alerts + 360 view)
# ---------------------------------------------------------------------------

def employee_attendance_rate(employee_id, days=90):
    cutoff = date.today() - timedelta(days=days)
    rows = db.session.query(Attendance.status).filter(
        Attendance.employee_id == employee_id, Attendance.date >= cutoff).all()
    if not rows:
        return None
    statuses = [r[0] for r in rows]
    present = sum(1 for s in statuses if s in ("Present", "Late", "Half Day"))
    return round(present / len(statuses) * 100, 1)


def employee_leave_days(employee_id, days=365):
    cutoff = date.today() - timedelta(days=days)
    requests = LeaveRequest.query.filter(
        LeaveRequest.employee_id == employee_id,
        LeaveRequest.status == "Approved",
        LeaveRequest.start_date >= cutoff,
    ).all()
    return sum(r.days for r in requests)


# ---------------------------------------------------------------------------
# SMART HR ALERTS
# ---------------------------------------------------------------------------

def generate_alerts(thresholds=None):
    """Returns a list of alert dicts:
    {level: 'warning'|'info', category: str, message: str, detail: str}

    Every alert is derived from an actual query — if the supporting data
    isn't there, the alert simply isn't produced.
    """
    t = dict(DEFAULT_THRESHOLDS)
    if thresholds:
        t.update({k: v for k, v in thresholds.items() if v is not None})

    alerts = []

    # 1. High-attrition departments
    for dept in Department.query.all():
        total = dept.employees.count()
        if total < 5:
            continue  # too small to be statistically meaningful
        leavers = dept.employees.filter(Employee.status.in_(["Resigned", "Terminated"])).count()
        rate = leavers / total * 100
        if rate >= t["high_attrition_pct"]:
            alerts.append({
                "level": "warning", "category": "Attrition",
                "message": f"{dept.name} attrition is {rate:.1f}%, above the {t['high_attrition_pct']}% threshold.",
                "detail": f"{leavers} of {total} employees in {dept.name} have left.",
            })

    # 2. Employees with attendance below threshold
    cutoff = date.today() - timedelta(days=90)
    att_rows = db.session.query(
        Attendance.employee_id,
        func.count(Attendance.id).label("total"),
        func.sum(case((Attendance.status.in_(["Present", "Late", "Half Day"]), 1), else_=0)).label("present"),
    ).filter(Attendance.date >= cutoff).group_by(Attendance.employee_id).all()

    low_attendance = []
    for emp_id, total, present in att_rows:
        if total and total >= 10:
            rate = (present or 0) / total * 100
            if rate < t["low_attendance_pct"]:
                low_attendance.append((emp_id, round(rate, 1)))
    if low_attendance:
        alerts.append({
            "level": "warning", "category": "Attendance",
            "message": f"{len(low_attendance)} employee(s) have attendance below {t['low_attendance_pct']}%.",
            "detail": "Based on the last 90 days of recorded attendance.",
        })

    # 3. Low performance ratings (latest review per employee)
    latest_reviews = {}
    for review in PerformanceReview.query.order_by(PerformanceReview.review_date.asc()).all():
        latest_reviews[review.employee_id] = review
    low_perf = [r for r in latest_reviews.values() if r.overall_rating < t["low_performance_rating"]]
    if low_perf:
        alerts.append({
            "level": "warning", "category": "Performance",
            "message": f"{len(low_perf)} employee(s) have a latest performance rating below {t['low_performance_rating']}.",
            "detail": "Consider scheduling development conversations.",
        })

    # 4. High leave usage
    high_leave_count = 0
    active_ids = [e.id for e in Employee.query.filter(Employee.status == "Active").all()]
    for emp_id in active_ids:
        if employee_leave_days(emp_id) > t["high_leave_days"]:
            high_leave_count += 1
    if high_leave_count:
        alerts.append({
            "level": "info", "category": "Leave",
            "message": f"{high_leave_count} employee(s) have used more than {t['high_leave_days']} approved leave days in the last year.",
            "detail": "Review against your leave policy entitlements.",
        })

    # 5. Upcoming probation completions
    today = date.today()
    window_start = today - timedelta(days=t["probation_days"])
    window_end = window_start + timedelta(days=t["probation_window_days"])
    upcoming = Employee.query.filter(
        Employee.status == "Active",
        Employee.joining_date <= window_end,
        Employee.joining_date >= window_start,
    ).all()
    if upcoming:
        alerts.append({
            "level": "info", "category": "Probation",
            "message": f"{len(upcoming)} employee(s) are completing probation within the next {t['probation_window_days']} days.",
            "detail": ", ".join(e.full_name for e in upcoming[:5]) + ("..." if len(upcoming) > 5 else ""),
        })

    # 6. Salary anomalies within a job title (z-score based)
    rows = db.session.query(Employee.id, Employee.first_name, Employee.last_name,
                             Employee.job_title, Employee.salary).filter(
        Employee.salary > 0, Employee.status.notin_(["Resigned", "Terminated"])).all()
    if rows:
        df = pd.DataFrame(rows, columns=["id", "first", "last", "job_title", "salary"])
        anomalies = []
        for title, group in df.groupby("job_title"):
            if len(group) < 4:
                continue
            std = group["salary"].std()
            if not std or std == 0:
                continue
            z = (group["salary"] - group["salary"].mean()) / std
            outliers = group[abs(z) > t["salary_outlier_z"]]
            for _, row in outliers.iterrows():
                anomalies.append(f"{row['first']} {row['last']} ({title})")
        if anomalies:
            alerts.append({
                "level": "info", "category": "Salary",
                "message": f"{len(anomalies)} salary outlier(s) detected within job titles.",
                "detail": "Statistical outliers only (z-score based) — may be justified by seniority or performance. "
                          + ", ".join(anomalies[:4]) + ("..." if len(anomalies) > 4 else ""),
            })

    if not alerts:
        alerts.append({
            "level": "info", "category": "General",
            "message": "No HR alerts triggered with the current thresholds.",
            "detail": "All monitored metrics are within their configured limits.",
        })

    return alerts


# ---------------------------------------------------------------------------
# PERFORMANCE RANKING / TOP PERFORMERS
# ---------------------------------------------------------------------------

def top_performers(department=None, limit=10, months=None):
    """Ranks employees by their average performance rating.
    Optionally filtered to a department and/or a recent time window."""
    query = db.session.query(
        Employee.id, Employee.first_name, Employee.last_name, Employee.job_title,
        Employee.profile_picture, Department.name.label("department"),
        func.avg(PerformanceReview.overall_rating).label("avg_rating"),
        func.count(PerformanceReview.id).label("review_count"),
    ).join(PerformanceReview, PerformanceReview.employee_id == Employee.id) \
     .outerjoin(Department, Employee.department_id == Department.id) \
     .filter(Employee.status.notin_(["Resigned", "Terminated"]))

    if department:
        query = query.filter(Department.name == department)
    if months:
        cutoff = date.today() - timedelta(days=int(months) * 30)
        query = query.filter(PerformanceReview.review_date >= cutoff)

    query = query.group_by(Employee.id).order_by(func.avg(PerformanceReview.overall_rating).desc())

    results = []
    for rank, row in enumerate(query.limit(limit).all(), start=1):
        results.append({
            "rank": rank,
            "employee_id": row.id,
            "name": f"{row.first_name} {row.last_name}",
            "initials": (row.first_name[0] + (row.last_name[0] if row.last_name else "")).upper(),
            "profile_picture": row.profile_picture,
            "job_title": row.job_title,
            "department": row.department or "Unassigned",
            "avg_rating": round(float(row.avg_rating), 2),
            "review_count": int(row.review_count),
        })
    return results

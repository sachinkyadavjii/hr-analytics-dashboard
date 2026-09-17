"""
analytics_engine.py
--------------------
All Pandas-based analysis lives here, kept separate from Flask routes so
it's easy to test, reuse, and reason about independently of the web layer.

Every function takes plain data (lists of dicts / DataFrames) or does its
own lightweight querying, and returns either a DataFrame or a plain dict
that templates / JSON responses can consume directly.
"""
from datetime import date, datetime
import numpy as np
import pandas as pd

from extensions import db
from models import Employee, Attendance, LeaveRequest, PerformanceReview, SalaryRecord, Department


def employees_dataframe(department=None, location=None, employment_type=None, gender=None,
                         start_date=None, end_date=None):
    """Pull employees into a DataFrame, optionally filtered. Used by both
    the dashboard and the Analytics page filters."""
    query = Employee.query
    if department:
        query = query.join(Department).filter(Department.name == department)
    if location:
        query = query.filter(Employee.location == location)
    if employment_type:
        query = query.filter(Employee.employment_type == employment_type)
    if gender:
        query = query.filter(Employee.gender == gender)
    if start_date:
        query = query.filter(Employee.joining_date >= start_date)
    if end_date:
        query = query.filter(Employee.joining_date <= end_date)

    rows = []
    for e in query.all():
        rows.append({
            "id": e.id,
            "employee_code": e.employee_code,
            "full_name": e.full_name,
            "department": e.department.name if e.department else "Unassigned",
            "job_title": e.job_title,
            "gender": e.gender,
            "date_of_birth": e.date_of_birth,
            "joining_date": e.joining_date,
            "employment_type": e.employment_type,
            "location": e.location,
            "status": e.status,
            "salary": e.salary or 0,
            "experience_years": e.experience_years or 0,
            "exit_date": e.exit_date,
            "exit_reason": e.exit_reason,
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df

    today = pd.Timestamp(date.today())
    df["joining_date"] = pd.to_datetime(df["joining_date"])
    df["date_of_birth"] = pd.to_datetime(df["date_of_birth"])
    df["age"] = ((today - df["date_of_birth"]).dt.days / 365.25).round(1)
    df["tenure_years"] = ((today - df["joining_date"]).dt.days / 365.25).round(2)
    df["is_leaver"] = df["status"].isin(["Resigned", "Terminated"])
    return df


def age_bucket(age):
    if pd.isna(age):
        return "Unknown"
    if age < 25:
        return "18-24"
    if age < 30:
        return "25-29"
    if age < 35:
        return "30-34"
    if age < 45:
        return "35-44"
    if age < 55:
        return "45-54"
    return "55+"


def tenure_bucket(years):
    if pd.isna(years):
        return "Unknown"
    if years < 1:
        return "<1 yr"
    if years < 2:
        return "1-2 yrs"
    if years < 5:
        return "2-5 yrs"
    return "5+ yrs"


def salary_bucket(salary):
    if pd.isna(salary):
        return "Unknown"
    if salary < 30000:
        return "<30k"
    if salary < 50000:
        return "30k-50k"
    if salary < 80000:
        return "50k-80k"
    return "80k+"


def kpi_summary(df=None):
    """Top-line KPI cards for the dashboard. Computed live from the DB,
    never hardcoded."""
    if df is None:
        df = employees_dataframe()
    if df.empty:
        return {
            "total_employees": 0, "active_employees": 0, "on_leave": 0, "new_hires": 0,
            "attrition_rate": 0.0, "average_salary": 0.0, "attendance_rate": 0.0,
            "average_performance": 0.0,
        }

    total = len(df)
    active = int((df["status"] == "Active").sum())
    on_leave = int((df["status"] == "On Leave").sum())

    thirty_days_ago = pd.Timestamp(date.today()) - pd.Timedelta(days=30)
    new_hires = int((df["joining_date"] >= thirty_days_ago).sum())

    leavers = int(df["is_leaver"].sum())
    avg_headcount = max(total, 1)
    attrition_rate = round((leavers / avg_headcount) * 100, 1)

    average_salary = round(df["salary"].mean(), 0) if total else 0

    attendance_rate = attendance_rate_overall()
    average_performance = average_performance_overall()

    return {
        "total_employees": total,
        "active_employees": active,
        "on_leave": on_leave,
        "new_hires": new_hires,
        "attrition_rate": attrition_rate,
        "average_salary": average_salary,
        "attendance_rate": attendance_rate,
        "average_performance": average_performance,
    }


def attendance_rate_overall(days=90):
    cutoff = date.today() - pd.Timedelta(days=days)
    rows = db.session.query(Attendance.status).filter(Attendance.date >= cutoff).all()
    if not rows:
        return 0.0
    statuses = [r[0] for r in rows]
    present_like = sum(1 for s in statuses if s in ("Present", "Late", "Half Day"))
    return round((present_like / len(statuses)) * 100, 1)


def average_performance_overall():
    ratings = [r[0] for r in db.session.query(PerformanceReview.overall_rating).all()]
    if not ratings:
        return 0.0
    return round(float(np.mean(ratings)), 1)


def headcount_by_department(df=None):
    df = df if df is not None else employees_dataframe()
    if df.empty:
        return {"labels": [], "data": []}
    counts = df.groupby("department").size().sort_values(ascending=False)
    return {"labels": counts.index.tolist(), "data": counts.values.tolist()}


def gender_distribution(df=None):
    df = df if df is not None else employees_dataframe()
    if df.empty:
        return {"labels": [], "data": []}
    counts = df["gender"].fillna("Other").value_counts()
    return {"labels": counts.index.tolist(), "data": counts.values.tolist()}


def status_distribution(df=None):
    df = df if df is not None else employees_dataframe()
    if df.empty:
        return {"labels": [], "data": []}
    counts = df["status"].value_counts()
    return {"labels": counts.index.tolist(), "data": counts.values.tolist()}


def age_distribution(df=None):
    df = df if df is not None else employees_dataframe()
    if df.empty:
        return {"labels": [], "data": []}
    buckets = df["age"].apply(age_bucket)
    order = ["18-24", "25-29", "30-34", "35-44", "45-54", "55+"]
    counts = buckets.value_counts().reindex(order).fillna(0).astype(int)
    return {"labels": counts.index.tolist(), "data": counts.values.tolist()}


def employee_growth(df=None):
    """Cumulative headcount by month based on joining dates (last 12 months)."""
    df = df if df is not None else employees_dataframe()
    if df.empty:
        return {"labels": [], "data": []}
    monthly = df.groupby(df["joining_date"].dt.to_period("M")).size().sort_index()
    last_12 = monthly.tail(12)
    cumulative_base = monthly[:monthly.index.get_loc(last_12.index[0])].sum() if len(monthly) > len(last_12) else 0
    running = cumulative_base
    labels, values = [], []
    for period, count in last_12.items():
        running += count
        labels.append(period.strftime("%b %Y"))
        values.append(int(running))
    return {"labels": labels, "data": values}


def hiring_trend(df=None):
    df = df if df is not None else employees_dataframe()
    if df.empty:
        return {"labels": [], "data": []}
    monthly = df.groupby(df["joining_date"].dt.to_period("M")).size().sort_index().tail(12)
    return {"labels": [p.strftime("%b %Y") for p in monthly.index], "data": monthly.values.tolist()}


def attrition_trend(df=None):
    df = df if df is not None else employees_dataframe()
    if df.empty or "exit_date" not in df:
        return {"labels": [], "data": []}
    leavers = df[df["is_leaver"] & df["exit_date"].notna()].copy()
    if leavers.empty:
        return {"labels": [], "data": []}
    leavers["exit_date"] = pd.to_datetime(leavers["exit_date"])
    monthly = leavers.groupby(leavers["exit_date"].dt.to_period("M")).size().sort_index().tail(12)
    return {"labels": [p.strftime("%b %Y") for p in monthly.index], "data": monthly.values.tolist()}


def attrition_by(df, column):
    """Generic 'attrition rate by X' calculator. Returns rate% per group."""
    if df.empty:
        return {"labels": [], "data": []}
    grouped = df.groupby(column).agg(total=("id", "count"), leavers=("is_leaver", "sum"))
    grouped["rate"] = (grouped["leavers"] / grouped["total"] * 100).round(1)
    grouped = grouped.sort_values("rate", ascending=False)
    return {"labels": grouped.index.tolist(), "data": grouped["rate"].tolist()}


def attrition_breakdown(df=None):
    df = df if df is not None else employees_dataframe()
    if df.empty:
        empty = {"labels": [], "data": []}
        return {k: empty for k in ["by_department", "by_gender", "by_age", "by_experience",
                                    "by_salary", "by_employment_type"]}
    d = df.copy()
    d["age_group"] = d["age"].apply(age_bucket)
    d["tenure_group"] = d["tenure_years"].apply(tenure_bucket)
    d["salary_range"] = d["salary"].apply(salary_bucket)

    return {
        "by_department": attrition_by(d, "department"),
        "by_gender": attrition_by(d, "gender"),
        "by_age": attrition_by(d, "age_group"),
        "by_experience": attrition_by(d, "tenure_group"),
        "by_salary": attrition_by(d, "salary_range"),
        "by_employment_type": attrition_by(d, "employment_type"),
    }


def exit_reasons(df=None):
    df = df if df is not None else employees_dataframe()
    if df.empty:
        return {"labels": [], "data": []}
    leavers = df[df["is_leaver"] & df["exit_reason"].notna()]
    if leavers.empty:
        return {"labels": [], "data": []}
    counts = leavers["exit_reason"].value_counts()
    return {"labels": counts.index.tolist(), "data": counts.values.tolist()}


def salary_by_department(df=None):
    df = df if df is not None else employees_dataframe()
    if df.empty:
        return {"labels": [], "data": []}
    avg = df.groupby("department")["salary"].mean().round(0).sort_values(ascending=False)
    return {"labels": avg.index.tolist(), "data": avg.values.tolist()}


def salary_by_designation(df=None):
    df = df if df is not None else employees_dataframe()
    if df.empty:
        return {"labels": [], "data": []}
    avg = df.groupby("job_title")["salary"].mean().round(0).sort_values(ascending=False).head(10)
    return {"labels": avg.index.tolist(), "data": avg.values.tolist()}


def performance_distribution():
    ratings = [r[0] for r in db.session.query(PerformanceReview.overall_rating).all()]
    if not ratings:
        return {"labels": [], "data": []}
    s = pd.Series(ratings)
    bins = pd.cut(s, bins=[0, 1, 2, 3, 4, 5], labels=["1", "2", "3", "4", "5"])
    counts = bins.value_counts().sort_index()
    return {"labels": counts.index.astype(str).tolist(), "data": counts.values.tolist()}


def department_performance():
    rows = db.session.query(PerformanceReview.overall_rating, Employee.department_id, Department.name).join(
        Employee, PerformanceReview.employee_id == Employee.id
    ).join(Department, Employee.department_id == Department.id).all()
    if not rows:
        return {"labels": [], "data": []}
    df = pd.DataFrame(rows, columns=["rating", "dept_id", "department"])
    avg = df.groupby("department")["rating"].mean().round(2).sort_values(ascending=False)
    return {"labels": avg.index.tolist(), "data": avg.values.tolist()}


def attendance_trend(days=180):
    cutoff = date.today() - pd.Timedelta(days=days)
    rows = db.session.query(Attendance.date, Attendance.status).filter(Attendance.date >= cutoff).all()
    if not rows:
        return {"labels": [], "data": []}
    df = pd.DataFrame(rows, columns=["date", "status"])
    df["date"] = pd.to_datetime(df["date"])
    df["present"] = df["status"].isin(["Present", "Late", "Half Day"])
    monthly = df.groupby(df["date"].dt.to_period("M")).agg(total=("status", "count"), present=("present", "sum"))
    monthly["rate"] = (monthly["present"] / monthly["total"] * 100).round(1)
    monthly = monthly.sort_index().tail(12)
    return {"labels": [p.strftime("%b %Y") for p in monthly.index], "data": monthly["rate"].tolist()}


def department_attendance():
    rows = db.session.query(Attendance.status, Employee.department_id, Department.name).join(
        Employee, Attendance.employee_id == Employee.id
    ).join(Department, Employee.department_id == Department.id).all()
    if not rows:
        return {"labels": [], "data": []}
    df = pd.DataFrame(rows, columns=["status", "dept_id", "department"])
    df["present"] = df["status"].isin(["Present", "Late", "Half Day"])
    grouped = df.groupby("department").agg(total=("status", "count"), present=("present", "sum"))
    grouped["rate"] = (grouped["present"] / grouped["total"] * 100).round(1)
    return {"labels": grouped.index.tolist(), "data": grouped["rate"].tolist()}


def generate_insights(df=None):
    """Auto-generated, data-driven business insights for the Analytics page.
    Every sentence here is produced from a live calculation — nothing is
    hardcoded text."""
    df = df if df is not None else employees_dataframe()
    insights = []
    if df.empty:
        return ["No employee data available yet — add employees to see insights."]

    d = df.copy()
    d["age_group"] = d["age"].apply(age_bucket)
    d["tenure_group"] = d["tenure_years"].apply(tenure_bucket)

    # Highest attrition department
    dept_attr = d.groupby("department").agg(total=("id", "count"), leavers=("is_leaver", "sum"))
    dept_attr = dept_attr[dept_attr["total"] >= 3]
    if not dept_attr.empty:
        dept_attr["rate"] = dept_attr["leavers"] / dept_attr["total"] * 100
        top_dept = dept_attr["rate"].idxmax()
        top_rate = dept_attr["rate"].max()
        if top_rate > 0:
            insights.append(f"{top_dept} has the highest attrition rate at {top_rate:.1f}%.")

    # Highest average salary department
    dept_salary = d.groupby("department")["salary"].mean()
    if not dept_salary.empty:
        top_salary_dept = dept_salary.idxmax()
        insights.append(f"{top_salary_dept} has the highest average salary at \u20b9{dept_salary.max():,.0f}.")

    # Tenure vs attrition
    tenure_attr = d.groupby("tenure_group").agg(total=("id", "count"), leavers=("is_leaver", "sum"))
    if "<1 yr" in tenure_attr.index and tenure_attr.loc["<1 yr", "total"] > 0:
        rate_new = tenure_attr.loc["<1 yr", "leavers"] / tenure_attr.loc["<1 yr", "total"] * 100
        overall_rate = d["is_leaver"].sum() / len(d) * 100
        if rate_new > overall_rate:
            insights.append(
                f"Employees with less than 1 year tenure show higher attrition ({rate_new:.1f}%) "
                f"than the company average ({overall_rate:.1f}%)."
            )

    # Attendance trend (this month vs previous month)
    trend = attendance_trend()
    if len(trend["data"]) >= 2:
        latest, prev = trend["data"][-1], trend["data"][-2]
        if latest < prev:
            insights.append(f"Attendance rate decreased this month to {latest:.1f}% (from {prev:.1f}%).")
        elif latest > prev:
            insights.append(f"Attendance rate improved this month to {latest:.1f}% (from {prev:.1f}%).")

    # Gender balance
    gender_counts = d["gender"].value_counts(normalize=True) * 100
    if not gender_counts.empty:
        top_gender = gender_counts.idxmax()
        insights.append(f"{top_gender} employees make up {gender_counts.max():.0f}% of the workforce.")

    # Salary vs attrition
    salary_attr = d.groupby(d["salary"].apply(salary_bucket)).agg(total=("id", "count"), leavers=("is_leaver", "sum"))
    salary_attr = salary_attr[salary_attr["total"] >= 3]
    if not salary_attr.empty:
        salary_attr["rate"] = salary_attr["leavers"] / salary_attr["total"] * 100
        worst_bracket = salary_attr["rate"].idxmax()
        if salary_attr["rate"].max() > 0:
            insights.append(f"The '{worst_bracket}' salary bracket shows the highest attrition among salary ranges.")

    return insights or ["No significant patterns detected in the current dataset."]

from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from extensions import db
from auth_utils import login_required, permission_required
from models import PerformanceReview, Employee, Notification
import analytics_engine as ae

performance_bp = Blueprint("performance", __name__, url_prefix="/performance")


@performance_bp.route("/")
@login_required
def list_performance():
    q = request.args.get("q", "").strip()
    department = request.args.get("department", "")

    query = PerformanceReview.query.join(Employee)
    if q:
        like = f"%{q}%"
        query = query.filter(Employee.first_name.ilike(like) | Employee.last_name.ilike(like))

    reviews = query.order_by(PerformanceReview.review_date.desc()).limit(100).all()
    employees = Employee.query.filter(Employee.status != "Inactive").order_by(Employee.first_name).all()

    charts = {
        "distribution": ae.performance_distribution(),
        "department": ae.department_performance(),
    }
    avg_rating = ae.average_performance_overall()

    return render_template("performance/list.html", reviews=reviews, employees=employees,
                            charts=charts, avg_rating=avg_rating, q=q)


@performance_bp.route("/add", methods=["POST"])
@permission_required("manage_performance")
def add_review():
    form = request.form
    employee_id = form.get("employee_id", type=int)

    ratings = [form.get(f, type=int) for f in
               ["technical_skills", "communication", "teamwork", "leadership", "problem_solving"]]
    ratings = [r for r in ratings if r is not None]
    overall = round(sum(ratings) / len(ratings), 1) if ratings else form.get("overall_rating", type=float, default=3.0)

    review = PerformanceReview(
        employee_id=employee_id,
        review_date=datetime.utcnow().date(),
        reviewer=session.get("name"),
        overall_rating=overall,
        technical_skills=form.get("technical_skills", type=int),
        communication=form.get("communication", type=int),
        teamwork=form.get("teamwork", type=int),
        leadership=form.get("leadership", type=int),
        problem_solving=form.get("problem_solving", type=int),
        goals=form.get("goals"),
        comments=form.get("comments"),
    )
    db.session.add(review)

    employee = Employee.query.get(employee_id)
    if employee:
        db.session.add(Notification(
            message=f"Performance review completed for {employee.full_name}", category="performance"))

    db.session.commit()
    flash("Performance review saved.", "success")
    return redirect(url_for("performance.list_performance"))

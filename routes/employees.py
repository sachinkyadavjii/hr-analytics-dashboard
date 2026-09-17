import os
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from sqlalchemy import or_
from extensions import db
from auth_utils import login_required, permission_required
from models import Employee, Department, Attendance, LeaveRequest, PerformanceReview, SalaryRecord, Notification
from file_upload_utils import (is_allowed_image, file_size_ok, MAX_IMAGE_SIZE_BYTES,
                                safe_unique_filename, resolve_upload_path, delete_file_if_exists,
                                PROFILE_PICS_SUBDIR)

employees_bp = Blueprint("employees", __name__, url_prefix="/employees")


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


@employees_bp.route("/")
@login_required
def list_employees():
    q = request.args.get("q", "").strip()
    department = request.args.get("department", "")
    status = request.args.get("status", "")
    employment_type = request.args.get("employment_type", "")
    location = request.args.get("location", "")
    page = request.args.get("page", 1, type=int)

    query = Employee.query
    if q:
        like = f"%{q}%"
        query = query.filter(or_(
            Employee.first_name.ilike(like),
            Employee.last_name.ilike(like),
            Employee.employee_code.ilike(like),
            Employee.email.ilike(like),
            Employee.job_title.ilike(like),
        ))
    if department:
        query = query.join(Department).filter(Department.name == department)
    if status:
        query = query.filter(Employee.status == status)
    if employment_type:
        query = query.filter(Employee.employment_type == employment_type)
    if location:
        query = query.filter(Employee.location == location)

    query = query.order_by(Employee.created_at.desc())
    per_page = current_app.config.get("EMPLOYEES_PER_PAGE", 15)
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    departments = Department.query.order_by(Department.name).all()
    locations = [r[0] for r in db.session.query(Employee.location).distinct() if r[0]]

    return render_template(
        "employees/list.html",
        employees=pagination.items,
        pagination=pagination,
        departments=departments,
        locations=locations,
        filters={"q": q, "department": department, "status": status,
                 "employment_type": employment_type, "location": location},
    )


@employees_bp.route("/add", methods=["GET", "POST"])
@permission_required("manage_employees")
def add_employee():
    departments = Department.query.order_by(Department.name).all()

    if request.method == "POST":
        form = request.form
        employee_code = form.get("employee_code", "").strip()
        email = form.get("email", "").strip().lower()

        errors = []
        if Employee.query.filter_by(employee_code=employee_code).first():
            errors.append("Employee ID already exists.")
        if Employee.query.filter_by(email=email).first():
            errors.append("Email already exists.")
        if not form.get("first_name") or not form.get("last_name"):
            errors.append("First and last name are required.")

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("employees/add.html", departments=departments, form=form)

        employee = Employee(
            employee_code=employee_code,
            first_name=form.get("first_name").strip(),
            last_name=form.get("last_name").strip(),
            email=email,
            phone=form.get("phone"),
            date_of_birth=_parse_date(form.get("date_of_birth")),
            gender=form.get("gender"),
            address=form.get("address"),
            emergency_contact=form.get("emergency_contact"),
            department_id=form.get("department_id") or None,
            job_title=form.get("job_title"),
            manager_name=form.get("manager_name"),
            joining_date=_parse_date(form.get("joining_date")) or datetime.utcnow().date(),
            employment_type=form.get("employment_type", "Full-Time"),
            location=form.get("location"),
            status=form.get("status", "Active"),
            salary=float(form.get("salary") or 0),
            experience_years=float(form.get("experience_years") or 0),
            skills=form.get("skills"),
        )
        db.session.add(employee)
        db.session.flush()

        if employee.salary:
            db.session.add(SalaryRecord(employee_id=employee.id, base_salary=employee.salary,
                                         effective_date=employee.joining_date))

        db.session.add(Notification(message=f"New employee added: {employee.full_name}", category="employee"))
        db.session.commit()

        flash(f"Employee {employee.full_name} added successfully.", "success")
        return redirect(url_for("employees.list_employees"))

    return render_template("employees/add.html", departments=departments, form={})


@employees_bp.route("/<int:employee_id>")
@login_required
def view_employee(employee_id):
    employee = Employee.query.get_or_404(employee_id)

    attendance_records = employee.attendance_records.order_by(Attendance.date.desc()).limit(30).all()
    present_days = employee.attendance_records.filter(Attendance.status == "Present").count()
    absent_days = employee.attendance_records.filter(Attendance.status == "Absent").count()
    late_days = employee.attendance_records.filter(Attendance.status == "Late").count()
    total_marked = employee.attendance_records.count()
    attendance_pct = round((present_days + late_days) / total_marked * 100, 1) if total_marked else 0

    leave_history = employee.leave_requests.order_by(LeaveRequest.applied_on.desc()).all()
    used_leave = sum(l.days for l in leave_history if l.status == "Approved")
    total_leave = 42  # standard annual entitlement across all leave types
    remaining_leave = max(total_leave - used_leave, 0)

    reviews = employee.performance_reviews.order_by(PerformanceReview.review_date.desc()).all()
    latest_rating = reviews[0].overall_rating if reviews else None
    previous_rating = reviews[1].overall_rating if len(reviews) > 1 else None

    salary_history = employee.salary_records.order_by(SalaryRecord.effective_date.desc()).all()

    # Salary benchmarking vs department and job-title averages
    import hr_intelligence as hi
    benchmark = hi.benchmark_salary(employee)
    attendance_rate_90d = hi.employee_attendance_rate(employee.id)
    leave_days_12m = hi.employee_leave_days(employee.id)

    # Attrition risk for this individual (only if the model is trainable)
    risk = None
    try:
        import attrition_model as am
        model_result = am.train_and_predict()
        if model_result.get("available"):
            for p in model_result.get("predictions", []):
                if p["employee_id"] == employee.id:
                    risk = p
                    break
            risk_unavailable = None
        else:
            risk_unavailable = model_result.get("message")
    except Exception:
        risk_unavailable = "Attrition risk could not be computed."

    # Activity timeline assembled from real records
    activity = []
    if employee.joining_date:
        activity.append({"date": employee.joining_date, "icon": "bi-person-plus",
                          "title": "Joined the company",
                          "detail": f"{employee.job_title or 'Employee'} in "
                                    f"{employee.department.name if employee.department else 'Unassigned'}"})
    for s in employee.salary_records.order_by(SalaryRecord.effective_date.desc()).limit(5).all():
        activity.append({"date": s.effective_date, "icon": "bi-cash-coin",
                          "title": "Salary record", "detail": f"Base {s.base_salary:,.0f}"})
    for r in reviews[:5]:
        activity.append({"date": r.review_date, "icon": "bi-star",
                          "title": "Performance review",
                          "detail": f"Rated {r.overall_rating}/5 by {r.reviewer or 'manager'}"})
    for l in leave_history[:5]:
        activity.append({"date": l.start_date, "icon": "bi-airplane",
                          "title": f"{l.leave_type} ({l.status})",
                          "detail": f"{l.days} day(s) from {l.start_date}"})
    if employee.exit_date:
        activity.append({"date": employee.exit_date, "icon": "bi-box-arrow-right",
                          "title": "Left the company",
                          "detail": employee.exit_reason or employee.status})
    activity = sorted([a for a in activity if a["date"]], key=lambda a: a["date"], reverse=True)[:12]

    return render_template(
        "employees/profile.html",
        employee=employee,
        attendance_records=attendance_records,
        present_days=present_days, absent_days=absent_days, late_days=late_days,
        attendance_pct=attendance_pct,
        leave_history=leave_history, used_leave=used_leave,
        total_leave=total_leave, remaining_leave=remaining_leave,
        reviews=reviews, latest_rating=latest_rating, previous_rating=previous_rating,
        salary_history=salary_history,
        benchmark=benchmark,
        attendance_rate_90d=attendance_rate_90d,
        leave_days_12m=leave_days_12m,
        risk=risk, risk_unavailable=risk_unavailable, activity=activity,
    )


@employees_bp.route("/<int:employee_id>/edit", methods=["GET", "POST"])
@permission_required("manage_employees")
def edit_employee(employee_id):
    employee = Employee.query.get_or_404(employee_id)
    departments = Department.query.order_by(Department.name).all()

    if request.method == "POST":
        form = request.form
        email = form.get("email", "").strip().lower()
        employee_code = form.get("employee_code", "").strip()

        dup_email = Employee.query.filter(Employee.email == email, Employee.id != employee.id).first()
        dup_code = Employee.query.filter(Employee.employee_code == employee_code,
                                          Employee.id != employee.id).first()
        if dup_email:
            flash("Another employee already uses that email.", "danger")
            return render_template("employees/edit.html", employee=employee, departments=departments)
        if dup_code:
            flash("Another employee already uses that Employee ID.", "danger")
            return render_template("employees/edit.html", employee=employee, departments=departments)

        old_salary = employee.salary

        employee.employee_code = employee_code
        employee.first_name = form.get("first_name").strip()
        employee.last_name = form.get("last_name").strip()
        employee.email = email
        employee.phone = form.get("phone")
        employee.date_of_birth = _parse_date(form.get("date_of_birth"))
        employee.gender = form.get("gender")
        employee.address = form.get("address")
        employee.emergency_contact = form.get("emergency_contact")
        employee.department_id = form.get("department_id") or None
        employee.job_title = form.get("job_title")
        employee.manager_name = form.get("manager_name")
        employee.joining_date = _parse_date(form.get("joining_date")) or employee.joining_date
        employee.employment_type = form.get("employment_type", employee.employment_type)
        employee.location = form.get("location")
        employee.status = form.get("status", employee.status)
        employee.salary = float(form.get("salary") or 0)
        employee.experience_years = float(form.get("experience_years") or 0)
        employee.skills = form.get("skills")

        if employee.status in ("Resigned", "Terminated") and not employee.exit_date:
            employee.exit_date = datetime.utcnow().date()
            employee.exit_reason = form.get("exit_reason") or employee.exit_reason

        if employee.salary != old_salary:
            db.session.add(SalaryRecord(employee_id=employee.id, base_salary=employee.salary,
                                         effective_date=datetime.utcnow().date()))

        db.session.commit()
        flash(f"Employee {employee.full_name} updated.", "success")
        return redirect(url_for("employees.view_employee", employee_id=employee.id))

    return render_template("employees/edit.html", employee=employee, departments=departments)


@employees_bp.route("/<int:employee_id>/deactivate", methods=["POST"])
@permission_required("manage_employees")
def deactivate_employee(employee_id):
    employee = Employee.query.get_or_404(employee_id)
    employee.status = "Inactive"
    employee.exit_date = employee.exit_date or datetime.utcnow().date()
    employee.exit_reason = request.form.get("exit_reason", "Deactivated by HR")
    db.session.commit()
    flash(f"{employee.full_name} has been deactivated. Historical records are preserved.", "info")
    return redirect(url_for("employees.list_employees"))


@employees_bp.route("/<int:employee_id>/photo", methods=["POST"])
@permission_required("manage_employees")
def upload_photo(employee_id):
    employee = Employee.query.get_or_404(employee_id)
    file = request.files.get("profile_picture")

    if not file or file.filename == "":
        flash("Please choose an image file to upload.", "danger")
        return redirect(url_for("employees.view_employee", employee_id=employee.id))

    if not is_allowed_image(file.filename):
        flash("Only JPG, JPEG, PNG, and WebP images are allowed.", "danger")
        return redirect(url_for("employees.view_employee", employee_id=employee.id))

    ok, size = file_size_ok(file, MAX_IMAGE_SIZE_BYTES)
    if not ok:
        flash(f"Image is too large ({size // 1024} KB). Maximum allowed size is "
              f"{MAX_IMAGE_SIZE_BYTES // (1024 * 1024)} MB.", "danger")
        return redirect(url_for("employees.view_employee", employee_id=employee.id))

    # Remove any previous picture before saving the new one
    delete_file_if_exists(current_app.static_folder, employee.profile_picture)

    filename = safe_unique_filename(file.filename, employee_code=employee.employee_code, prefix="emp")
    dest_path = resolve_upload_path(current_app.static_folder, PROFILE_PICS_SUBDIR, filename)
    file.save(dest_path)

    employee.profile_picture = os.path.join(PROFILE_PICS_SUBDIR, filename).replace("\\", "/")
    db.session.commit()

    flash(f"Profile picture updated for {employee.full_name}.", "success")
    return redirect(url_for("employees.view_employee", employee_id=employee.id))


@employees_bp.route("/<int:employee_id>/photo/remove", methods=["POST"])
@permission_required("manage_employees")
def remove_photo(employee_id):
    employee = Employee.query.get_or_404(employee_id)
    delete_file_if_exists(current_app.static_folder, employee.profile_picture)
    employee.profile_picture = None
    db.session.commit()
    flash(f"Profile picture removed for {employee.full_name}. Showing initials avatar.", "info")
    return redirect(url_for("employees.view_employee", employee_id=employee.id))

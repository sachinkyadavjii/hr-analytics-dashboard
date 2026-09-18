from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from sqlalchemy import or_

from extensions import db
from auth_utils import login_required, permission_required, current_user
from models import User, Employee, Department
from audit import log_audit

users_bp = Blueprint("users", __name__, url_prefix="/user-management")


@users_bp.route("/")
@permission_required("manage_users")
def list_users():
    q = request.args.get("q", "").strip()
    role_filter = request.args.get("role", "")
    status_filter = request.args.get("status", "")
    department_filter = request.args.get("department", "")

    query = User.query
    if q:
        like = f"%{q}%"
        query = query.filter(or_(User.name.ilike(like), User.email.ilike(like)))
    if role_filter:
        query = query.filter(User.role == role_filter)
    if status_filter:
        query = query.filter(User.status == status_filter)
    if department_filter:
        query = query.join(Employee, User.employee_id == Employee.id).filter(
            Employee.department_id == department_filter)

    users = query.order_by(User.created_at.desc()).all()
    departments = Department.query.order_by(Department.name).all()

    return render_template(
        "users/list.html", users=users, departments=departments,
        filters={"q": q, "role": role_filter, "status": status_filter, "department": department_filter},
    )


@users_bp.route("/create", methods=["GET", "POST"])
@permission_required("manage_users")
def create_user():
    actor = current_user()
    allowed_roles = actor.creatable_roles()

    if not allowed_roles:
        # Defense in depth: even if someone reaches this route, they have
        # no roles they're allowed to create.
        flash("Your role does not permit creating user accounts.", "danger")
        return redirect(url_for("users.list_users"))

    # Employees who don't already have a login account, so we never create
    # duplicate Employee records or double-link one employee to two logins.
    unlinked_employees = Employee.query.filter(
        ~Employee.id.in_(db.session.query(User.employee_id).filter(User.employee_id.isnot(None)))
    ).order_by(Employee.first_name).all()

    if request.method == "POST":
        form = request.form
        name = form.get("name", "").strip()
        email = form.get("email", "").strip().lower()
        role = form.get("role", "")
        status = form.get("status", "Active")
        password = form.get("password", "")
        confirm_password = form.get("confirm_password", "")
        employee_id = form.get("employee_id") or None

        errors = []
        if not name or not email:
            errors.append("Full name and email are required.")
        if role not in allowed_roles:
            # Server-side enforcement — never trust the submitted role even
            # if the form only rendered allowed options.
            errors.append("You are not permitted to create an account with that role.")
        if User.query.filter_by(email=email).first():
            errors.append("An account with that email already exists.")
        if not password or len(password) < 8:
            errors.append("Password must be at least 8 characters.")
        if password != confirm_password:
            errors.append("Password and confirm password do not match.")
        if status not in ["Active", "Inactive", "Suspended"]:
            status = "Active"

        employee = None
        if employee_id:
            employee = Employee.query.get(employee_id)
            if not employee:
                errors.append("Selected employee record was not found.")
            elif employee.user_account is not None:
                errors.append("That employee already has a linked user account.")

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("users/create.html", allowed_roles=allowed_roles,
                                    unlinked_employees=unlinked_employees, form=form)

        new_user = User(
            name=name, email=email, role=role, status=status,
            employee_id=employee.id if employee else None,
            must_change_password=True,   # temporary password flow
            created_by_id=actor.id,
        )
        new_user.set_password(password)
        db.session.add(new_user)

        log_audit("User Created", performed_by=actor, target_user=new_user,
                   details=f"Role: {role}" + (f", linked to employee {employee.full_name}" if employee else ""))
        db.session.commit()

        flash(f"Account created for {new_user.name}. They will be required to set a new password on first login.",
              "success")
        return redirect(url_for("users.list_users"))

    return render_template("users/create.html", allowed_roles=allowed_roles,
                            unlinked_employees=unlinked_employees, form={})


@users_bp.route("/<int:user_id>")
@permission_required("manage_users")
def view_user(user_id):
    target = User.query.get_or_404(user_id)
    return render_template("users/view.html", target=target)


@users_bp.route("/<int:user_id>/edit", methods=["GET", "POST"])
@permission_required("manage_users")
def edit_user(user_id):
    actor = current_user()
    target = User.query.get_or_404(user_id)

    # A user can always edit accounts with a role they're allowed to create,
    # PLUS they must be able to edit at their own level or below — but never
    # escalate/edit someone whose role they couldn't have created themselves,
    # to stop e.g. HR editing an Admin account.
    allowed_roles = actor.creatable_roles()
    if target.role not in allowed_roles and target.id != actor.id:
        flash("You are not permitted to edit this account.", "danger")
        return redirect(url_for("users.list_users"))

    if request.method == "POST":
        form = request.form
        old_role = target.role
        new_role = form.get("role", target.role)

        if new_role != old_role and new_role not in allowed_roles:
            flash("You are not permitted to assign that role.", "danger")
            return redirect(url_for("users.edit_user", user_id=target.id))

        target.name = form.get("name", target.name).strip()
        target.role = new_role
        target.status = form.get("status", target.status)

        if new_role != old_role:
            log_audit("Role Changed", performed_by=actor, target_user=target,
                       details=f"{old_role} -> {new_role}")

        db.session.commit()
        flash(f"Account for {target.name} updated.", "success")
        return redirect(url_for("users.list_users"))

    return render_template("users/edit.html", target=target, allowed_roles=allowed_roles)


@users_bp.route("/<int:user_id>/deactivate", methods=["POST"])
@permission_required("manage_users")
def deactivate_user(user_id):
    actor = current_user()
    target = User.query.get_or_404(user_id)

    if target.id == actor.id:
        flash("You cannot deactivate your own account.", "danger")
        return redirect(url_for("users.list_users"))
    if target.role not in actor.creatable_roles():
        flash("You are not permitted to deactivate this account.", "danger")
        return redirect(url_for("users.list_users"))

    target.status = "Inactive"
    log_audit("User Deactivated", performed_by=actor, target_user=target)
    db.session.commit()
    flash(f"{target.name}'s account has been deactivated. They can no longer log in; "
          f"their employee records and history are unaffected.", "info")
    return redirect(url_for("users.list_users"))


@users_bp.route("/<int:user_id>/reactivate", methods=["POST"])
@permission_required("manage_users")
def reactivate_user(user_id):
    actor = current_user()
    target = User.query.get_or_404(user_id)

    if target.role not in actor.creatable_roles():
        flash("You are not permitted to reactivate this account.", "danger")
        return redirect(url_for("users.list_users"))

    target.status = "Active"
    log_audit("User Reactivated", performed_by=actor, target_user=target)
    db.session.commit()
    flash(f"{target.name}'s account has been reactivated.", "success")
    return redirect(url_for("users.list_users"))


@users_bp.route("/<int:user_id>/reset-password", methods=["POST"])
@permission_required("manage_users")
def reset_password(user_id):
    actor = current_user()
    target = User.query.get_or_404(user_id)

    if target.role not in actor.creatable_roles() and target.id != actor.id:
        flash("You are not permitted to reset this account's password.", "danger")
        return redirect(url_for("users.list_users"))

    new_password = request.form.get("new_password", "")
    if len(new_password) < 8:
        flash("New password must be at least 8 characters.", "danger")
        return redirect(url_for("users.view_user", user_id=target.id))

    target.set_password(new_password)
    target.must_change_password = True
    log_audit("Password Reset", performed_by=actor, target_user=target,
               details="Temporary password set by HR/Admin")
    db.session.commit()

    flash(f"Password reset for {target.name}. They will be required to set a new password on next login. "
          f"Share the temporary password with them through a secure channel.", "success")
    return redirect(url_for("users.view_user", user_id=target.id))


@users_bp.route("/audit-log")
@permission_required("view_audit_log")
def audit_log():
    from models import AuditLog
    entries = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(200).all()
    return render_template("users/audit_log.html", entries=entries)

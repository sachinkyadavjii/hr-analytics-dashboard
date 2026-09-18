from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from extensions import db
from models import User
from auth_utils import login_required, current_user
from audit import log_audit

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/", methods=["GET"])
def index():
    if session.get("user_id"):
        return redirect(url_for("dashboard.index"))
    return redirect(url_for("auth.login"))


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("dashboard.index"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        remember = request.form.get("remember")

        user = User.query.filter_by(email=email).first()
        if not user or not user.check_password(password):
            flash("Invalid email or password.", "danger")
            return render_template("login.html")

        if user.status != "Active":
            flash(f"This account is {user.status.lower()}. Contact your HR/Admin for access.", "danger")
            return render_template("login.html")

        session["user_id"] = user.id
        session["role"] = user.role
        session["name"] = user.name
        session["employee_id"] = user.employee_id
        session["must_change_password"] = user.must_change_password
        session.permanent = bool(remember)

        user.last_login = datetime.utcnow()
        db.session.commit()

        if user.must_change_password:
            flash("For security, please set a new password before continuing.", "warning")
            return redirect(url_for("auth.change_password"))

        flash(f"Welcome back, {user.name.split(' ')[0]}!", "success")
        next_url = request.args.get("next")
        return redirect(next_url or url_for("dashboard.index"))

    return render_template("login.html")


@auth_bp.route("/forgot-password")
def forgot_password():
    """No email-based reset is implemented, so this is intentionally just an
    informational page — NOT a self-service reset. A public 'enter your
    email to reset' flow without email verification would let anyone reset
    anyone else's password just by knowing their address, which is far
    less secure than routing the request through HR/Admin."""
    return render_template("forgot_password.html")


@auth_bp.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    """Self-service password change. Available to every logged-in role.
    Also the forced landing page after HR/Admin sets a temporary password."""
    user = current_user()
    forced = bool(session.get("must_change_password"))

    if request.method == "POST":
        current_pw = request.form.get("current_password", "")
        new_pw = request.form.get("new_password", "")
        confirm_pw = request.form.get("confirm_password", "")

        if not user.check_password(current_pw):
            flash("Current password is incorrect.", "danger")
            return render_template("change_password.html", forced=forced)
        if len(new_pw) < 8:
            flash("New password must be at least 8 characters.", "danger")
            return render_template("change_password.html", forced=forced)
        if new_pw != confirm_pw:
            flash("New password and confirmation do not match.", "danger")
            return render_template("change_password.html", forced=forced)
        if user.check_password(new_pw):
            flash("New password must be different from your current password.", "danger")
            return render_template("change_password.html", forced=forced)

        user.set_password(new_pw)
        user.must_change_password = False
        log_audit("Password Changed", performed_by=user, target_user=user,
                   details="Self-service password change")
        db.session.commit()

        session["must_change_password"] = False
        flash("Password updated successfully.", "success")
        return redirect(url_for("dashboard.index"))

    return render_template("change_password.html", forced=forced)

from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from extensions import db
from models import User

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

        if not user.is_active:
            flash("This account has been deactivated. Contact your administrator.", "danger")
            return render_template("login.html")

        session["user_id"] = user.id
        session["role"] = user.role
        session["name"] = user.name
        session["employee_id"] = user.employee_id
        session.permanent = bool(remember)

        user.last_login = datetime.utcnow()
        db.session.commit()

        flash(f"Welcome back, {user.name.split(' ')[0]}!", "success")
        next_url = request.args.get("next")
        return redirect(next_url or url_for("dashboard.index"))

    return render_template("login.html")


@auth_bp.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))

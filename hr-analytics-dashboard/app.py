import os
from datetime import datetime, date
from flask import Flask, render_template, session
from dotenv import load_dotenv

load_dotenv()

from config import Config
from extensions import db, csrf


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    csrf.init_app(app)

    # ---- Blueprints ----
    from routes.auth import auth_bp
    from routes.dashboard import dashboard_bp
    from routes.employees import employees_bp
    from routes.departments import departments_bp
    from routes.attendance import attendance_bp
    from routes.leave import leave_bp
    from routes.performance import performance_bp
    from routes.payroll import payroll_bp
    from routes.analytics import analytics_bp
    from routes.reports import reports_bp
    from routes.settings import settings_bp
    from routes.notifications import notifications_bp
    from routes.data_upload import data_upload_bp
    from routes.intelligence import intelligence_bp
    from routes.users import users_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(employees_bp)
    app.register_blueprint(departments_bp)
    app.register_blueprint(attendance_bp)
    app.register_blueprint(leave_bp)
    app.register_blueprint(performance_bp)
    app.register_blueprint(payroll_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(notifications_bp)
    app.register_blueprint(data_upload_bp)
    app.register_blueprint(intelligence_bp)
    app.register_blueprint(users_bp)

    # ---- Forced password-change enforcement ----
    # A user with a temporary password (freshly created or just reset by
    # HR/Admin) cannot use ANY other route until they set their own
    # password — this is checked on every request server-side, not just
    # hidden behind a UI redirect, so it can't be bypassed by typing a URL
    # directly.
    _ALLOWED_WHILE_FORCED = {
        "auth.change_password", "auth.logout", "static",
    }

    @app.before_request
    def enforce_password_change():
        from flask import request, redirect, url_for
        if session.get("user_id") and session.get("must_change_password"):
            if request.endpoint not in _ALLOWED_WHILE_FORCED:
                return redirect(url_for("auth.change_password"))

    # ---- Template globals / filters ----
    @app.context_processor
    def inject_globals():
        from models import Notification
        unread_count = 0
        if session.get("user_id"):
            unread_count = Notification.query.filter_by(is_read=False).count()
        return {
            "current_year": datetime.utcnow().year,
            "session_role": session.get("role"),
            "session_name": session.get("name"),
            "unread_notifications": unread_count,
        }

    @app.template_filter("money")
    def money_filter(value):
        try:
            return f"\u20b9{float(value):,.0f}"
        except (TypeError, ValueError):
            return "\u20b90"

    @app.template_filter("dateformat")
    def dateformat_filter(value, fmt="%d %b %Y"):
        if not value:
            return "-"
        if isinstance(value, str):
            return value
        return value.strftime(fmt)

    # ---- Error handlers ----
    @app.errorhandler(404)
    def not_found(e):
        return render_template("errors/404.html"), 404

    @app.errorhandler(403)
    def forbidden(e):
        return render_template("errors/403.html"), 403

    @app.errorhandler(413)
    def file_too_large(e):
        from flask import flash, redirect, request, url_for
        flash("The uploaded file is too large.", "danger")
        return redirect(request.referrer or url_for("dashboard.index")), 413

    @app.errorhandler(500)
    def server_error(e):
        db.session.rollback()
        return render_template("errors/500.html"), 500

    with app.app_context():
        db.create_all()
        _auto_seed_if_empty(app)

    return app


def _auto_seed_if_empty(app):
    """On some hosts (e.g. Render's free tier) there is no Shell access to
    run `python data/seed_data.py` manually, and the SQLite file is wiped on
    every restart/redeploy. Rather than leaving a freshly-restarted deploy
    with an empty User table (nobody able to log in at all), automatically
    seed demo data the first time the app boots against an empty database.

    This intentionally does NOT run against a database that already has any
    users — it only ever fires once, on a genuinely empty database, so it
    can never silently wipe real production data added after seeding.
    Set AUTO_SEED_ON_EMPTY_DB=0 to disable this entirely (e.g. once you've
    switched to a persistent Postgres database and don't want it)."""
    if os.environ.get("AUTO_SEED_ON_EMPTY_DB", "1") == "0":
        return
    from models import User
    try:
        if User.query.count() > 0:
            return
    except Exception:
        # Table might not exist yet on a very first boot before create_all
        # has fully settled in some edge case — fail safe by skipping.
        return

    app.logger.info("Database is empty — running first-time demo data seed...")
    try:
        from data.seed_data import run_seed
        run_seed(clear_first=False)
        app.logger.info("Auto-seed complete.")
    except Exception as e:
        # Never let a seeding problem crash app startup — worst case the
        # app boots with an empty DB, which is recoverable, vs. not booting
        # at all.
        app.logger.error(f"Auto-seed failed: {e}")


app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)

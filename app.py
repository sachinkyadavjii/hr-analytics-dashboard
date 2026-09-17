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
        from flask import flash, redirect, request
        flash("The uploaded file is too large.", "danger")
        return redirect(request.referrer or url_for("dashboard.index")), 413

    @app.errorhandler(500)
    def server_error(e):
        db.session.rollback()
        return render_template("errors/500.html"), 500

    with app.app_context():
        db.create_all()

    return app


app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)

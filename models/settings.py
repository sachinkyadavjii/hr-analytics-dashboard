from extensions import db


class CompanySettings(db.Model):
    """Single-row table holding company-wide configuration."""
    __tablename__ = "company_settings"

    id = db.Column(db.Integer, primary_key=True)
    company_name = db.Column(db.String(150), default="HR Analytics Inc.")
    company_email = db.Column(db.String(150), default="info@hranalytics.com")
    company_phone = db.Column(db.String(30), default="+91 98765 43210")
    company_address = db.Column(db.String(255), default="Bengaluru, India")
    working_days = db.Column(db.String(100), default="Monday - Friday")
    casual_leave_days = db.Column(db.Integer, default=12)
    sick_leave_days = db.Column(db.Integer, default=10)
    earned_leave_days = db.Column(db.Integer, default=15)
    emergency_leave_days = db.Column(db.Integer, default=5)

    @staticmethod
    def get():
        settings = CompanySettings.query.first()
        if not settings:
            settings = CompanySettings()
            db.session.add(settings)
            db.session.commit()
        return settings

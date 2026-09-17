from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from extensions import db


class User(db.Model):
    """Login account. Linked 1-to-1 with an Employee record where relevant
    (e.g. an EMPLOYEE-role user is tied to their own employee profile)."""

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="EMPLOYEE")  # ADMIN, HR, MANAGER, EMPLOYEE
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime, nullable=True)

    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=True)
    employee = db.relationship("Employee", backref=db.backref("user_account", uselist=False))

    def set_password(self, raw_password):
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password):
        return check_password_hash(self.password_hash, raw_password)

    # Simple permission helpers used across templates/routes
    def can(self, permission):
        matrix = {
            "ADMIN": {"manage_users", "manage_employees", "manage_departments", "manage_attendance",
                      "manage_leave", "manage_performance", "manage_payroll", "view_analytics",
                      "view_reports", "manage_settings", "approve_leave"},
            "HR": {"manage_employees", "manage_departments", "manage_attendance", "manage_leave",
                   "manage_performance", "manage_payroll", "view_analytics", "view_reports", "approve_leave"},
            "MANAGER": {"view_team", "manage_attendance", "approve_leave", "manage_performance"},
            "EMPLOYEE": {"view_self"},
        }
        return permission in matrix.get(self.role, set())

    def __repr__(self):
        return f"<User {self.email} ({self.role})>"

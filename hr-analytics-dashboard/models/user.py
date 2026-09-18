from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from extensions import db

# Which roles a given role is allowed to CREATE via User Management.
# Enforced server-side in routes/users.py — never trust a hidden form field.
CREATABLE_ROLES = {
    "ADMIN": ["ADMIN", "HR", "MANAGER", "EMPLOYEE"],
    "HR": ["MANAGER", "EMPLOYEE"],
    "MANAGER": [],
    "EMPLOYEE": [],
}

ACCOUNT_STATUSES = ["Active", "Inactive", "Suspended"]


class User(db.Model):
    """Login account. Linked 1-to-1 with an Employee record where relevant
    (e.g. an EMPLOYEE-role user is tied to their own employee profile).

    There is deliberately NO public self-registration path anywhere in this
    app — accounts are only ever created by ADMIN/HR through routes/users.py,
    which enforces CREATABLE_ROLES server-side."""

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="EMPLOYEE")  # ADMIN, HR, MANAGER, EMPLOYEE

    # Account status. Logging in requires status == 'Active'. Kept separate
    # from Employee.status (employment status) — deactivating a login has no
    # effect on HR/payroll/attendance history.
    status = db.Column(db.String(20), nullable=False, default="Active")

    # Forces the change-password screen on next login. Set True whenever
    # HR/Admin creates an account or resets a password (temporary password
    # flow), cleared once the user sets their own password.
    must_change_password = db.Column(db.Boolean, default=False, nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime, nullable=True)

    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_by = db.relationship("User", remote_side=[id])

    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=True)
    employee = db.relationship("Employee", backref=db.backref("user_account", uselist=False))

    def set_password(self, raw_password):
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password):
        return check_password_hash(self.password_hash, raw_password)

    @property
    def is_active(self):
        """Backward-compatible boolean view of status, used by login checks."""
        return self.status == "Active"

    def can_create_role(self, target_role):
        return target_role in CREATABLE_ROLES.get(self.role, [])

    def creatable_roles(self):
        return CREATABLE_ROLES.get(self.role, [])

    # Simple permission helpers used across templates/routes
    def can(self, permission):
        matrix = {
            "ADMIN": {"manage_users", "manage_employees", "manage_departments", "manage_attendance",
                      "manage_leave", "manage_performance", "manage_payroll", "view_analytics",
                      "view_reports", "manage_settings", "approve_leave", "view_audit_log"},
            "HR": {"manage_users", "manage_employees", "manage_departments", "manage_attendance",
                   "manage_leave", "manage_performance", "manage_payroll", "view_analytics",
                   "view_reports", "approve_leave"},
            "MANAGER": {"view_team", "manage_attendance", "approve_leave", "manage_performance"},
            "EMPLOYEE": {"view_self"},
        }
        return permission in matrix.get(self.role, set())

    def __repr__(self):
        return f"<User {self.email} ({self.role})>"

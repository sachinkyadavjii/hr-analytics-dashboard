from datetime import datetime
from extensions import db


class AuditLog(db.Model):
    """Immutable record of account-related security actions.

    Deliberately denormalized (plain name strings, not foreign keys) so the
    log stays readable and intact even if a user account is later edited —
    audit trails should never silently change after the fact. Passwords are
    NEVER written here, in any form (not even hashed)."""

    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    action = db.Column(db.String(50), nullable=False)
    # e.g. "User Created", "User Deactivated", "User Reactivated",
    # "Role Changed", "Password Reset", "Password Changed",
    # "Employee Linked", "Employee Unlinked"

    performed_by = db.Column(db.String(120), nullable=False)   # name of the actor
    performed_by_role = db.Column(db.String(20), nullable=True)
    target_user = db.Column(db.String(120), nullable=True)      # name of the affected account
    details = db.Column(db.String(300), nullable=True)          # short human-readable context

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<AuditLog {self.action} by={self.performed_by} target={self.target_user}>"

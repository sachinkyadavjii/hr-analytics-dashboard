from datetime import datetime
from extensions import db


class LeaveRequest(db.Model):
    __tablename__ = "leave_requests"

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=False)
    leave_type = db.Column(db.String(30), nullable=False)  # Casual, Sick, Earned, Emergency
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    reason = db.Column(db.String(300))
    status = db.Column(db.String(20), default="Pending")  # Pending, Approved, Rejected
    applied_on = db.Column(db.DateTime, default=datetime.utcnow)
    decided_by = db.Column(db.String(120), nullable=True)

    @property
    def days(self):
        return (self.end_date - self.start_date).days + 1

    def __repr__(self):
        return f"<LeaveRequest emp={self.employee_id} {self.leave_type} {self.status}>"


class LeaveBalance(db.Model):
    """Per-employee, per-leave-type entitlement for the year."""
    __tablename__ = "leave_balances"

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=False)
    leave_type = db.Column(db.String(30), nullable=False)
    total_days = db.Column(db.Integer, default=12)

    __table_args__ = (db.UniqueConstraint("employee_id", "leave_type", name="uq_emp_leave_type"),)

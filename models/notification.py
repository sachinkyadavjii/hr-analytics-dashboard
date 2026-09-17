from datetime import datetime
from extensions import db


class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    message = db.Column(db.String(300), nullable=False)
    category = db.Column(db.String(40), default="general")  # leave, employee, performance, general
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # Optional: restrict visibility to a role; null = visible to all HR-side roles
    target_role = db.Column(db.String(20), nullable=True)

    def __repr__(self):
        return f"<Notification {self.message[:30]}>"

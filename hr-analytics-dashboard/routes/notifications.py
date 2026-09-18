from flask import Blueprint, render_template, redirect, url_for
from extensions import db
from auth_utils import login_required
from models import Notification

notifications_bp = Blueprint("notifications", __name__, url_prefix="/notifications")


@notifications_bp.route("/")
@login_required
def list_notifications():
    items = Notification.query.order_by(Notification.created_at.desc()).limit(50).all()
    unread_ids = [n.id for n in items if not n.is_read]
    for n in items:
        n.is_read = True
    if unread_ids:
        db.session.commit()
    return render_template("notifications.html", notifications=items)

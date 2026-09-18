from extensions import db
from models import AuditLog


def log_audit(action, performed_by, target_user=None, details=None):
    """Writes one audit log entry. `performed_by` is a User instance (or a
    plain name string as a fallback). Never pass password values in
    `details` — this function does not scrub input, the caller is
    responsible for never including credentials here."""
    performed_by_name = performed_by.name if hasattr(performed_by, "name") else str(performed_by)
    performed_by_role = getattr(performed_by, "role", None)
    target_name = target_user.name if hasattr(target_user, "name") else target_user

    entry = AuditLog(
        action=action,
        performed_by=performed_by_name,
        performed_by_role=performed_by_role,
        target_user=target_name,
        details=details,
    )
    db.session.add(entry)
    # Intentionally not committing here — caller commits as part of its own
    # transaction so the audit entry and the actual change are atomic.

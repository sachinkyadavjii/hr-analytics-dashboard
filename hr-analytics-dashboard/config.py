import os
from datetime import timedelta

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# The 'instance' folder holds the local SQLite database file and is
# git-ignored (it shouldn't contain committed data). That means on a fresh
# clone (e.g. Render's build), the folder itself doesn't exist yet — and
# SQLite cannot create a database file inside a missing directory. Creating
# it here, before SQLAlchemy ever tries to open a connection, fixes that.
INSTANCE_DIR = os.path.join(BASE_DIR, "instance")
os.makedirs(INSTANCE_DIR, exist_ok=True)


class Config:
    """Base configuration. Values are pulled from environment variables
    so no secrets are ever hardcoded in source control."""

    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")

    # Render (and most hosts) provide DATABASE_URL for Postgres.
    # Locally we fall back to a SQLite file so the app works out of the box.
    _db_url = os.environ.get("DATABASE_URL", "")
    if _db_url.startswith("postgres://"):
        # SQLAlchemy 1.4+/2.x requires the postgresql:// scheme
        _db_url = _db_url.replace("postgres://", "postgresql://", 1)

    SQLALCHEMY_DATABASE_URI = _db_url or f"sqlite:///{os.path.join(INSTANCE_DIR, 'database.db')}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    PERMANENT_SESSION_LIFETIME = timedelta(days=7)

    # Pagination
    EMPLOYEES_PER_PAGE = 15

    WTF_CSRF_ENABLED = True

    # Hard ceiling on any single request body (defense in depth on top of the
    # per-file checks in file_upload_utils.py). Generous enough for dataset
    # uploads (up to 15MB) plus some overhead.
    MAX_CONTENT_LENGTH = 20 * 1024 * 1024

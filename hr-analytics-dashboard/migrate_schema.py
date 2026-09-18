"""
migrate_schema.py
------------------
Safely evolves the existing database schema WITHOUT dropping any tables or
losing existing data. Uses SQLAlchemy's inspector to check what already
exists, and only adds what's missing. Safe to run multiple times.

Run with:  python migrate_schema.py
"""
import sys
from sqlalchemy import inspect, text

from app import create_app
from extensions import db


def column_exists(inspector, table, column):
    cols = [c["name"] for c in inspector.get_columns(table)]
    return column in cols


def table_exists(inspector, table):
    return table in inspector.get_table_names()


def add_column(engine, table, column_def):
    """column_def example: 'profile_picture VARCHAR(255)'"""
    with engine.begin() as conn:
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column_def}"))


def main():
    app = create_app()
    with app.app_context():
        # Ensure all tables from models exist first (new tables only — never
        # touches existing ones).
        db.create_all()

        engine = db.engine
        inspector = inspect(engine)

        changes = []

        # --- Employee: profile_picture ---
        if table_exists(inspector, "employees") and not column_exists(inspector, "employees", "profile_picture"):
            add_column(engine, "employees", "profile_picture VARCHAR(255)")
            changes.append("employees.profile_picture")

        # --- User: secure account-management fields ---
        if table_exists(inspector, "users"):
            had_is_active = column_exists(inspector, "users", "is_active")

            if not column_exists(inspector, "users", "status"):
                add_column(engine, "users", "status VARCHAR(20) DEFAULT 'Active'")
                changes.append("users.status")
                # Preserve existing accounts' active/inactive state from the
                # old is_active boolean, so nobody gets silently locked out
                # (or silently re-enabled) by this migration.
                if had_is_active:
                    with engine.begin() as conn:
                        conn.execute(text(
                            "UPDATE users SET status = CASE WHEN is_active = 0 THEN 'Inactive' ELSE 'Active' END"
                        ))

            if not column_exists(inspector, "users", "must_change_password"):
                add_column(engine, "users", "must_change_password BOOLEAN DEFAULT 0")
                changes.append("users.must_change_password")

            if not column_exists(inspector, "users", "created_by_id"):
                add_column(engine, "users", "created_by_id INTEGER")
                changes.append("users.created_by_id")

        if not changes:
            print("Schema already up to date. No changes needed.")
        else:
            print("Schema updated safely. Added columns:")
            for c in changes:
                print(f"  - {c}")

        # Re-inspect to confirm
        inspector = inspect(engine)
        print("\nCurrent tables:", inspector.get_table_names())


if __name__ == "__main__":
    main()

"""Shared Flask extension instances.

Kept in their own module so models and routes can import `db` without
causing circular imports with the app factory in app.py.
"""
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect

db = SQLAlchemy()
csrf = CSRFProtect()

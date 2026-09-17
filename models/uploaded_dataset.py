import json
from datetime import datetime
from extensions import db


class UploadedDataset(db.Model):
    """Metadata for a CSV/Excel file uploaded for standalone analysis.

    IMPORTANT: this is intentionally isolated from the Employee table.
    Uploaded datasets are analyzed as their own DataFrame and never write
    to, or read from, the production HR tables. The raw file is stored on
    disk (never in the DB) under instance/uploads/datasets/.
    """
    __tablename__ = "uploaded_datasets"

    id = db.Column(db.Integer, primary_key=True)
    original_filename = db.Column(db.String(255), nullable=False)
    stored_path = db.Column(db.String(500), nullable=False)  # path relative to instance/
    file_size_bytes = db.Column(db.Integer, default=0)
    file_type = db.Column(db.String(10))  # csv / xlsx / xls

    uploaded_by = db.Column(db.String(120))
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

    row_count = db.Column(db.Integer, default=0)
    column_count = db.Column(db.Integer, default=0)

    # JSON-encoded dict: canonical_field -> actual column name in the file
    # (or null if that field wasn't found / mapped)
    column_mapping_json = db.Column(db.Text, default="{}")

    # "pending_mapping" (needs manual confirmation), "ready" (mapping
    # confirmed, analytics available), "error"
    status = db.Column(db.String(30), default="pending_mapping")

    @property
    def column_mapping(self):
        try:
            return json.loads(self.column_mapping_json or "{}")
        except (ValueError, TypeError):
            return {}

    @column_mapping.setter
    def column_mapping(self, value):
        self.column_mapping_json = json.dumps(value)

    def __repr__(self):
        return f"<UploadedDataset {self.original_filename} ({self.status})>"

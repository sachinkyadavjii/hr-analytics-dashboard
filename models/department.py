from extensions import db


class Department(db.Model):
    __tablename__ = "departments"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    manager_name = db.Column(db.String(120), nullable=True)
    status = db.Column(db.String(20), default="Active")  # Active / Inactive

    employees = db.relationship("Employee", backref="department", lazy="dynamic")

    def __repr__(self):
        return f"<Department {self.name}>"

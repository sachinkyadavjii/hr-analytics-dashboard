from datetime import datetime
from extensions import db


class Employee(db.Model):
    __tablename__ = "employees"

    id = db.Column(db.Integer, primary_key=True)
    employee_code = db.Column(db.String(20), unique=True, nullable=False, index=True)  # e.g. EMP1001

    # Personal information
    first_name = db.Column(db.String(80), nullable=False)
    last_name = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False, index=True)
    phone = db.Column(db.String(30))
    date_of_birth = db.Column(db.Date)
    gender = db.Column(db.String(20))
    address = db.Column(db.String(255))
    emergency_contact = db.Column(db.String(120))

    # Work information
    department_id = db.Column(db.Integer, db.ForeignKey("departments.id"), nullable=True)
    job_title = db.Column(db.String(120))
    manager_name = db.Column(db.String(120))
    joining_date = db.Column(db.Date)
    employment_type = db.Column(db.String(30), default="Full-Time")  # Full-Time, Part-Time, Contract, Intern
    location = db.Column(db.String(120))
    status = db.Column(db.String(20), default="Active")  # Active, On Leave, Inactive, Resigned, Terminated

    # Employment information
    salary = db.Column(db.Float, default=0)
    experience_years = db.Column(db.Float, default=0)
    skills = db.Column(db.String(300))

    # Profile picture — stores a relative path under static/uploads/profile_pics/,
    # never the raw binary in the DB. Null means "use initials avatar".
    profile_picture = db.Column(db.String(255), nullable=True)

    # Attrition tracking
    exit_date = db.Column(db.Date, nullable=True)
    exit_reason = db.Column(db.String(120), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    attendance_records = db.relationship("Attendance", backref="employee", lazy="dynamic",
                                          cascade="all, delete-orphan")
    leave_requests = db.relationship("LeaveRequest", backref="employee", lazy="dynamic",
                                      cascade="all, delete-orphan")
    performance_reviews = db.relationship("PerformanceReview", backref="employee", lazy="dynamic",
                                           cascade="all, delete-orphan")
    salary_records = db.relationship("SalaryRecord", backref="employee", lazy="dynamic",
                                      cascade="all, delete-orphan")

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def initials(self):
        first = (self.first_name or "?")[0]
        last = (self.last_name or "")[0] if self.last_name else ""
        return (first + last).upper()

    @property
    def avatar_color(self):
        """Deterministic color from the employee's name so the same person
        always gets the same fallback avatar color, without any randomness."""
        palette = ["#2f6bff", "#f97066", "#12b76a", "#f79009", "#9b8afb",
                   "#06aed4", "#ee46bc", "#667085", "#7a5af8", "#e04f16"]
        seed = sum(ord(ch) for ch in (self.full_name or "?"))
        return palette[seed % len(palette)]

    @property
    def is_leaver(self):
        return self.status in ("Resigned", "Terminated")

    def __repr__(self):
        return f"<Employee {self.employee_code} {self.full_name}>"

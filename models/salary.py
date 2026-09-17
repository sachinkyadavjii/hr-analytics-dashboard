from datetime import datetime
from extensions import db


class SalaryRecord(db.Model):
    __tablename__ = "salary_records"

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=False)
    base_salary = db.Column(db.Float, nullable=False)
    bonus = db.Column(db.Float, default=0)
    deduction = db.Column(db.Float, default=0)
    effective_date = db.Column(db.Date, default=datetime.utcnow)

    @property
    def net_salary(self):
        return round(self.base_salary + self.bonus - self.deduction, 2)

    def __repr__(self):
        return f"<SalaryRecord emp={self.employee_id} net={self.net_salary}>"

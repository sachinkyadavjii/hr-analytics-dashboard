from datetime import datetime
from extensions import db


class PerformanceReview(db.Model):
    __tablename__ = "performance_reviews"

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=False)
    review_date = db.Column(db.Date, default=datetime.utcnow)
    reviewer = db.Column(db.String(120))

    overall_rating = db.Column(db.Float, nullable=False)  # 1-5
    technical_skills = db.Column(db.Integer)
    communication = db.Column(db.Integer)
    teamwork = db.Column(db.Integer)
    leadership = db.Column(db.Integer)
    problem_solving = db.Column(db.Integer)

    goals = db.Column(db.String(400))
    comments = db.Column(db.String(500))

    def __repr__(self):
        return f"<PerformanceReview emp={self.employee_id} rating={self.overall_rating}>"

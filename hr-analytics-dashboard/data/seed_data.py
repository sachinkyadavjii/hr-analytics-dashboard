"""
seed_data.py
------------
Populates the database with realistic (fictional) demo data:
- 4 demo user accounts (one per role)
- 6 departments
- 180 employees with varied departments, salaries, tenure, and some
  historical leavers for attrition analysis
- Attendance history (last 90 days, business days only)
- Leave requests (mixed statuses)
- Performance reviews
- Salary history

Run with:  python data/seed_data.py
"""
import os
import random
import sys
from datetime import date, timedelta, datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from faker import Faker

from app import create_app
from extensions import db
from models import (User, Department, Employee, Attendance, LeaveRequest,
                     PerformanceReview, SalaryRecord, Notification, CompanySettings)

fake = Faker()
random.seed(42)
Faker.seed(42)

DEPARTMENTS = [
    ("IT", "Ananya Sharma"),
    ("HR", "Rohan Mehta"),
    ("Finance", "Kavita Nair"),
    ("Marketing", "Aditya Rao"),
    ("Sales", "Neha Kapoor"),
    ("Operations", "Sanjay Verma"),
]

JOB_TITLES = {
    "IT": ["Software Developer", "Frontend Developer", "Backend Developer", "QA Engineer",
           "DevOps Engineer", "IT Support Specialist", "Systems Analyst", "Engineering Manager"],
    "HR": ["HR Executive", "HR Generalist", "Talent Acquisition Specialist", "HR Manager", "HR Business Partner"],
    "Finance": ["Accountant", "Financial Analyst", "Finance Manager", "Accounts Payable Specialist", "Auditor"],
    "Marketing": ["Marketing Executive", "Content Strategist", "SEO Specialist", "Brand Manager", "Marketing Manager"],
    "Sales": ["Sales Executive", "Account Manager", "Business Development Executive", "Sales Manager", "Sales Associate"],
    "Operations": ["Operations Executive", "Operations Manager", "Logistics Coordinator", "Process Analyst"],
}

LOCATIONS = ["Bengaluru", "Mumbai", "Delhi", "Hyderabad", "Pune", "Chennai", "Remote"]
EMPLOYMENT_TYPES = ["Full-Time", "Full-Time", "Full-Time", "Contract", "Part-Time", "Intern"]
EXIT_REASONS = ["Better Opportunity", "Salary", "Career Growth", "Work Environment", "Relocation", "Personal Reasons"]
LEAVE_TYPES = ["Casual Leave", "Sick Leave", "Earned Leave", "Emergency Leave"]

SALARY_RANGES = {
    "IT": (45000, 130000),
    "HR": (32000, 85000),
    "Finance": (35000, 95000),
    "Marketing": (30000, 90000),
    "Sales": (28000, 100000),
    "Operations": (26000, 75000),
}


def clear_data():
    print("Clearing existing data...")
    Notification.query.delete()
    SalaryRecord.query.delete()
    PerformanceReview.query.delete()
    LeaveRequest.query.delete()
    Attendance.query.delete()
    Employee.query.delete()
    Department.query.delete()
    User.query.delete()
    CompanySettings.query.delete()
    db.session.commit()


def seed_departments():
    print("Seeding departments...")
    depts = {}
    for name, manager in DEPARTMENTS:
        d = Department(name=name, manager_name=manager, status="Active")
        db.session.add(d)
        depts[name] = d
    db.session.commit()
    return depts


def seed_users(depts):
    print("Seeding demo user accounts...")
    accounts = [
        ("Sachin Yadav", "admin@hranalytics.com", "Admin@123", "ADMIN"),
        ("Priya Iyer", "hr@hranalytics.com", "HR@123", "HR"),
        ("Karan Malhotra", "manager@hranalytics.com", "Manager@123", "MANAGER"),
        ("Divya Menon", "employee@hranalytics.com", "Employee@123", "EMPLOYEE"),
    ]
    for name, email, pwd, role in accounts:
        # Demo accounts use their published password directly (no forced
        # change) so the credentials in the README work as documented.
        # Accounts created later through User Management always force a
        # password change on first login — see routes/users.py.
        u = User(name=name, email=email, role=role, status="Active", must_change_password=False)
        u.set_password(pwd)
        db.session.add(u)
    db.session.commit()


def random_date_between(start, end):
    delta = (end - start).days
    return start + timedelta(days=random.randint(0, max(delta, 0)))


def seed_employees(depts, count=180):
    print(f"Seeding {count} employees...")
    employees = []
    today = date.today()
    used_emails = set()

    for i in range(count):
        dept_name = random.choice(list(depts.keys()))
        dept = depts[dept_name]
        gender = random.choice(["Male", "Female", "Female", "Male", "Other"])
        first = fake.first_name_male() if gender == "Male" else (
            fake.first_name_female() if gender == "Female" else fake.first_name())
        last = fake.last_name()

        email = f"{first.lower()}.{last.lower()}{i}@hranalytics.com"
        while email in used_emails:
            email = f"{first.lower()}.{last.lower()}{random.randint(1,9999)}@hranalytics.com"
        used_emails.add(email)

        dob = fake.date_of_birth(minimum_age=22, maximum_age=58)
        joining_date = random_date_between(today - timedelta(days=365 * 6), today - timedelta(days=10))
        exp_years = round(random.uniform(0.5, 20), 1)
        salary_low, salary_high = SALARY_RANGES[dept_name]
        salary = round(random.uniform(salary_low, salary_high), -2)

        # ~12% of employees have left the company (for attrition analysis)
        is_leaver = random.random() < 0.12
        if is_leaver:
            exit_date = random_date_between(joining_date + timedelta(days=60), today)
            status = random.choice(["Resigned", "Resigned", "Resigned", "Terminated"])
            exit_reason = random.choice(EXIT_REASONS)
        else:
            exit_date = None
            exit_reason = None
            status = random.choices(
                ["Active", "Active", "Active", "Active", "On Leave", "Inactive"],
                weights=[70, 70, 70, 70, 10, 5], k=1
            )[0]

        employee = Employee(
            employee_code=f"EMP{1000 + i}",
            first_name=first, last_name=last, email=email,
            phone=fake.phone_number()[:20],
            date_of_birth=dob, gender=gender,
            address=fake.address().replace("\n", ", ")[:200],
            emergency_contact=f"{fake.name()} - {fake.phone_number()[:15]}",
            department_id=dept.id,
            job_title=random.choice(JOB_TITLES[dept_name]),
            manager_name=dept.manager_name,
            joining_date=joining_date,
            employment_type=random.choice(EMPLOYMENT_TYPES),
            location=random.choice(LOCATIONS),
            status=status,
            salary=salary,
            experience_years=exp_years,
            skills=", ".join(fake.words(nb=4)),
            exit_date=exit_date,
            exit_reason=exit_reason,
        )
        db.session.add(employee)
        employees.append(employee)

    db.session.commit()
    return employees


def seed_attendance(employees, days=90):
    print("Seeding attendance history (last 90 business days)...")
    today = date.today()
    day_cursor = today - timedelta(days=days)
    business_days = []
    while day_cursor <= today:
        if day_cursor.weekday() < 5:  # Mon-Fri
            business_days.append(day_cursor)
        day_cursor += timedelta(days=1)

    batch = []
    for emp in employees:
        if emp.status == "Inactive":
            continue
        for d in business_days:
            if d < emp.joining_date:
                continue
            # Leavers only have attendance up to their exit date — this keeps
            # the data realistic while still giving the ML model usable
            # history for employees who have left.
            if emp.exit_date and d > emp.exit_date:
                continue
            if random.random() < 0.06:
                continue  # skip some days as "unmarked"
            roll = random.random()
            # Employees who eventually left tend to have somewhat worse
            # attendance in their final months — a realistic signal rather
            # than a giveaway.
            if emp.exit_date:
                if roll < 0.78:
                    s = "Present"
                elif roll < 0.87:
                    s = "Late"
                elif roll < 0.95:
                    s = "Absent"
                else:
                    s = "Leave"
            else:
                if roll < 0.86:
                    s = "Present"
                elif roll < 0.92:
                    s = "Late"
                elif roll < 0.97:
                    s = "Absent"
                else:
                    s = "Leave"
            check_in = "09:%02d" % random.randint(0, 45) if s in ("Present", "Late") else None
            check_out = "18:%02d" % random.randint(0, 45) if s in ("Present", "Late") else None
            batch.append(Attendance(employee_id=emp.id, date=d, status=s,
                                     check_in=check_in, check_out=check_out))
            if len(batch) >= 2000:
                db.session.bulk_save_objects(batch)
                db.session.commit()
                batch = []
    if batch:
        db.session.bulk_save_objects(batch)
        db.session.commit()


def seed_leave(employees):
    print("Seeding leave requests...")
    today = date.today()
    for emp in random.sample(employees, k=min(90, len(employees))):
        for _ in range(random.randint(1, 3)):
            start = random_date_between(max(emp.joining_date, today - timedelta(days=180)), today)
            length = random.randint(1, 5)
            end = start + timedelta(days=length - 1)
            status = random.choices(["Approved", "Pending", "Rejected"], weights=[70, 20, 10], k=1)[0]
            leave = LeaveRequest(
                employee_id=emp.id, leave_type=random.choice(LEAVE_TYPES),
                start_date=start, end_date=end,
                reason=random.choice(["Family function", "Not feeling well", "Personal work",
                                       "Travel", "Medical appointment"]),
                status=status,
                applied_on=datetime.combine(start - timedelta(days=random.randint(1, 5)), datetime.min.time()),
                decided_by="Priya Iyer" if status != "Pending" else None,
            )
            db.session.add(leave)
    db.session.commit()


def seed_performance(employees):
    print("Seeding performance reviews...")
    for emp in employees:
        num_reviews = random.randint(0, 3)
        review_date = emp.joining_date + timedelta(days=180)
        for _ in range(num_reviews):
            if review_date > date.today():
                break
            # Don't create reviews dated after someone left
            if emp.exit_date and review_date > emp.exit_date:
                break
            # Employees who left tend to score slightly lower on average —
            # a realistic pattern, not a perfect giveaway.
            if emp.exit_date:
                scores = [random.randint(1, 4) for _ in range(5)]
            else:
                scores = [random.randint(2, 5) for _ in range(5)]
            overall = round(sum(scores) / len(scores), 1)
            db.session.add(PerformanceReview(
                employee_id=emp.id, review_date=review_date, reviewer=emp.manager_name,
                overall_rating=overall,
                technical_skills=scores[0], communication=scores[1], teamwork=scores[2],
                leadership=scores[3], problem_solving=scores[4],
                goals="Improve process efficiency and mentor junior team members.",
                comments=random.choice([
                    "Consistently meets expectations and shows strong initiative.",
                    "Good progress this cycle; needs to improve on deadlines.",
                    "Excellent collaboration and communication with the team.",
                    "Solid technical contributions this period.",
                ]),
            ))
            review_date += timedelta(days=180)
    db.session.commit()


def seed_salary_history(employees):
    print("Seeding salary history...")
    for emp in employees:
        db.session.add(SalaryRecord(
            employee_id=emp.id, base_salary=emp.salary,
            bonus=round(emp.salary * random.choice([0, 0, 0.05, 0.1]), 2),
            deduction=round(emp.salary * 0.02, 2),
            effective_date=emp.joining_date,
        ))
        if random.random() < 0.3:
            new_salary = round(emp.salary * random.uniform(1.05, 1.2), -2)
            db.session.add(SalaryRecord(
                employee_id=emp.id, base_salary=new_salary,
                bonus=round(new_salary * random.choice([0, 0.05, 0.1]), 2),
                deduction=round(new_salary * 0.02, 2),
                effective_date=emp.joining_date + timedelta(days=365),
            ))
    db.session.commit()


def seed_notifications():
    print("Seeding sample notifications...")
    messages = [
        ("New leave request from an employee", "leave"),
        ("Leave approved for a team member", "leave"),
        ("New employee added to IT department", "employee"),
        ("Performance review due for Q3", "performance"),
    ]
    for msg, cat in messages:
        db.session.add(Notification(message=msg, category=cat))
    db.session.commit()


def run_seed(clear_first=True):
    """The actual seeding logic, assuming an app context is ALREADY pushed
    by the caller. Used both by the CLI entrypoint below and by app.py's
    auto-seed-if-empty startup check (important on hosts like Render's free
    tier, where there's no Shell access to run this script manually and the
    SQLite file is wiped on every restart)."""
    db.create_all()
    if clear_first:
        clear_data()
    depts = seed_departments()
    seed_users(depts)
    employees = seed_employees(depts, count=180)
    seed_attendance(employees)
    seed_leave(employees)
    seed_performance(employees)
    seed_salary_history(employees)
    seed_notifications()
    CompanySettings.get()

    print("\nDone! Summary:")
    print(f"  Departments: {Department.query.count()}")
    print(f"  Employees:   {Employee.query.count()}")
    print(f"  Attendance:  {Attendance.query.count()}")
    print(f"  Leave reqs:  {LeaveRequest.query.count()}")
    print(f"  Reviews:     {PerformanceReview.query.count()}")
    print(f"  Salary recs: {SalaryRecord.query.count()}")
    print(f"  Users:       {User.query.count()}")


def main():
    """CLI entrypoint: `python data/seed_data.py`. Creates its own app +
    app context, then always clears and reseeds — safe to run manually as
    many times as you like during development."""
    app = create_app()
    with app.app_context():
        run_seed(clear_first=True)


if __name__ == "__main__":
    main()

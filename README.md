# HR Analytics & Employee Management System

A full-stack HR Management & Analytics web application built with **Flask**,
**SQLAlchemy**, and **Pandas**. It's a working product, not a mockup — every
button, form, chart, and export in this app is backed by real database
operations and live calculations.

Built as a portfolio project to demonstrate both **Python/Flask development**
skills (auth, CRUD, database design, deployment) and **data analyst** skills
(Pandas-driven KPIs, attrition analysis, business insights, reporting).

---

## What's New in v2

This release adds a profile-picture system, a standalone CSV/Excel analytics
pipeline, and an HR intelligence layer — all on top of the original app,
with existing data and features preserved.

### Employee Profile Pictures
- Upload / replace / remove photos (ADMIN & HR only), shown across employee
  lists, profiles, dashboard, attendance, leave, performance and payroll
- Deterministic initials avatar fallback (same person always gets the same
  color) when no photo exists, plus an automatic fallback if an image 404s
- Security: extension allowlist (JPG/JPEG/PNG/WebP), 3 MB per-file limit,
  20 MB global request cap, `secure_filename` + UUID naming, and a
  resolved-path containment check against path traversal

### CSV / Excel Dataset Analytics (`Data Analytics` in the sidebar)
Uploaded files are analyzed as **separate analytical datasets** and never
write to the production HR tables.
- **Upload** — drag & drop or browse, with client-side type/size validation
  and loading/error states; files stored under `instance/uploads/datasets/`
  (outside the public static folder)
- **Automatic column detection** — recognizes common header variations
  (`emp_code`, `annual_income`, `date_joined`, `sex`, `rating`, …). Anything
  matched only by a substring is marked *uncertain* and sent to a manual
  mapping screen rather than being silently guessed
- **Data quality report** — rows/columns, duplicate rows, duplicate and
  missing employee IDs, missing values by column, empty columns, unparseable
  dates, negative salaries, implausible ages, unknown statuses, and exit
  dates before joining dates
- **Cleaning pipeline** — produces a new cleaned DataFrame (the uploaded file
  is never modified): trims whitespace, standardizes categoricals (preserving
  acronyms like IT/HR/QA), parses dates, coerces numerics, invalidates
  impossible values, and derives `age_group`, `tenure_years`, `tenure_group`,
  `salary_band`, `is_leaver`
- **Insights dashboard** — KPIs, workforce/attrition/salary/performance/
  attendance charts and auto-generated business insights. Metrics whose
  source column is absent render as *"Not available"* rather than a fabricated
  number
- **Compare with Main HR Dataset** — side-by-side KPI and distribution
  comparison, with both sources clearly labeled
- **Exports** — cleaned data, KPI summary, data-quality report and insights
  as CSV or Excel

### HR Intelligence
- **Salary benchmarking** on the employee profile: salary vs department
  average and vs job-title average (with peer count), labeled
  *Below / Around / Above average* in neutral language
- **Smart HR Alerts** — high-attrition departments, attendance below
  threshold, low performance ratings, high leave usage, upcoming probation
  completions, and z-score salary outliers. Thresholds are configurable from
  the UI. Small groups are excluded so alerts stay statistically meaningful
- **Top Performers** — ranked by average rating, filterable by department and
  period

### Attrition Risk Prediction (machine learning)
- Trains a **Random Forest / Logistic Regression / Decision Tree** (selectable)
  on your labeled employee data and scores every current employee with a risk
  probability and HIGH / MEDIUM / LOW level
- **Refuses to run on insufficient data.** It requires at least 40 employees
  with at least 8 leavers *and* 8 stayers. Below that it shows
  *"Attrition prediction unavailable because the current dataset does not
  contain sufficient labeled data"* instead of fabricating probabilities
- **Automatic data-leakage guard**: any feature recorded for one class but
  systematically missing for the other (e.g. attendance only logged for
  current employees) is detected and excluded before training, and the
  exclusion is shown in the UI. Without this the model scores a fake 1.00
  AUC by learning *missingness* rather than real signal
- Reports honest held-out accuracy and ROC-AUC, plus contributing factors
  from feature importances — labeled as **association, not causation**
- Results are cached for 5 minutes so the model isn't retrained on every page view

### AI HR Assistant
Ask questions in plain English: *"Which department has the highest attrition?"*,
*"What is the average salary in IT?"*, *"How many pending leave requests?"*

- **Safe analytics layer**: the assistant has no database access, no SQL, and
  never sees raw employee records, passwords, password hashes or contact
  details. It can only call a fixed allowlist of aggregated metric functions
- **Role-enforced**: EMPLOYEE-role users are refused company-wide analytics
- **Works with no API key.** A built-in rule-based engine answers from the safe
  metrics layer by default. If `ANTHROPIC_API_KEY` is set, the same aggregated
  metrics (never raw records) are summarised into natural language; any failure
  silently falls back to the rule-based answer, so the app never breaks

### Employee 360° View
The employee profile now has **Risk** and **Activity** tabs alongside Personal,
Work, Attendance, Leave, Performance and Salary:
- **Risk** (ADMIN/HR/MANAGER only) — individual attrition probability with the
  same "prediction, not prophecy" framing, plus the signals behind it
- **Activity** — a timeline assembled from real records: joining, salary
  changes, performance reviews, leave, and exit

### Attrition Risk Prediction (Machine Learning)
- Trains a real scikit-learn model (Random Forest / Logistic Regression /
  Decision Tree, selectable) on your own employees who left vs stayed
- **Refuses to run** unless there's enough labeled data (≥40 employees, ≥8
  leavers and ≥8 stayers) — shows "Attrition prediction unavailable because
  the current dataset does not contain sufficient labeled data" instead of a
  fake number
- **Data-leakage guard**: automatically drops any feature that's recorded
  for one class (e.g. current employees) but almost never for the other
  (e.g. past employees), since that lets a model "cheat" instead of learning
  real signal
- Reports honest **held-out ROC-AUC / accuracy** — computed on a test split
  the model never trained on
- Shows contributing factors as feature importances (association, not
  causation) and scores only currently active employees
- Individual risk score surfaced on each employee's **360° profile**

### AI HR Assistant
- Answers natural-language questions (*"Which department has the highest
  attrition?"*, *"What is the average salary in IT?"*) from a **safe,
  aggregated metrics layer** — it has no raw database or ORM access, so
  there's no way for it to leak passwords, auth data, or individual PII
- **Role-gated**: EMPLOYEE-role users cannot query company-wide analytics
  through the assistant
- Rule-based by default (always available, no setup needed). If
  `ANTHROPIC_API_KEY` is set, the same safe metrics are optionally
  rephrased more naturally by Claude — the model only ever sees the
  pre-computed aggregate numbers, never raw records, and any failure
  silently falls back to the rule-based answer
- The assistant page itself documents exactly what it can and can't see

### Employee 360° View
Every employee profile now has **Risk** and **Activity** tabs alongside the
original Personal / Work / Attendance / Leave / Performance / Salary tabs:
- **Risk** — this employee's individual attrition-risk score (when the ML
  model is available), with the same "not a guaranteed outcome" framing
- **Activity** — a real timeline built from actual records (joining, salary
  changes, reviews, leave, exit) sorted by date, not placeholder content

### Safe schema migration
`migrate_schema.py` inspects the live database and only adds what's missing
(new columns / new tables). It never drops tables or resets data — verified
against an existing 180-employee database.

```bash
python migrate_schema.py
```

## Features

- **Authentication** — session-based login with hashed passwords (Werkzeug), "remember me", and role-based access control (RBAC)
- **4 roles** — Admin, HR, Manager, Employee, each with different permissions enforced at the route level
- **Employee management** — add / view / edit / deactivate, search, multi-field filters, pagination, tabbed profile pages (Personal, Work, Attendance, Leave, Performance, Salary)
- **Department management** — CRUD with live headcount, average salary, and attrition rate per department
- **Attendance** — daily marking (Present/Absent/Late/Half Day/Leave), monthly & department-level attendance charts
- **Leave management** — apply, approve/reject, leave balance tracking
- **Performance management** — multi-criteria reviews (technical, communication, teamwork, leadership, problem-solving), rating distribution and department comparison charts
- **Payroll / Salary** — base + bonus − deduction = net salary, salary history per employee, salary-by-department and salary-by-designation charts
- **HR Analytics** — a dedicated analytics page with filters (department, location, employment type, gender, date range) driving 10 live charts
- **Attrition analysis** — attrition rate by department, gender, age group, experience, salary range, employment type, plus exit reasons
- **Auto-generated business insights** — plain-English insights ("Sales has the highest attrition rate at 11.2%.") computed from the live dataset with Pandas — never hardcoded
- **Reports** — export Employee / Attendance / Leave / Performance / Salary / Attrition data to CSV or Excel
- **Notifications** — in-app notification feed for leave requests, new hires, reviews
- **Settings** — company info and leave policy, editable by Admin
- **Responsive UI** — collapsible sidebar, horizontally scrollable tables on mobile
- **Error handling** — custom 403/404/500 pages, duplicate email/ID validation, friendly flash messages

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11, Flask |
| Database | SQLite (dev) / PostgreSQL (production, via `DATABASE_URL`) |
| ORM | SQLAlchemy (Flask-SQLAlchemy) |
| Data analysis | Pandas, NumPy |
| Frontend | HTML5, Bootstrap 5, vanilla JS, Chart.js, Bootstrap Icons |
| Auth | Flask sessions + Werkzeug password hashing + Flask-WTF CSRF protection |
| Sample data | Faker |
| Machine learning | scikit-learn |
| File uploads | Werkzeug secure upload handling |
| Deployment | Render + Gunicorn |

No React, no Node.js — kept intentionally Python-first.

## Screenshots

_Add screenshots of your running app here before publishing, e.g.:_

```
docs/screenshots/dashboard.png
docs/screenshots/employees.png
docs/screenshots/analytics.png
```

---

## Project Structure

```
hr-analytics-dashboard/
│
├── app.py                  # Flask application factory
├── config.py                # Configuration (reads from environment variables)
├── extensions.py             # Shared db / csrf extension instances
├── auth_utils.py              # login_required / roles_required / permission_required decorators
├── analytics_engine.py         # All Pandas-based analytics & insight generation
├── requirements.txt
├── Procfile                  # Render/Gunicorn start command
├── runtime.txt                # Python version pin for Render
├── .env.example
├── .gitignore
│
├── models/                   # SQLAlchemy models
│   ├── user.py, employee.py, department.py, attendance.py,
│   ├── leave.py, performance.py, salary.py, notification.py, settings.py
│
├── routes/                   # Flask blueprints (one per module)
│   ├── auth.py, dashboard.py, employees.py, departments.py,
│   ├── attendance.py, leave.py, performance.py, payroll.py,
│   ├── analytics.py, reports.py, settings.py, notifications.py
│
├── templates/                 # Jinja2 templates (Bootstrap 5 + Chart.js)
│   ├── base.html, login.html, dashboard.html, notifications.html
│   ├── employees/, departments/, attendance/, leave/,
│   ├── performance/, payroll/, analytics/, reports/, settings/, errors/
│
├── static/
│   ├── css/style.css, js/app.js
│
├── data/
│   └── seed_data.py            # Generates 180 realistic fictional employees + history
│
└── instance/
    └── database.db              # SQLite file (created automatically, git-ignored)
```

## Database Schema

```
User ─┐ (optional link)
      └── Employee ─┬── Attendance      (1‑to‑many)
                     ├── LeaveRequest    (1‑to‑many)
                     ├── PerformanceReview (1‑to‑many)
                     └── SalaryRecord    (1‑to‑many)

Department ── Employee   (1‑to‑many)
```

All child records use `ON DELETE CASCADE` semantics at the ORM level, but
employees are **deactivated**, never deleted, so historical analytics stay
correct.

---

## Local Setup

### 1. Prerequisites
- Python 3.11+
- pip

### 2. Clone and install

```bash
git clone https://github.com/<your-username>/hr-analytics-dashboard.git
cd hr-analytics-dashboard

python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
# then open .env and set SECRET_KEY to a random string, e.g.:
python -c "import secrets; print(secrets.token_hex(32))"
```

### 4. Initialize and seed the database

The database and tables are created automatically the first time the app
runs. To populate it with realistic sample data (180 employees across 6
departments, attendance, leave, performance and salary history):

```bash
python data/seed_data.py
```

You'll see a summary of how many records were created. Re-running this
script wipes and regenerates all data — safe to run as many times as you
like during development.

### 5. Run the app

```bash
python app.py
```

Visit **http://127.0.0.1:5000**.

### Demo Credentials

| Role | Email | Password |
|---|---|---|
| Admin | admin@hranalytics.com | Admin@123 |
| HR | hr@hranalytics.com | HR@123 |
| Manager | manager@hranalytics.com | Manager@123 |
| Employee | employee@hranalytics.com | Employee@123 |

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `SECRET_KEY` | Yes | Signs session cookies. Use a long random string in production. |
| `DATABASE_URL` | No (local) / Yes (production) | Postgres connection string. If unset, the app uses local SQLite at `instance/database.db`. |
| `ANTHROPIC_API_KEY` | No | Optional. Enables natural-language answers in the HR Assistant. Without it the assistant runs in rule-based mode and everything else works normally. |

---

## Deployment to Render

### Push to GitHub

```bash
git init
git add .
git commit -m "Initial commit: HR Analytics & Employee Management System"
git branch -M main
git remote add origin https://github.com/<your-username>/hr-analytics-dashboard.git
git push -u origin main
```

### Create the Render Web Service

1. Go to **https://dashboard.render.com** → **New** → **Web Service**.
2. Connect your GitHub account and select the `hr-analytics-dashboard` repository.
3. Configure:
   - **Environment**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app`
4. Add environment variables under **Environment**:
   - `SECRET_KEY` = (generate a random string)
   - `DATABASE_URL` = (see below)
5. Click **Create Web Service** and wait for the build to finish.

### Database on Render

SQLite works locally but Render's filesystem is ephemeral, so data would be
lost on every deploy/restart. For a persistent deployment:

1. In Render, create a **PostgreSQL** instance (Render → New → PostgreSQL).
2. Copy its **Internal Database URL**.
3. Set it as the `DATABASE_URL` environment variable on your Web Service.
4. The app automatically detects `DATABASE_URL` and switches from SQLite to
   Postgres (see `config.py`) — no code changes needed.
5. After the first deploy, seed the production database once via Render's
   **Shell** tab:
   ```bash
   python data/seed_data.py
   ```

### Verify

Once deployed, open the Render-provided URL (e.g.
`https://hr-analytics-dashboard.onrender.com`) and log in with the demo
credentials above.

---

## Testing Checklist

The following flows have been manually verified end-to-end during
development:

- [x] Login / logout, invalid credentials, inactive-account handling
- [x] Role-based access control for all 4 roles (Admin/HR/Manager/Employee return 403 where expected)
- [x] Add / edit / deactivate employee, duplicate email & ID validation
- [x] Search and multi-field filters on the Employees page, pagination
- [x] Department CRUD with live headcount/salary/attrition
- [x] Mark attendance, attendance rate calculation
- [x] Apply / approve / reject leave requests
- [x] Add performance review, rating distribution charts
- [x] Add salary record, payroll analytics charts
- [x] Analytics page filters recompute all 10 charts + insights
- [x] Attrition deep-dive breakdowns
- [x] CSV and Excel export for all 6 report types
- [x] Dashboard KPIs and charts computed live from the database (never hardcoded)
- [x] Responsive layout on mobile widths
- [x] 403 / 404 / 500 error pages

---

## Implemented Features (Summary)

Auth & RBAC · Dashboard with live KPIs & 6 charts · Employee CRUD + profile
tabs · Department CRUD · Attendance marking & analytics · Leave
apply/approve/reject · Performance reviews & analytics · Payroll/salary
tracking · HR Analytics page with filters & 10 charts · Auto-generated
business insights · Attrition deep-dive (7 breakdowns + reasons) · CSV/Excel
report export · Notifications · Company & leave-policy settings · 150–250
seeded employees with realistic history.

## Known Limitations

- **PDF export** is not implemented (CSV and Excel are). PDF libraries are the
  most common cause of build failures on Render's free tier, so it was left out
  deliberately rather than shipped fragile.
- **Attrition prediction quality depends on your data.** With the seeded demo
  data it reaches ~0.92 ROC-AUC, but a real deployment needs attendance and
  performance history recorded for *past* employees too, or those features get
  excluded by the leakage guard.
- **The AI Assistant's rule-based mode** matches intents by keyword. It answers
  the documented question types well but is not a general-purpose chatbot.
- **Uploaded datasets are analyzed in-request.** Very large files (near the
  15 MB limit) will make the insights page slower; there is no background
  job queue.

## Future Improvements

- PDF export for reports
- Email notifications (leave approvals, review reminders) via an SMTP provider
- Org-chart visualization for manager relationships
- Bulk employee import via CSV upload
- Two-factor authentication for Admin accounts
- Audit log of who changed what and when
- Dark mode

---

## License

This project is provided as a portfolio/learning template. Use and modify
freely. All sample data is fictional.

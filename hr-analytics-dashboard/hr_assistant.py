"""
hr_assistant.py
----------------
A question-answering assistant over HR analytics.

SECURITY MODEL (important):
  - The assistant NEVER receives raw database access, raw SQL, or full
    employee records.
  - It can only call functions in SAFE_METRICS below, each of which returns
    an aggregated, non-sensitive value.
  - Passwords, password hashes, session data, email addresses and personal
    contact details are never exposed to it.
  - Role permissions are enforced before any metric is computed: an
    EMPLOYEE-role user cannot pull company-wide analytics.

It works in two modes:
  1. Rule-based (default, always available, no API key needed) — matches the
     question against known intents and answers from the safe metrics layer.
  2. LLM-assisted (optional) — if ANTHROPIC_API_KEY is set, the same safe
     metrics are summarised into natural language by the model. The model
     still only ever sees the aggregated metrics, never raw records.

If no API key is configured, mode 1 is used and the rest of the app is
completely unaffected.
"""
import os
import re

from sqlalchemy import func

from extensions import db
from models import Employee, Department, Attendance, LeaveRequest, PerformanceReview
import analytics_engine as ae
import hr_intelligence as hi


# ---------------------------------------------------------------------------
# SAFE METRICS LAYER — the ONLY data the assistant can reach.
# ---------------------------------------------------------------------------

def _headcount():
    total = Employee.query.count()
    active = Employee.query.filter_by(status="Active").count()
    return {"total_employees": total, "active_employees": active}


def _attrition_overall():
    df = ae.employees_dataframe()
    k = ae.kpi_summary(df)
    return {"attrition_rate_pct": k["attrition_rate"]}


def _attrition_by_department():
    out = {}
    for dept in Department.query.all():
        total = dept.employees.count()
        if total == 0:
            continue
        leavers = dept.employees.filter(Employee.status.in_(["Resigned", "Terminated"])).count()
        out[dept.name] = round(leavers / total * 100, 1)
    return out


def _average_salary(department=None):
    q = db.session.query(func.avg(Employee.salary)).filter(
        Employee.salary > 0, Employee.status.notin_(["Resigned", "Terminated"]))
    if department:
        q = q.join(Department, Employee.department_id == Department.id).filter(
            Department.name.ilike(department))
    val = q.scalar()
    return {"average_salary": round(float(val), 0) if val else None,
            "department": department}


def _headcount_by_department():
    out = {}
    for dept in Department.query.all():
        out[dept.name] = dept.employees.filter(
            Employee.status.notin_(["Resigned", "Terminated"])).count()
    return out


def _attendance_by_department():
    data = ae.department_attendance()
    return dict(zip(data["labels"], data["data"])) if data["labels"] else {}


def _average_performance(department=None):
    q = db.session.query(func.avg(PerformanceReview.overall_rating)).join(
        Employee, PerformanceReview.employee_id == Employee.id)
    if department:
        q = q.join(Department, Employee.department_id == Department.id).filter(
            Department.name.ilike(department))
    val = q.scalar()
    return {"average_performance": round(float(val), 2) if val else None,
            "department": department}


def _leave_summary():
    return {
        "pending": LeaveRequest.query.filter_by(status="Pending").count(),
        "approved": LeaveRequest.query.filter_by(status="Approved").count(),
        "rejected": LeaveRequest.query.filter_by(status="Rejected").count(),
    }


def _gender_distribution():
    df = ae.employees_dataframe()
    data = ae.gender_distribution(df)
    return dict(zip(data["labels"], data["data"])) if data["labels"] else {}


def _alerts_summary():
    alerts = hi.generate_alerts()
    return [{"level": a["level"], "category": a["category"], "message": a["message"]}
            for a in alerts]


SAFE_METRICS = {
    "headcount": _headcount,
    "attrition_overall": _attrition_overall,
    "attrition_by_department": _attrition_by_department,
    "average_salary": _average_salary,
    "headcount_by_department": _headcount_by_department,
    "attendance_by_department": _attendance_by_department,
    "average_performance": _average_performance,
    "leave_summary": _leave_summary,
    "gender_distribution": _gender_distribution,
    "alerts": _alerts_summary,
}

# Roles allowed to query company-wide analytics through the assistant.
ANALYTICS_ROLES = {"ADMIN", "HR"}
LIMITED_ROLES = {"MANAGER"}


def _extract_department(question):
    names = [d.name for d in Department.query.all()]
    for name in names:
        if re.search(rf"\b{re.escape(name.lower())}\b", question.lower()):
            return name
    return None


# ---------------------------------------------------------------------------
# RULE-BASED ANSWERING
# ---------------------------------------------------------------------------

def _answer_rule_based(question, role):
    q = question.lower().strip()
    dept = _extract_department(question)

    # --- attrition ---
    if "attrition" in q or "turnover" in q or "leaving" in q or "leavers" in q:
        by_dept = _attrition_by_department()
        overall = _attrition_overall()["attrition_rate_pct"]
        if "highest" in q or "worst" in q or "most" in q:
            if not by_dept:
                return "I don't have any department attrition data yet.", {}
            top = max(by_dept, key=by_dept.get)
            return (f"{top} has the highest attrition rate at {by_dept[top]}%. "
                     f"The company-wide attrition rate is {overall}%."), {"attrition_by_department": by_dept}
        if "lowest" in q or "best" in q:
            if not by_dept:
                return "I don't have any department attrition data yet.", {}
            low = min(by_dept, key=by_dept.get)
            return (f"{low} has the lowest attrition rate at {by_dept[low]}%. "
                     f"The company-wide rate is {overall}%."), {"attrition_by_department": by_dept}
        if dept and dept in by_dept:
            return f"{dept} has an attrition rate of {by_dept[dept]}%.", {"attrition_by_department": by_dept}
        listing = ", ".join(f"{k} {v}%" for k, v in sorted(by_dept.items(), key=lambda x: -x[1]))
        return (f"The overall attrition rate is {overall}%. By department: {listing}."), \
               {"attrition_by_department": by_dept}

    # --- salary ---
    if "salary" in q or "pay" in q or "compensation" in q or "paid" in q:
        if "highest" in q or "most" in q:
            avgs = {}
            for d in Department.query.all():
                v = _average_salary(d.name)["average_salary"]
                if v:
                    avgs[d.name] = v
            if not avgs:
                return "I don't have salary data available.", {}
            top = max(avgs, key=avgs.get)
            return f"{top} has the highest average salary at ₹{avgs[top]:,.0f}.", {"average_salary_by_department": avgs}
        result = _average_salary(dept)
        if result["average_salary"] is None:
            return (f"I don't have salary data for {dept}." if dept
                     else "I don't have salary data available."), {}
        scope = f"in {dept}" if dept else "across the company"
        return f"The average salary {scope} is ₹{result['average_salary']:,.0f}.", {"average_salary": result}

    # --- attendance ---
    if "attendance" in q or "absent" in q or "present" in q:
        by_dept = _attendance_by_department()
        if not by_dept:
            return "I don't have attendance data recorded yet.", {}
        if "lowest" in q or "worst" in q:
            low = min(by_dept, key=by_dept.get)
            return f"{low} has the lowest attendance rate at {by_dept[low]}%.", {"attendance_by_department": by_dept}
        if "highest" in q or "best" in q:
            top = max(by_dept, key=by_dept.get)
            return f"{top} has the highest attendance rate at {by_dept[top]}%.", {"attendance_by_department": by_dept}
        if dept and dept in by_dept:
            return f"{dept} has an attendance rate of {by_dept[dept]}%.", {"attendance_by_department": by_dept}
        overall = ae.attendance_rate_overall()
        return f"The overall attendance rate is {overall}%.", {"attendance_by_department": by_dept}

    # --- performance ---
    if "performance" in q or "rating" in q or "top performer" in q:
        result = _average_performance(dept)
        if result["average_performance"] is None:
            return "I don't have performance review data available.", {}
        scope = f"in {dept}" if dept else "across the company"
        return f"The average performance rating {scope} is {result['average_performance']}/5.", \
               {"average_performance": result}

    # --- leave (checked before headcount so "how many leave requests" works) ---
    if "leave" in q or "vacation" in q or "time off" in q:
        ls = _leave_summary()
        return (f"There are {ls['pending']} pending leave requests, "
                 f"{ls['approved']} approved and {ls['rejected']} rejected."), {"leave_summary": ls}

    # --- headcount ---
    if "how many" in q or "headcount" in q or "employees" in q or "active" in q or "staff" in q:
        hc = _headcount()
        if dept:
            by_dept = _headcount_by_department()
            if dept in by_dept:
                return f"{dept} has {by_dept[dept]} active employees.", {"headcount_by_department": by_dept}
        if "department" in q:
            by_dept = _headcount_by_department()
            listing = ", ".join(f"{k}: {v}" for k, v in sorted(by_dept.items(), key=lambda x: -x[1]))
            return f"Headcount by department — {listing}.", {"headcount_by_department": by_dept}
        return (f"There are {hc['total_employees']} employees in total, "
                 f"{hc['active_employees']} of whom are currently active."), {"headcount": hc}

    # --- gender ---
    if "gender" in q or "diversity" in q or "male" in q or "female" in q:
        gd = _gender_distribution()
        if not gd:
            return "I don't have gender data available.", {}
        total = sum(gd.values())
        parts = ", ".join(f"{k}: {v} ({v/total*100:.0f}%)" for k, v in gd.items())
        return f"Gender distribution — {parts}.", {"gender_distribution": gd}

    # --- alerts / summary ---
    if "alert" in q or "risk" in q or "problem" in q or "concern" in q or "summar" in q:
        alerts = _alerts_summary()
        warnings = [a for a in alerts if a["level"] == "warning"]
        if not warnings:
            return "There are currently no warning-level HR alerts.", {"alerts": alerts}
        listing = " ".join(a["message"] for a in warnings[:3])
        return f"There are {len(warnings)} active warnings. {listing}", {"alerts": alerts}

    return (
        "I can answer questions about headcount, attrition, salary, attendance, "
        "performance, leave, gender distribution and active HR alerts. "
        "For example: \"Which department has the highest attrition?\" or "
        "\"What is the average salary in IT?\"",
        {},
    )


# ---------------------------------------------------------------------------
# OPTIONAL LLM LAYER
# ---------------------------------------------------------------------------

def llm_configured():
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _answer_with_llm(question, metrics_context, role):
    """Sends ONLY the aggregated metrics (never raw records) to the model."""
    try:
        import json
        import urllib.request

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        system_prompt = (
            "You are an HR analytics assistant. Answer the user's question using ONLY "
            "the aggregated metrics provided. Never invent numbers. If the metrics do "
            "not contain the answer, say so plainly. Keep the answer to 1-3 sentences. "
            "These are aggregated company metrics; do not speculate about individuals."
        )
        payload = {
            "model": "claude-sonnet-4-6",
            "max_tokens": 400,
            "system": system_prompt,
            "messages": [{
                "role": "user",
                "content": f"Question: {question}\n\nAvailable metrics (JSON):\n"
                            f"{json.dumps(metrics_context, default=str)}",
            }],
        }
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=json.dumps(payload).encode(),
            headers={
                "content-type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        text = "".join(block.get("text", "") for block in data.get("content", [])
                        if block.get("type") == "text")
        return text.strip() or None
    except Exception:
        # Any failure silently falls back to the rule-based answer so the
        # feature never breaks the app.
        return None


# ---------------------------------------------------------------------------
# PUBLIC ENTRY POINT
# ---------------------------------------------------------------------------

def ask(question, role):
    """Returns {answer, mode, metrics, allowed}."""
    if not question or not question.strip():
        return {"answer": "Please enter a question.", "mode": "rule-based",
                "metrics": {}, "allowed": True}

    if role not in ANALYTICS_ROLES and role not in LIMITED_ROLES:
        return {
            "answer": ("You don't have permission to query company-wide HR analytics. "
                        "Please contact your HR administrator."),
            "mode": "blocked", "metrics": {}, "allowed": False,
        }

    answer, metrics = _answer_rule_based(question, role)
    mode = "rule-based"

    if llm_configured() and metrics:
        llm_answer = _answer_with_llm(question, metrics, role)
        if llm_answer:
            answer, mode = llm_answer, "ai-assisted"

    return {"answer": answer, "mode": mode, "metrics": metrics, "allowed": True}


SUGGESTED_QUESTIONS = [
    "Which department has the highest attrition?",
    "What is the average salary in IT?",
    "How many employees are active?",
    "Which department has the lowest attendance?",
    "Summarize the main HR risks right now.",
    "What is the gender distribution?",
]

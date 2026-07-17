"""
Adapter: HR schema description + read-only SQL execution.

Shared by both the ask_analytics agent (which generates SQL) and the
get_db_schema / run_db_query tools. Keeps the schema text in ONE place.
"""
import re

import config  # MUST be first — loads .env and builds the shared engine

_engine = config.engine

SCHEMA_FOR_CLAUDE = """
DATABASE: hr_db  |  MySQL 8.4  |  HR analytics (employees, attendance, payroll, performance, attrition)
Coverage: 100 employees (88 Active / 12 Inactive). Monthly facts Jan–Jun 2026. Performance: one period 'H1 2026'.
CURRENCY: Indian Rupees (INR). Display with ₹ and Indian grouping, e.g. ₹2,64,947.

!! READ FIRST — pitfalls specific to this data !!
  MONEY IN LAKHS : employees.annual_ctc_inr_lakhs and attrition_exit.last_drawn_ctc_inr_lakhs are in LAKHS
                   (1 lakh = 100000). Multiply by 100000 for rupees. payroll.* columns are already in rupees.
  MONTH SORTING  : `month` is text like 'Jan-2026'. Sort chronologically with:
                   ORDER BY STR_TO_DATE(CONCAT('01-', month), '%d-%b-%Y')
  AGE / TENURE   : employees.age and tenure_years are snapshot values; date_of_birth / date_of_joining are truth.
  ATTRITION SET  : the 12 rows in attrition_exit are exactly the 12 employees with employment_status='Inactive'.
  COVERAGE       : attendance_leave and payroll cover 90 of the 100 employees, each × 6 months = 540 rows.

TABLE employees  — 100 rows, 1 per employee (the hub)
  employee_id          VARCHAR  PK
  full_name, gender, date_of_birth DATE, age INT, date_of_joining DATE, tenure_years DECIMAL
  department, designation, band, location_city, location_state, site_type
  employment_type, highest_education, marital_status
  annual_ctc_inr_lakhs DECIMAL  (LAKHS)
  email
  reporting_manager_id VARCHAR  -> employees.employee_id (self-join for org chart; NULL = top of org, 8 rows)
  employment_status    'Active' | 'Inactive'

TABLE attendance_leave  — 540 rows, grain = employee × month
  employee_id VARCHAR -> employees.employee_id
  month VARCHAR 'Mon-YYYY'
  working_days, days_present, casual_leave_taken, sick_leave_taken, earned_leave_taken,
  leave_without_pay, late_marks, work_from_home_days   (INT, days)
  overtime_hours DECIMAL
  PK (employee_id, month)

TABLE payroll  — 540 rows, grain = employee × month   (all amounts in RUPEES, INT)
  employee_id VARCHAR -> employees.employee_id
  month VARCHAR 'Mon-YYYY'
  basic_pay, hra, special_allowance, conveyance_allowance, medical_allowance,
  gross_pay, pf_deduction, professional_tax, income_tax_tds, total_deductions,
  incentive_bonus, overtime_pay, net_pay
  PK (employee_id, month)

TABLE performance_reviews  — 100 rows, grain = employee × review_period
  employee_id VARCHAR -> employees.employee_id
  review_period VARCHAR 'H1 2026'
  kra_achievement_pct DECIMAL, overall_rating DECIMAL (1.0–5.0), rating_label,
  potential_rating ('Low'|'Medium'|'High'), promotion_recommended ('Yes'|'No'),
  training_hours_completed INT, manager_feedback_score DECIMAL
  PK (employee_id, review_period)

TABLE attrition_exit  — 12 rows, grain = one exit event per employee
  employee_id VARCHAR PK -> employees.employee_id
  full_name, department, location_city, band          (denormalized snapshot copied from employees)
  date_of_joining DATE, exit_date DATE, tenure_months DECIMAL
  exit_type ('Voluntary'|'Involuntary'), reason_for_exit
  last_drawn_ctc_inr_lakhs DECIMAL  (LAKHS)
  last_performance_rating DECIMAL, notice_period_served, rehire_eligible ('Yes'|'No'),
  exit_interview_score DECIMAL

JOIN KEYS:
  attendance_leave.employee_id    -> employees.employee_id
  payroll.employee_id             -> employees.employee_id
  performance_reviews.employee_id -> employees.employee_id
  attrition_exit.employee_id      -> employees.employee_id
  employees.reporting_manager_id  -> employees.employee_id            (org hierarchy)
  attendance_leave <-> payroll    joined on (employee_id, month)      (same grain)

QUERY TIPS:
  "attrition rate" means exits / headcount (a PERCENTAGE), NOT a raw count of exits:
     SELECT e.department,
            COUNT(DISTINCT x.employee_id) AS exits,
            COUNT(DISTINCT e.employee_id) AS headcount,
            ROUND(100*COUNT(DISTINCT x.employee_id)/COUNT(DISTINCT e.employee_id),1) AS attrition_pct
     FROM employees e LEFT JOIN attrition_exit x ON x.employee_id=e.employee_id
     GROUP BY e.department ORDER BY attrition_pct DESC;
  Regretted attrition: attrition_exit rows with high last_performance_rating (e.g. >= 4).
  Total CTC in rupees: SUM(annual_ctc_inr_lakhs) * 100000.
"""

_BLOCKED = re.compile(
    r"^\s*(INSERT|UPDATE|DELETE|DROP|TRUNCATE|ALTER|CREATE|REPLACE|GRANT|REVOKE|EXEC|EXECUTE|CALL|MERGE)\b",
    re.IGNORECASE,
)

MAX_ROWS = 500


def get_schema() -> dict:
    return {"schema": SCHEMA_FOR_CLAUDE.strip()}


def run_query(sql: str) -> dict:
    """Execute a read-only SELECT/WITH query. Returns columns, rows, row_count, truncated, error."""
    sql_stripped = (sql or "").strip().rstrip(";")

    # reject anything whose leading keyword is a write/DDL (functions like REPLACE() mid-query are fine)
    if _BLOCKED.match(sql_stripped):
        return {"error": "Only read-only SELECT queries are allowed.",
                "columns": [], "rows": [], "row_count": 0, "truncated": False}

    upper = sql_stripped.upper()
    if not (upper.startswith("SELECT") or upper.startswith("WITH")):
        return {"error": "Query must start with SELECT or WITH.",
                "columns": [], "rows": [], "row_count": 0, "truncated": False}

    try:
        import sqlalchemy as sa
        import datetime
        import decimal

        def _serialise(v):
            if isinstance(v, decimal.Decimal):
                return float(v)
            if isinstance(v, (datetime.date, datetime.datetime)):
                return v.isoformat()
            return v

        with _engine.connect() as conn:
            result = conn.execute(sa.text(sql_stripped))
            columns = list(result.keys())
            raw = result.fetchall()
            rows = [{k: _serialise(v) for k, v in zip(columns, row)} for row in raw]

        return {
            "columns":   columns,
            "rows":      rows[:MAX_ROWS],
            "row_count": len(rows),
            "truncated": len(rows) > MAX_ROWS,
            "error":     None,
        }
    except Exception as exc:
        msg = str(exc)
        m = re.search(r"\(pymysql\.err\.\w+\)\s*(.*)", msg, re.DOTALL)
        if m:
            msg = m.group(1).strip()
        return {"error": msg, "columns": [], "rows": [], "row_count": 0, "truncated": False}

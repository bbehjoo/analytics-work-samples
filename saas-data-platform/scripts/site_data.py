"""
site_data.py — every number the published site shows, read from the warehouse.

build_site.py renders these into pages. Keeping the queries here, apart from the
HTML, means each figure on the site can be traced to one SQL statement against
the dbt models.

The site builder reads the warehouse as the platform owner. It shows what each
role sees by selecting from that role's secure view, never by re-masking data
itself, so the "who sees what" table is the views' real output.
"""
import json
import os

import duckdb

HERE = os.path.dirname(os.path.abspath(__file__))
DBT_DIR = os.path.dirname(HERE)
DB_PATH = os.path.join(DBT_DIR, "warehouse.duckdb")
REPORT_PATH = os.path.join(DBT_DIR, "target", "governance_report.json")
SALT = os.environ.get("PSEUDONYM_SALT", "local-demo-salt")

ROLE_VIEWS = [  # (role, label, schema) in the order the switcher shows them
    ("hr", "HR partner", "secure_hr"),
    ("finance", "Finance", "secure_finance"),
    ("sales_manager_emea", "Sales manager, EMEA", "secure_sales_manager_emea"),
    ("analyst", "Analyst", "secure_analyst"),
]
SHOW_COLS = [  # the columns the switcher table shows: (column, label, class, policy category)
    ("employee_name", "Employee", "pii", "identity"),
    ("work_email", "Work email", "pii", "work_contact"),
    ("department", "Department", "internal", "org"),
    ("region", "Region", "internal", "org"),
    ("job_level", "Level", "confidential", "employment"),
    ("base_salary", "Base pay", "restricted", "comp"),
    ("current_leave_type", "Leave", "restricted", "health"),
    ("gender", "Gender", "restricted", "demographic"),
]


def rows(con, sql, *params):
    cur = con.execute(sql, params)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def one(con, sql, *params):
    return con.execute(sql, params).fetchone()


def money_m(v):
    return f"${v / 1e6:.1f}M"


# --------------------------------------------------------------------------- #
# Revenue
# --------------------------------------------------------------------------- #
def revenue(con):
    arr_trend = rows(con, """
        select strftime(measurement_month, '%Y-%m') as ym, round(sum(ending_arr) / 1e6, 2) as arr
        from marts.fct_arr group by 1 order by 1""")
    bridge = rows(con, """
        with mv as (
            select cast(extract(year from measurement_month) as integer) as yr,
                   sum(new_logo_arr) as new_logo, sum(cross_sell_arr + upsell_arr) as expansion,
                   sum(downgrade_arr) as downgrade, sum(churn_arr) as churn, sum(arr_change) as net_new
            from marts.fct_arr group by 1),
        ye as (
            select cast(extract(year from measurement_month) as integer) as yr, sum(ending_arr) as ending
            from marts.fct_arr
            where measurement_month in (select max(measurement_month) from marts.fct_arr
                                        group by extract(year from measurement_month))
            group by 1)
        select mv.*, ye.ending from mv join ye using (yr) order by yr""")
    nrr, grr, ending = one(con, """
        select (sum(beginning_arr)+sum(upsell_arr)+sum(cross_sell_arr)+sum(downgrade_arr)+sum(churn_arr))
                   / nullif(sum(beginning_arr), 0),
               (sum(beginning_arr)+sum(downgrade_arr)+sum(churn_arr)) / nullif(sum(beginning_arr), 0),
               (select sum(ending_arr) from marts.fct_arr
                 where measurement_month = (select max(measurement_month) from marts.fct_arr))
        from marts.fct_arr""")
    bookings_cat = rows(con, """
        select revenue_category as category, sum(acv) as acv
        from marts.fct_acv where is_closed_won and acv > 0 group by 1 order by 2 desc""")
    bookings_seg = rows(con, """
        select a.segment, sum(f.acv) as acv, count(distinct f.opportunity_id) as deals
        from marts.fct_acv f join marts.dim_account a using (account_key)
        where f.is_closed_won group by 1 order by 2 desc""")
    pipeline_acv, pipeline_n = one(con, """
        select sum(acv), count(distinct opportunity_id) from marts.fct_acv where not is_closed""")
    fy, fy_bookings = one(con, """
        select max(sales_year), sum(acv) filter (where sales_year = (select max(sales_year) from marts.fct_acv where is_closed_won))
        from marts.fct_acv where is_closed_won""")
    usage = rows(con, """
        select sum(case when utilization_pct > 1 then 1 else 0 end) as over_ent,
               sum(case when utilization_pct between 0.5 and 1 then 1 else 0 end) as healthy,
               sum(case when utilization_pct < 0.5 then 1 else 0 end) as under_util,
               count(*) as total
        from marts.fct_usage""")[0]
    recon = rows(con, """
        select discrepancy_category as category, count(*) as n,
               sum(abs(coalesce(amount_variance, sfdc_contract_amount, ns_order_amount))) as at_risk
        from marts.rpt_contract_to_netsuite_recon
        where discrepancy_category <> 'matched_clean'
        group by 1 order by 3 desc""")
    return {
        "ending_arr": ending, "nrr": nrr, "grr": grr,
        "fy": fy, "fy_bookings": fy_bookings,
        "pipeline_acv": pipeline_acv, "pipeline_n": pipeline_n,
        "arr_trend": arr_trend, "bridge": bridge,
        "bookings_cat": bookings_cat, "bookings_seg": bookings_seg,
        "usage": usage, "recon": recon,
        "at_risk": sum(r["at_risk"] or 0 for r in recon),
    }


# --------------------------------------------------------------------------- #
# People (aggregates only: everything here comes from people_metrics)
# --------------------------------------------------------------------------- #
def people(con):
    rpe = rows(con, """
        select strftime(month_end, '%Y-%m') as ym, ending_arr, headcount, arr_per_employee
        from people_metrics.rpt_people__revenue_per_employee order by month_end""")
    depts = rows(con, """
        select * from people_metrics.rpt_people__department_summary
        order by is_suppressed, voluntary_attrition_rate_ttm desc""")
    equity = rows(con, """
        select * from people_metrics.rpt_people__pay_equity order by job_level, gender""")
    company = next(d for d in depts if d["department"] == "All departments")
    return {"rpe": rpe, "departments": depts, "pay_equity": equity, "company": company}


# --------------------------------------------------------------------------- #
# Who sees what: the same sample people through each role's secure view
# --------------------------------------------------------------------------- #
def pseudonym(con, worker_id, prefix="P-"):
    return prefix + one(con, "select upper(substr(md5(? || ?), 1, 6))", worker_id, SALT)[0]


def sample_people(con):
    """A handful of current employees that show every rule at work."""
    picks = []

    def take(sql, n=1):
        for r in rows(con, sql):
            if r["worker_id"] not in picks and n > 0:
                picks.append(r["worker_id"])
                n -= 1

    base = "select worker_id from people.dim_employee where is_active and "
    take(base + "department = 'Sales' and region = 'EMEA' and is_sales_rep order by hire_date", 2)
    take(base + "department = 'Sales' and region = 'EMEA' and current_leave_type is not null order by hire_date")
    take(base + "department = 'Sales' and region = 'EMEA' and not is_sales_rep order by hire_date")
    take(base + "current_leave_type = 'Medical' and department <> 'Sales' order by hire_date")
    take(base + "department = 'Engineering' and region = 'NA' and job_level = 'L5' order by hire_date")
    take(base + "department = 'Customer Success' and region in ('APAC', 'LATAM') order by hire_date")
    take(base + "current_leave_type = 'Parental' and department not in ('Sales') order by hire_date")
    take(base + "gender = 'Non-binary' order by hire_date")
    return picks[:8]


def who_sees_what(con, report):
    policy = {r["category"]: r for r in report["policy"]}
    ids = sample_people(con)
    total_active = one(con, "select count(*) from people.dim_employee where is_active")[0]
    views = {}
    for role, label, schema in ROLE_VIEWS:
        cols = [r[0] for r in con.execute(
            "select column_name from information_schema.columns where table_schema = ? "
            "and table_name = 'employees' order by ordinal_position", [schema]).fetchall()]
        key_is_pseudo = not one(con, f"select count(*) from {schema}.employees where worker_id like 'EMP-%'")[0] > 0
        out = []
        for wid in ids:
            key = pseudonym(con, wid) if key_is_pseudo else wid
            r = rows(con, f"select * from {schema}.employees where worker_id = ?", key)
            if not r:
                continue  # filtered out for this role
            row = {}
            for c, _, _, cat in SHOW_COLS:
                treatment = policy[cat][role]
                if c not in cols:
                    row[c] = {"t": "hide"}
                else:
                    v = r[0][c]
                    row[c] = {"t": treatment, "v": None if v is None else str(v)}
            out.append(row)
        visible = one(con, f"select count(*) from {schema}.employees where is_active")[0]
        hidden = [c for c, _, _, _ in SHOW_COLS if c not in cols]
        rules = [{"label": lbl, "t": policy[cat][role]} for c, lbl, cls, cat in SHOW_COLS if cls != "internal"]
        views[role] = {"label": label, "rows": out, "visible": visible, "total": total_active,
                       "hidden": hidden, "columns": len(cols), "rules": rules}
    ai = rows(con, "select department, is_suppressed, headcount, avg_base_pay_band "
                   "from secure_ai_agent.department_summary order by is_suppressed, headcount desc")
    roles = {r["role"]: r for r in report["roles"]}
    for role in views:
        views[role]["description"] = roles[role]["description"]
    first = ids[0]
    examples = {
        "name": one(con, "select employee_name from secure_hr.employees where worker_id = ?", first)[0],
        "pseudo": one(con, "select employee_name from secure_analyst.employees where worker_id = ?", pseudonym(con, first))[0],
        "mask": one(con, "select work_email from secure_analyst.employees where worker_id = ?", pseudonym(con, first))[0],
        "band": one(con, "select base_salary from secure_analyst.employees where worker_id = ?", pseudonym(con, first))[0],
        "age": one(con, "select date_of_birth from secure_analyst.employees where worker_id = ?", pseudonym(con, first))[0],
    }
    return {"columns": [{"key": c, "label": l, "cls": s} for c, l, s, _ in SHOW_COLS], "examples": examples,
            "views": views, "ai": {"departments": ai, "description": roles["ai_agent"]["description"]},
            "sample_size": len(ids)}


def collect():
    with open(REPORT_PATH, encoding="utf-8") as f:
        report = json.load(f)
    con = duckdb.connect(DB_PATH, read_only=True)
    data = {
        "revenue": revenue(con),
        "people": people(con),
        "access": who_sees_what(con, report),
        "governance": {k: report[k] for k in
                       ("models", "models_with_owner", "tests", "build", "classified_columns",
                        "catalog", "policy", "roles", "proofs")},
    }
    con.close()
    return data


if __name__ == "__main__":
    print(json.dumps(collect(), indent=1, default=str)[:6000])

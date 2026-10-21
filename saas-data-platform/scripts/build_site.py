#!/usr/bin/env python
"""
build_site.py — render the published site (GitHub Pages, ../docs/) from the warehouse.

Four pages: home, the revenue review, the people review, and who sees what.
Every number comes from site_data.py (SQL against the dbt models) and from
target/governance_report.json (written by check_governance.py). Pages are
self-contained: CSS, JS and data are inlined; only the fonts load from Google.

The prose makes claims ("churn tripled", "renewals are the biggest source of
bookings"). CLAIMS below checks each one against the data, and the build stops
if any no longer holds, so the words can't drift from the numbers.

Run (from saas-data-platform/, after `dbt build` and check_governance.py):
    python scripts/build_site.py
"""
import datetime
import html
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import site_data  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.join(HERE, "site")
DBT_DIR = os.path.dirname(HERE)
DOCS = os.path.join(os.path.dirname(DBT_DIR), "docs")
REPO = "https://github.com/bbehjoo/analytics-work-samples"
GH = REPO + "/blob/main"

PAGES = [  # file, nav label, <title>, description
    ("index.html", "Home", "Data Leadership Work Samples · Behrang Behjoo",
     "One B2B SaaS company's data, end to end: revenue, people, and the rules for who sees what."),
    ("revenue.html", "Revenue", "Revenue Review · Behrang Behjoo",
     "ARR waterfall, retention, usage, bookings and a CRM-to-ERP reconciliation, built on dbt marts."),
    ("people.html", "People", "People Review · Behrang Behjoo",
     "ARR per employee, attrition and pay equity from aggregates only, with small groups suppressed."),
    ("access.html", "Who sees what", "Who Sees What · Behrang Behjoo",
     "Column classification, one access policy, role-scoped views and the tests that prove nothing leaks."),
]
ROLE_ORDER = ["hr", "finance", "sales_manager_emea", "analyst", "ai_agent"]
CHECK = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m5 12.5 4.5 4.5L19 7.5"/></svg>'


def m(v):
    return ("-" if v < 0 else "") + f"${abs(v) / 1e6:.1f}M"


def k(v):
    return f"${round(v / 1000)}k"


def pct(v, d=1):
    return f"{v * 100:.{d}f}%"


def fill(template, values):
    """Replace {{key}} placeholders; fail loudly on any key without a value."""
    def sub(match):
        key = match.group(1)
        if key not in values:
            raise KeyError(f"no value for {{{{{key}}}}}")
        return str(values[key])
    return re.sub(r"\{\{(\w+)\}\}", sub, template)


def read(name):
    with open(os.path.join(SITE, name), encoding="utf-8") as f:
        return f.read()


def values_and_claims(d):
    R, P, A, G = d["revenue"], d["people"], d["access"], d["governance"]
    bridge = {b["yr"]: b for b in R["bridge"]}
    years = sorted(bridge)
    first, prev, last = years[0], years[-2], years[-1]
    recon = {r["category"]: r for r in R["recon"]}
    rpe = P["rpe"]
    peak = max(rpe, key=lambda r: r["arr_per_employee"])
    end = rpe[-1]
    i_peak = rpe.index(peak)
    dec_prev = next(r for r in rpe if r["ym"] == f"{prev}-12")
    depts = {x["department"]: x for x in P["departments"]}
    company, cs = P["company"], depts["Customer Success"]
    eq = {(r["job_level"], r["gender"]): r for r in P["pay_equity"]}
    proofs = G["proofs"]
    gov_proofs = proofs[:4]
    build_total = sum(G["build"].values())
    build_passed = G["build"].get("success", 0) + G["build"].get("pass", 0)
    usage = R["usage"]
    top_cat = max(R["bookings_cat"], key=lambda r: r["acv"])["category"]
    top_seg = max(R["bookings_seg"], key=lambda r: r["acv"])["segment"]
    month = datetime.date(int(peak["ym"][:4]), int(peak["ym"][5:]), 1).strftime("%B %Y")

    V = {
        "repo": REPO, "gh": GH, "generated": datetime.date.today().isoformat(),
        "build_passed": build_passed, "build_total": build_total,
        "last_year": last, "as_of": "31 Dec " + str(last),
        # home + revenue
        "ending_arr": m(R["ending_arr"]), "nrr": pct(R["nrr"], 0), "grr": pct(R["grr"], 0),
        "fy_bookings": m(R["fy_bookings"]), "pipeline": m(R["pipeline_acv"]), "pipeline_n": R["pipeline_n"],
        "at_risk": m(R["at_risk"]), "missing_ns": m(recon["missing_in_netsuite"]["at_risk"]),
        "missing_n": recon["missing_in_netsuite"]["n"], "orphan_n": recon["orphan_in_netsuite"]["n"],
        "exp_first": m(bridge[first]["expansion"]), "exp_last": m(bridge[last]["expansion"]),
        "nl_first": m(bridge[first]["new_logo"]), "nl_last": m(bridge[last]["new_logo"]),
        "churn_prev": m(-bridge[prev]["churn"]), "churn_2025": m(-bridge[last]["churn"]),
        "grr_2pts": m(0.02 * R["ending_arr"]),
        "over_pct": pct(usage["over_ent"] / usage["total"], 0), "under_pct": pct(usage["under_util"] / usage["total"], 0),
        "pii_leaks": "0", "gov_test_count": len(gov_proofs),
        "models": G["models"], "owned_pct": pct(G["models_with_owner"] / G["models"], 0),
        "metric_count": d["metric_count"],
        # people
        "headcount": company["headcount"], "attrition": pct(company["attrition_rate_ttm"]),
        "vol_attrition": pct(company["voluntary_attrition_rate_ttm"]),
        "cs_attrition": pct(cs["attrition_rate_ttm"], 0),
        "rpe_peak": k(peak["arr_per_employee"]), "rpe_end": k(end["arr_per_employee"]), "rpe_peak_month": month,
        "h2_hires": end["headcount"] - peak["headcount"], "h2_arr": m(end["ending_arr"] - peak["ending_arr"]),
        "gap_l4": f'{eq[("L4", "Woman")]["gap_vs_men_pct"]:.1f}%', "gap_l6": f'{eq[("L6", "Woman")]["gap_vs_men_pct"]:.1f}%',
        "avg_w": f'${eq[("All", "Woman")]["avg_base_salary"] / 1000:.1f}k',
        "avg_m": f'${eq[("All", "Man")]["avg_base_salary"] / 1000:.1f}k',
        "l4_women": eq[("L4", "Woman")]["employees"], "l4_cost": k(eq[("L4", "Woman")]["cost_to_close_usd"]),
        "l4_cost_pct": f'{eq[("L4", "Woman")]["cost_to_close_pct_of_payroll"]:.2f}%',
        "l4_w_cr": f'{eq[("L4", "Woman")]["avg_compa_ratio"]:.3f}', "l4_m_cr": f'{eq[("L4", "Man")]["avg_compa_ratio"]:.3f}',
        # access
        "classified": sum(G["classified_columns"].values()), "role_count": len(G["roles"]),
        "proofs_passed": f'{sum(p["status"] == "pass" for p in proofs)} of {len(proofs)}',
        "owned": f'{G["models_with_owner"]} of {G["models"]}',
        "ex_name": html.escape(A["examples"]["name"]), "ex_pseudo": A["examples"]["pseudo"],
        "ex_mask": A["examples"]["mask"], "ex_band": A["examples"]["band"], "ex_age": A["examples"]["age"],
    }

    CLAIMS = [
        (all(p["status"] == "pass" for p in proofs), "every proof test passed (the site says 0 leaks)"),
        (build_passed == build_total, "dbt build passed in full"),
        (bridge[last]["churn"] / bridge[prev]["churn"] >= 2.5, "churn tripled year on year"),
        (bridge[last]["expansion"] > bridge[last]["new_logo"], "expansion now drives growth"),
        (bridge[last]["new_logo"] < bridge[first]["new_logo"], "new logo fell"),
        (abs(bridge[last]["net_new"] / bridge[prev]["net_new"] - 1) < 0.1, "net new ARR held roughly steady"),
        (top_cat == "scheduled", "renewals are the biggest source of bookings"),
        (top_seg == "Mid-Market", "Mid-Market is the volume engine"),
        (recon["missing_in_netsuite"]["at_risk"] == max(r["at_risk"] for r in R["recon"]), "missing-in-NetSuite is the biggest exposure"),
        (i_peak < len(rpe) - 1 and end["arr_per_employee"] < peak["arr_per_employee"], "ARR per employee peaked, then slipped"),
        (end["headcount"] / peak["headcount"] - 1 > end["ending_arr"] / peak["ending_arr"] - 1, "hiring outran revenue"),
        (abs(end["arr_per_employee"] / dec_prev["arr_per_employee"] - 1) < 0.03, "efficiency fell back to a year earlier"),
        (cs["attrition_rate_ttm"] == cs["voluntary_attrition_rate_ttm"], "every Customer Success exit was voluntary"),
        (abs(cs["avg_compa_ratio"] - 1) <= 0.02, "Customer Success is paid at its band midpoint"),
        (cs["voluntary_attrition_rate_ttm"] == max(x["voluntary_attrition_rate_ttm"] or 0 for x in P["departments"]), "Customer Success is the hotspot"),
        (abs(eq[("All", "Woman")]["avg_base_salary"] / eq[("All", "Man")]["avg_base_salary"] - 1) < 0.01, "company-wide pay looks equal"),
        (eq[("L4", "Woman")]["gap_vs_men_pct"] == min(r["gap_vs_men_pct"] for r in P["pay_equity"] if r["gap_vs_men_pct"] is not None and r["job_level"] != "All"), "L4 is the largest gap"),
        (depts["Legal"]["is_suppressed"], "Legal is suppressed"),
        (eq[("L7", "Woman")]["is_suppressed"], "L7 women are suppressed"),
    ]
    broken = [msg for ok, msg in CLAIMS if not ok]
    if broken:
        raise SystemExit("The data no longer supports: " + "; ".join(broken) + ". Update the copy in scripts/site/.")
    return V, gov_proofs


def policy_table(G):
    labels = {r["role"]: r["label"] for r in G["roles"]}
    head = "<tr><th>Category</th><th>Class</th>" + "".join(f"<th>{html.escape(labels[r])}</th>" for r in ROLE_ORDER) + "</tr>"
    rows = []
    for p in G["policy"]:
        cells = "".join(f'<td class="nowrap"><span class="t {p[r]}">{p[r]}</span></td>' for r in ROLE_ORDER)
        rows.append(f'<tr><td><b>{p["category"].replace("_", " ").capitalize()}</b><small>{html.escape(p["example_columns"])}</small></td>'
                    f'<td class="nowrap"><span class="sens"><i class="dot {p["sensitivity"] if p["sensitivity"] != "internal" else ""}"></i>{p["sensitivity"]}</span></td>{cells}</tr>')
    return f"<table><thead>{head}</thead><tbody>{''.join(rows)}</tbody></table>"


def proof_table(proofs):
    rows = "".join(
        f'<tr><td class="nowrap"><a href="{GH}/saas-data-platform/tests/{p["test"]}.sql"><code>{p["test"]}</code></a></td>'
        f'<td>{html.escape(p["plain"])}</td><td class="nowrap ok">{"✓ pass" if p["status"] == "pass" else html.escape(p["status"])}</td></tr>'
        for p in proofs)
    return f"<table><thead><tr><th>Test</th><th>What it proves</th><th>Last build</th></tr></thead><tbody>{rows}</tbody></table>"


def catalog_table(G):
    order = {"marts": 0, "people": 1, "people_metrics": 2}
    cat = sorted(G["catalog"], key=lambda c: (order.get(c["schema"], 3), c["model"]))
    rows = "".join(
        f'<tr><td class="nowrap"><code>{c["model"]}</code><small>{c["relation"]}</small></td>'
        f'<td class="nowrap">{html.escape(c["owner"] or "")}</td><td>{c["access"]}</td>'
        f'<td>{"✓ enforced" if c["contract"] else ""}</td>'
        f'<td class="nowrap"><span class="sens"><i class="dot {c["sensitivity"] if c["sensitivity"] != "internal" else ""}"></i>{c["sensitivity"]}</span></td>'
        f'<td>{c["tests"]}</td></tr>'
        for c in cat)
    return ("<table><thead><tr><th>Model</th><th>Owner</th><th>Access</th><th>Contract</th>"
            f"<th>Most sensitive column</th><th>Tests</th></tr></thead><tbody>{rows}</tbody></table>")


def main():
    d = site_data.collect()
    with open(os.path.join(DBT_DIR, "target", "manifest.json"), encoding="utf-8") as f:
        d["metric_count"] = len(json.load(f).get("metrics", {}))
    V, gov_proofs = values_and_claims(d)
    G = d["governance"]
    proofs_html = "".join(
        f'<div class="proof">{CHECK}<div>{html.escape(p["plain"])}<code>{p["test"]}</code></div></div>' for p in gov_proofs)
    V["policy_table"] = policy_table(G)
    V["proof_table"] = proof_table(G["proofs"])
    V["catalog_table"] = catalog_table(G)

    css, js = read("site.css"), read("site.js")
    data = json.dumps({"revenue": d["revenue"], "people": d["people"], "access": d["access"]},
                      default=str, separators=(",", ":")).replace("</", "<\\/")
    os.makedirs(DOCS, exist_ok=True)
    for name, label, title, description in PAGES:
        more = '<a class="more" href="access.html">How it\'s enforced: the policy, the tests, the owners</a>' if name == "index.html" else ""
        who = fill(read("_who.html"), {**V, "gov_proofs": proofs_html, "who_more": more})
        content = fill(read(name), {**V, "who_block": who})
        current = ' aria-current="page"'
        nav = "".join(
            f'<a href="{f}"{current if f == name else ""}>{lbl}</a>' for f, lbl, _, _ in PAGES
        ) + f'<a href="{REPO}">GitHub ↗</a>'
        page = fill(read("base.html"), {**V, "title": title, "description": description, "nav": nav,
                                        "content": content, "css": css, "js": js, "data": data})
        with open(os.path.join(DOCS, name), "w", encoding="utf-8", newline="\n") as f:
            f.write(page)
        print(f"Wrote docs/{name}  ({len(page) // 1024} KB)")
    open(os.path.join(DOCS, ".nojekyll"), "w").close()
    print("Claims checked against the data: all hold.")


if __name__ == "__main__":
    main()

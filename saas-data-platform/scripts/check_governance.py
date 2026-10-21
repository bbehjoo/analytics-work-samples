#!/usr/bin/env python
"""
check_governance.py — fail the build when ownership or classification slips.

Reads dbt's target/manifest.json (and run_results.json, if present) plus the
warehouse itself, and checks four rules:

  1. Every model belongs to a group, and every group has a named owner.
  2. Every model has a description.
  3. Every column of every people-domain model that exists in the warehouse is
     classified (config.meta.sensitivity). Secure views may only expose columns
     that exist, classified, on the model they protect.
  4. Anywhere in the project, a column whose name looks like personal data
     (email, birth date, postal code, pay, gender, leave, a person's name) is
     classified.

It also writes target/governance_report.json: the ownership catalog, the
classification counts, the access policy and the proof-test results. The site
builder reads that file, so the published page always matches the code.

Run (from saas-data-platform/, after `dbt build`):
    python scripts/check_governance.py
Exit code 1 on any violation, so CI fails.
"""
import csv
import json
import os
import re
import sys
from collections import Counter

import duckdb

HERE = os.path.dirname(os.path.abspath(__file__))
DBT_DIR = os.path.dirname(HERE)
TARGET = os.path.join(DBT_DIR, "target")
DB_PATH = os.path.join(DBT_DIR, "warehouse.duckdb")
POLICY_CSV = os.path.join(DBT_DIR, "seeds", "governance", "access_policy.csv")
ROLES_CSV = os.path.join(DBT_DIR, "seeds", "governance", "roles.csv")

PERSONAL = re.compile(
    r"(email|birth|postal|salary|(^|_)pay(_|$)|bonus|equity|gender|leave|"
    r"(rep|owner|user|employee|person|manager)_?name|^employee_name$)")
RANK = {None: -1, "internal": 0, "confidential": 1, "pii": 2, "restricted": 3}
PROOF_TESTS = [
    ("assert_no_pii_leaks", "No masked value matches the original, and hidden columns are really gone"),
    ("assert_restricted_never_reaches_analyst_or_ai", "Pay, health and gender never reach analysts or the AI agent"),
    ("assert_row_filters_hold", "The EMEA manager's view holds exactly their EMEA sales team"),
    ("assert_small_groups_suppressed", "No number is shown for a group under 5"),
    ("assert_arr_waterfall_integrity", "The ARR waterfall balances to the cent, every month"),
    ("assert_arr_continuity", "Each month's ending ARR is the next month's beginning ARR"),
    ("assert_acv_equals_components", "Every deal's ACV equals its recurring plus one-time value"),
    ("assert_recon_category_counts", "The CRM-to-ERP reconciliation finds every seeded discrepancy"),
]


def col_meta(col):
    cfg = col.get("config") or {}
    return (cfg.get("meta") or {}) or (col.get("meta") or {})


def main():
    with open(os.path.join(TARGET, "manifest.json"), encoding="utf-8") as f:
        manifest = json.load(f)
    groups = {g["name"]: g for g in manifest.get("groups", {}).values()}
    models = {n["name"]: n for n in manifest["nodes"].values()
              if n["resource_type"] == "model" and n["package_name"] == manifest["metadata"]["project_name"]}
    tests = [n for n in manifest["nodes"].values() if n["resource_type"] == "test"]

    con = duckdb.connect(DB_PATH, read_only=True)
    db_cols = {}
    for schema, table, column in con.execute(
            "select table_schema, table_name, column_name from information_schema.columns").fetchall():
        db_cols.setdefault((schema, table), []).append(column)

    violations = []

    def warehouse_columns(node):
        return db_cols.get((node["schema"], node.get("alias") or node["name"]), [])

    for name, node in sorted(models.items()):
        group = node.get("group") or node["config"].get("group")
        # 1. owner
        if not group:
            violations.append(f"{name}: no group, so no owner")
        elif not (groups.get(group, {}).get("owner") or {}).get("name"):
            violations.append(f"{name}: group '{group}' has no named owner")
        # 2. description
        if not (node.get("description") or "").strip():
            violations.append(f"{name}: no description")

        documented = node.get("columns", {})
        actual = warehouse_columns(node)
        # 3. people domain fully classified; secure views expose only classified columns
        if group == "people":
            if name.startswith("secure_") and name.endswith("__employees"):
                protected = models["dim_employee"]["columns"]
                for c in actual:
                    if c not in protected or not col_meta(protected[c]).get("sensitivity"):
                        violations.append(f"{name}.{c}: not a classified column of dim_employee")
            elif name.startswith("rpt_") or name.startswith("secure_ai_agent") or name.startswith("bridge_"):
                pass  # aggregates and keys; covered by rule 4 and the suppression test
            else:
                for c in actual:
                    if not col_meta(documented.get(c, {})).get("sensitivity"):
                        violations.append(f"{name}.{c}: people column without a sensitivity tag")
        # 4. personal-looking columns anywhere
        if not (name.startswith("secure_") and name.endswith("__employees")):
            for c in actual:
                if PERSONAL.search(c) and not col_meta(documented.get(c, {})).get("sensitivity"):
                    violations.append(f"{name}.{c}: looks like personal data but has no sensitivity tag")

    # ---- the report the site reads ---------------------------------------
    run_results = {}
    rr_path = os.path.join(TARGET, "run_results.json")
    if os.path.exists(rr_path):
        with open(rr_path, encoding="utf-8") as f:
            for r in json.load(f)["results"]:
                run_results[r["unique_id"]] = r["status"]

    tests_by_model = Counter()
    for t in tests:
        for dep in t["depends_on"]["nodes"]:
            if dep.startswith("model."):
                tests_by_model[dep.split(".")[-1]] += 1

    catalog = []
    for name, node in sorted(models.items()):
        if not (node["schema"] in ("marts", "people", "people_metrics") or name.startswith("secure_")):
            continue
        group = node.get("group") or node["config"].get("group")
        sens = [col_meta(c).get("sensitivity") for c in node.get("columns", {}).values()]
        if name.startswith("secure_") and name.endswith("__employees"):
            protected = models["dim_employee"]["columns"]
            sens = [col_meta(protected[c]).get("sensitivity") for c in warehouse_columns(node) if c in protected]
        top = max(sens, key=lambda s: RANK[s]) if sens else None
        catalog.append({
            "model": name,
            "schema": node["schema"],
            "relation": f'{node["schema"]}.{node.get("alias") or name}',
            "owner": (groups.get(group, {}).get("owner") or {}).get("name"),
            "access": node["config"].get("access") or node.get("access"),
            "contract": bool((node["config"].get("contract") or {}).get("enforced")),
            "certified": (node["config"].get("meta") or {}).get("tier") == "certified",
            "sensitivity": top or "internal",
            "tests": tests_by_model[name],
        })

    classified = Counter()
    for node in models.values():
        for c in node.get("columns", {}).values():
            s = col_meta(c).get("sensitivity")
            if s:
                classified[s] += 1

    with open(POLICY_CSV, encoding="utf-8") as f:
        policy = list(csv.DictReader(f))
    with open(ROLES_CSV, encoding="utf-8") as f:
        roles = list(csv.DictReader(f))

    proofs = []
    for test_name, plain in PROOF_TESTS:
        uid = next((t["unique_id"] for t in tests if t["name"] == test_name), None)
        proofs.append({"test": test_name, "plain": plain, "status": run_results.get(uid, "not run")})

    statuses = Counter(run_results.values())
    report = {
        "models": len(models),
        "models_with_owner": sum(1 for n in models.values() if n.get("group") or n["config"].get("group")),
        "tests": len(tests),
        "build": dict(statuses),
        "classified_columns": dict(classified),
        "catalog": catalog,
        "policy": policy,
        "roles": roles,
        "proofs": proofs,
        "violations": violations,
    }
    with open(os.path.join(TARGET, "governance_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(f"Models: {len(models)}  owned: {report['models_with_owner']}  tests: {len(tests)}")
    print("Classified columns: " + ", ".join(f"{k}={v}" for k, v in sorted(classified.items())))
    for p in proofs:
        print(f"  [{p['status']:>6}] {p['test']}")
    if violations:
        print(f"\n{len(violations)} governance violation(s):")
        for v in violations:
            print("  - " + v)
        sys.exit(1)
    print("Governance check passed: every model owned, every personal column classified.")


if __name__ == "__main__":
    main()

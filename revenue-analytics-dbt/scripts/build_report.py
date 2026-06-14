#!/usr/bin/env python
"""
build_report.py — render the executive insights report as a self-contained HTML
page, computed live from the dbt marts in grafana.duckdb.

This is the visual companion to reports/revenue_insights_report.md: same findings,
but with KPI tiles and interactive charts. Output is written to the repo-root
docs/ folder so it can be served by GitHub Pages.

Run (from revenue-analytics-dbt/, after `dbt build`):
    python scripts/build_report.py
"""
import datetime
import json
import os

import duckdb

HERE = os.path.dirname(os.path.abspath(__file__))
DBT_DIR = os.path.dirname(HERE)
REPO_ROOT = os.path.dirname(DBT_DIR)
DOCS_DIR = os.path.join(REPO_ROOT, "docs")
DB_PATH = os.path.join(DBT_DIR, "grafana.duckdb")
os.makedirs(DOCS_DIR, exist_ok=True)


def fetch(con, sql):
    return con.execute(sql).fetchall()


def build_data():
    con = duckdb.connect(DB_PATH, read_only=True)

    # --- ARR monthly trend -------------------------------------------------
    arr_trend = fetch(con, """
        select strftime(measurement_month, '%Y-%m') as ym, sum(ending_arr) as arr
        from marts.fct_arr group by 1 order by 1
    """)

    # --- ARR movement by year + year-end ARR -------------------------------
    movements = fetch(con, """
        select cast(extract(year from measurement_month) as integer) as yr,
               sum(new_logo_arr) as new_logo,
               sum(cross_sell_arr + upsell_arr) as expansion,
               sum(downgrade_arr) as downgrade,
               sum(churn_arr) as churn,
               sum(arr_change) as net_new
        from marts.fct_arr group by 1 order by 1
    """)
    year_end = dict(fetch(con, """
        with ye as (
            select cast(extract(year from measurement_month) as integer) as yr,
                   max(measurement_month) as m
            from marts.fct_arr group by 1
        )
        select ye.yr, sum(f.ending_arr)
        from marts.fct_arr f join ye on f.measurement_month = ye.m
        group by 1
    """))

    # --- NRR / GRR (period approximation) ----------------------------------
    nrr, grr, ending_arr = fetch(con, """
        select
          (sum(beginning_arr)+sum(upsell_arr)+sum(cross_sell_arr)+sum(downgrade_arr)+sum(churn_arr))
              / nullif(sum(beginning_arr),0),
          (sum(beginning_arr)+sum(downgrade_arr)+sum(churn_arr)) / nullif(sum(beginning_arr),0),
          (select sum(ending_arr) from marts.fct_arr
             where measurement_month = (select max(measurement_month) from marts.fct_arr))
        from marts.fct_arr
    """)[0]

    # --- Bookings ACV by revenue category (won) ----------------------------
    bookings_cat = fetch(con, """
        select revenue_category, sum(acv) as acv
        from marts.fct_acv where is_closed_won and acv > 0
        group by 1 order by 2 desc
    """)

    # --- Bookings ACV by segment (won) -------------------------------------
    bookings_seg = fetch(con, """
        select a.segment, sum(f.acv) as acv, count(distinct f.opportunity_id) as deals
        from marts.fct_acv f join marts.dim_account a using (account_key)
        where f.is_closed_won group by 1 order by 2 desc
    """)

    pipeline_acv = fetch(con, "select sum(acv), count(distinct opportunity_id) from marts.fct_acv where not is_closed")[0]
    fy_bookings = fetch(con, """
        select sum(acv) from marts.fct_acv
        where is_closed_won and sales_year = (select max(sales_year) from marts.fct_acv where is_closed_won)
    """)[0][0]
    fy = fetch(con, "select max(sales_year) from marts.fct_acv where is_closed_won")[0][0]

    # --- Usage utilization buckets -----------------------------------------
    usage = fetch(con, """
        select
          sum(case when utilization_pct > 1 then 1 else 0 end) as over_ent,
          sum(case when utilization_pct between 0.5 and 1 then 1 else 0 end) as healthy,
          sum(case when utilization_pct < 0.5 then 1 else 0 end) as under_util,
          count(*) as total
        from marts.fct_usage
    """)[0]

    # --- Reconciliation $ at risk by category ------------------------------
    recon = fetch(con, """
        select discrepancy_category, count(*) as n,
               sum(abs(coalesce(amount_variance, sfdc_contract_amount, ns_order_amount))) as at_risk
        from marts.rpt_contract_to_netsuite_recon
        where discrepancy_category <> 'matched_clean'
        group by 1 order by 3 desc
    """)
    total_at_risk = sum(r[2] or 0 for r in recon)
    con.close()

    cat_label = {
        "new_logo": "New logo", "cross_sell": "Cross-sell", "upsell": "Upsell",
        "scheduled": "Renewal", "downgrade": "Downgrade", "churn": "Churn",
    }
    disc_label = {
        "missing_in_netsuite": "Missing in NetSuite", "amount_mismatch": "Amount mismatch",
        "orphan_in_netsuite": "Orphan in NetSuite", "currency_rounding": "Currency rounding",
        "timing_difference": "Timing difference", "partially_invoiced": "Partially invoiced",
    }

    return {
        "kpis": [
            {"label": "Ending ARR", "value": f"${ending_arr/1e6:.1f}M", "sub": "Dec 2025 run-rate"},
            {"label": "Net Revenue Retention", "value": f"{nrr*100:.0f}%", "sub": "period approximation"},
            {"label": "Gross Revenue Retention", "value": f"{grr*100:.0f}%", "sub": "period approximation"},
            {"label": f"Bookings ACV (FY{fy})", "value": f"${fy_bookings/1e6:.1f}M", "sub": "closed-won"},
            {"label": "Open Pipeline ACV", "value": f"${pipeline_acv[0]/1e6:.1f}M", "sub": f"{pipeline_acv[1]} opportunities"},
            {"label": "$ at risk (recon)", "value": f"${total_at_risk/1e6:.1f}M", "sub": "SFDC vs NetSuite"},
        ],
        "arr_trend": {"labels": [r[0] for r in arr_trend], "values": [round(r[1]/1e6, 2) for r in arr_trend]},
        "arr_bridge": {
            "years": [str(r[0]) for r in movements],
            "new_logo": [round(r[1]/1e6, 2) for r in movements],
            "expansion": [round(r[2]/1e6, 2) for r in movements],
            "downgrade": [round(r[3]/1e6, 2) for r in movements],
            "churn": [round(r[4]/1e6, 2) for r in movements],
            "ending": [round(year_end.get(r[0], 0)/1e6, 2) for r in movements],
        },
        "bookings_cat": {"labels": [cat_label.get(r[0], r[0]) for r in bookings_cat],
                          "values": [round(r[1]/1e6, 2) for r in bookings_cat]},
        "bookings_seg": {"labels": [r[0] for r in bookings_seg],
                          "values": [round(r[1]/1e6, 2) for r in bookings_seg],
                          "deals": [r[2] for r in bookings_seg]},
        "usage": {"over": usage[0], "healthy": usage[1], "under": usage[2],
                   "over_pct": round(100*usage[0]/usage[3], 1), "under_pct": round(100*usage[2]/usage[3], 1)},
        "recon": {"labels": [disc_label.get(r[0], r[0]) for r in recon],
                   "values": [round((r[2] or 0)/1e6, 3) for r in recon],
                   "counts": [r[1] for r in recon]},
    }


HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Revenue Insights — QBR (work sample)</title>
<script src="vendor/chart.umd.min.js"></script>
<style>
  :root{
    --bg:#eef2f6; --card:#ffffff; --ink:#16222e; --muted:#5b6b7b; --line:#e2e8f0;
    --navy:#12395b; --blue:#2f6db0; --teal:#1f9d8f; --amber:#d99a2b; --red:#c0492b;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
    line-height:1.5;-webkit-font-smoothing:antialiased}
  .wrap{max-width:1080px;margin:0 auto;padding:32px 20px 64px}
  header.top{margin-bottom:8px}
  header.top h1{margin:0 0 4px;font-size:30px;letter-spacing:-.4px}
  header.top .sub{color:var(--muted);font-size:15px}
  .pill{display:inline-block;background:#dbe7f2;color:var(--navy);font-size:12px;
    font-weight:600;padding:3px 10px;border-radius:999px;margin-bottom:14px}
  .kpis{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin:22px 0 8px}
  @media(max-width:720px){.kpis{grid-template-columns:repeat(2,1fr)}}
  .kpi{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 18px;
    box-shadow:0 1px 2px rgba(16,38,58,.04)}
  .kpi .v{font-size:26px;font-weight:700;color:var(--navy);letter-spacing:-.5px}
  .kpi .l{font-size:13px;color:var(--ink);font-weight:600;margin-top:2px}
  .kpi .s{font-size:12px;color:var(--muted)}
  .card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:22px 24px;
    margin-top:20px;box-shadow:0 1px 2px rgba(16,38,58,.04)}
  .card h2{margin:0 0 2px;font-size:19px}
  .card .src{font-size:12px;color:var(--muted);margin-bottom:14px}
  .grid{display:grid;grid-template-columns:1.15fr .85fr;gap:24px;align-items:center}
  @media(max-width:760px){.grid{grid-template-columns:1fr}}
  .chartbox{position:relative;height:300px}
  .note h3{margin:6px 0 4px;font-size:13px;text-transform:uppercase;letter-spacing:.4px;color:var(--muted)}
  .note p{margin:0 0 12px;font-size:14.5px}
  .tag{font-weight:700}
  .tag.good{color:var(--teal)} .tag.bad{color:var(--red)} .tag.navy{color:var(--navy)}
  footer{color:var(--muted);font-size:12.5px;margin-top:28px;text-align:center}
  a{color:var(--blue)}
</style>
</head>
<body>
<div class="wrap">
  <span class="pill">Work sample · synthetic data · generated from the dbt marts</span>
  <header class="top">
    <h1>Revenue Insights — Quarterly Business Review</h1>
    <div class="sub">A visual read of the Salesforce + NetSuite revenue marts. Every number is computed live from <code>fct_arr</code>, <code>fct_acv</code>, <code>fct_usage</code>, and <code>rpt_contract_to_netsuite_recon</code>.</div>
  </header>

  <div class="kpis" id="kpis"></div>

  <div class="card">
    <h2>1 · ARR growth &amp; the waterfall</h2>
    <div class="src">Source: <code>fct_arr</code> · the company ARR bridge balances to the cent (enforced by a dbt test)</div>
    <div class="grid">
      <div class="chartbox"><canvas id="arrTrend"></canvas></div>
      <div class="note">
        <h3>What it is</h3>
        <p>ARR grew from ~$1.5M to <span class="tag navy">$82.1M</span> over three years.</p>
        <h3>Why it matters</h3>
        <p>The engine is shifting from new logo to <span class="tag good">expansion</span> (land-and-expand maturing), but <span class="tag bad">churn is accelerating</span> — net new ARR is flat only because expansion masks it.</p>
        <h3>What to do</h3>
        <p>Pressure-test the new-logo top of funnel and stand up a churn early-warning from §4.</p>
      </div>
    </div>
    <div class="chartbox" style="height:280px;margin-top:18px"><canvas id="arrBridge"></canvas></div>
  </div>

  <div class="card">
    <h2>2 · Bookings &amp; pipeline — the sales view</h2>
    <div class="src">Source: <code>fct_acv</code> (opportunity-line grain) joined to <code>dim_account</code></div>
    <div class="grid">
      <div class="chartbox"><canvas id="bookingsCat"></canvas></div>
      <div class="chartbox"><canvas id="bookingsSeg"></canvas></div>
    </div>
    <div class="note">
      <p style="margin-top:14px"><b>Renewals are the largest bookings category</b> — protecting the renewal base matters as much as new sales. Mid-Market is the bookings volume engine; open pipeline is the forward indicator against the new-logo gap above.</p>
    </div>
  </div>

  <div class="card">
    <h2>3 · Usage vs entitlement — quantified expansion &amp; churn list</h2>
    <div class="src">Source: <code>fct_usage</code> (consumption vs the subscription in force that month)</div>
    <div class="grid">
      <div class="chartbox"><canvas id="usage"></canvas></div>
      <div class="note">
        <h3>Why it matters</h3>
        <p><span class="tag good" id="overPct"></span> of subscriptions consume <b>over</b> their entitlement — a warm, evidence-backed upsell list — while <span class="tag bad" id="underPct"></span> are <b>under-utilized</b> ahead of renewal (churn risk).</p>
        <h3>What to do</h3>
        <p>Route over-entitlement accounts to AMs as expansion plays; route under-utilized accounts near renewal to CS.</p>
      </div>
    </div>
  </div>

  <div class="card">
    <h2>4 · Finance hygiene — Salesforce ↔ NetSuite reconciliation</h2>
    <div class="src">Source: <code>rpt_contract_to_netsuite_recon</code> · a closed-loop dbt test asserts these counts</div>
    <div class="grid">
      <div class="chartbox"><canvas id="recon"></canvas></div>
      <div class="note">
        <h3>What it is</h3>
        <p>Every contract matched to its NetSuite order &amp; invoices, with the disagreements bucketed.</p>
        <h3>Why it matters</h3>
        <p><b>Missing-in-NetSuite is the biggest exposure</b>: contracted revenue with no ERP order — a close-the-books and revenue-recognition risk, not a rounding nuisance.</p>
        <h3>What to do</h3>
        <p>Work the missing + orphan records first; auto-clear currency rounding with a materiality threshold; make this a standing month-end check.</p>
      </div>
    </div>
  </div>

  <footer>
    Generated __GENERATED__ from <code>grafana.duckdb</code> · all data synthetic ·
    <a href="https://github.com/bbehjoo/analytics-work-samples">github.com/bbehjoo/analytics-work-samples</a>
  </footer>
</div>

<script>
const DATA = __DATA__;
const fmtM = v => '$' + v.toFixed(1) + 'M';
const C = {navy:'#12395b', blue:'#2f6db0', teal:'#1f9d8f', amber:'#d99a2b', red:'#c0492b', gray:'#9fb0c0'};
const $ = id => document.getElementById(id);

// KPI tiles
document.getElementById('kpis').innerHTML = DATA.kpis.map(k =>
  `<div class="kpi"><div class="v">${k.value}</div><div class="l">${k.label}</div><div class="s">${k.sub}</div></div>`).join('');
document.getElementById('overPct').textContent = DATA.usage.over_pct + '%';
document.getElementById('underPct').textContent = DATA.usage.under_pct + '%';

Chart.defaults.font.family = "-apple-system, Segoe UI, Roboto, sans-serif";
Chart.defaults.color = '#5b6b7b';
const money = {ticks:{callback:v=>'$'+v+'M'}};

new Chart($('arrTrend'), {type:'line',
  data:{labels:DATA.arr_trend.labels, datasets:[{label:'ARR', data:DATA.arr_trend.values,
    borderColor:C.navy, backgroundColor:'rgba(18,57,91,.08)', fill:true, tension:.25, pointRadius:0, borderWidth:2}]},
  options:{plugins:{legend:{display:false}}, scales:{y:money, x:{ticks:{maxTicksLimit:8}}}, maintainAspectRatio:false}});

new Chart($('arrBridge'), {
  data:{labels:DATA.arr_bridge.years, datasets:[
    {type:'bar', label:'New logo', data:DATA.arr_bridge.new_logo, backgroundColor:C.navy, stack:'m'},
    {type:'bar', label:'Expansion', data:DATA.arr_bridge.expansion, backgroundColor:C.teal, stack:'m'},
    {type:'bar', label:'Downgrade', data:DATA.arr_bridge.downgrade, backgroundColor:C.amber, stack:'m'},
    {type:'bar', label:'Churn', data:DATA.arr_bridge.churn, backgroundColor:C.red, stack:'m'},
    {type:'line', label:'Ending ARR', data:DATA.arr_bridge.ending, borderColor:'#16222e', borderWidth:2, pointRadius:3, tension:.2}
  ]},
  options:{plugins:{title:{display:true,text:'ARR movement by year ($M)'}}, responsive:true, maintainAspectRatio:false,
    scales:{x:{stacked:true}, y:{stacked:true, ...money}}}});

new Chart($('bookingsCat'), {type:'doughnut',
  data:{labels:DATA.bookings_cat.labels, datasets:[{data:DATA.bookings_cat.values,
    backgroundColor:[C.navy,C.teal,C.blue,C.amber,C.red,C.gray]}]},
  options:{plugins:{legend:{position:'right'}, title:{display:true,text:'Bookings ACV by category ($M)'}}, maintainAspectRatio:false}});

new Chart($('bookingsSeg'), {type:'bar',
  data:{labels:DATA.bookings_seg.labels, datasets:[{label:'Bookings ACV', data:DATA.bookings_seg.values, backgroundColor:C.blue}]},
  options:{plugins:{legend:{display:false}, title:{display:true,text:'Bookings ACV by segment ($M)'}}, scales:{y:money}, maintainAspectRatio:false}});

new Chart($('usage'), {type:'doughnut',
  data:{labels:['Over entitlement','Healthy (50–100%)','Under-utilized (<50%)'],
    datasets:[{data:[DATA.usage.over, DATA.usage.healthy, DATA.usage.under], backgroundColor:[C.teal,C.gray,C.red]}]},
  options:{plugins:{legend:{position:'bottom'}, title:{display:true,text:'Subscription-months by utilization'}}, maintainAspectRatio:false}});

new Chart($('recon'), {type:'bar',
  data:{labels:DATA.recon.labels, datasets:[{label:'$ at risk', data:DATA.recon.values, backgroundColor:C.red}]},
  options:{indexAxis:'y', plugins:{legend:{display:false}, title:{display:true,text:'$M at risk by discrepancy'}}, scales:{x:money}, maintainAspectRatio:false}});
</script>
</body>
</html>
"""


def main():
    data = build_data()
    today = datetime.date.today().isoformat()
    html = HTML.replace("__DATA__", json.dumps(data)).replace("__GENERATED__", today)
    out = os.path.join(DOCS_DIR, "index.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    # GitHub Pages: don't run Jekyll on the static site
    open(os.path.join(DOCS_DIR, ".nojekyll"), "w").close()
    print(f"Wrote {out}")
    print(f"KPIs: " + " | ".join(f"{k['label']}={k['value']}" for k in data['kpis']))


if __name__ == "__main__":
    main()

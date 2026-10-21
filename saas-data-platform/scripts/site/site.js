// Charts and the "who sees what" switcher for the published site.
// Every number comes from the JSON block build_site.py writes into the page.
(function () {
  "use strict";
  const D = JSON.parse(document.getElementById("site-data").textContent);
  const COL = { blue: "#3a5bff", red: "#ef233c", green: "#12a150", yellow: "#ffb703",
                gray: "#8d99ae", ink: "#101010", muted: "#55565c", line: "#e7e7ea" };
  if (document.body.classList.contains("report"))   // the business-review pages use the report palette
    Object.assign(COL, { blue: "#2f6db0", red: "#c0492b", green: "#1f9d8f", yellow: "#d99a2b", gray: "#9fb0c0", ink: "#12395b", muted: "#5b6b7b", line: "#e2e8f0" });
  const NS = "http://www.w3.org/2000/svg";
  const esc = v => String(v).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const fmtM = v => (v < 0 ? "-" : "") + "$" + Math.abs(v / 1e6).toFixed(1) + "M";
  const fmtK = v => "$" + Math.round(v / 1000) + "k";
  const pct = (v, d = 1) => (v * 100).toFixed(d) + "%";
  const LOCK = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" aria-hidden="true"><rect x="5" y="11" width="14" height="10"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/></svg>';
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const monthName = ym => MONTHS[+ym.slice(5, 7) - 1] + " " + ym.slice(0, 4);

  function svgEl(tag, attrs, parent, text) {
    const e = document.createElementNS(NS, tag);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    if (text != null) e.textContent = text;
    if (parent) parent.appendChild(e);
    return e;
  }
  function niceStep(range, ticks) {
    const raw = range / ticks, mag = Math.pow(10, Math.floor(Math.log10(raw))), n = raw / mag;
    return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * mag;
  }

  // ---- line chart, labels on the line ------------------------------------
  function lineChart(el, cfg) {
    const W = Math.max(300, el.clientWidth), H = cfg.height || 300;
    const m = { l: 56, r: 16, t: 34, b: 30 };
    const pts = cfg.points, n = pts.length;
    const lo = cfg.yMin != null ? cfg.yMin : 0;
    const step = niceStep(Math.max(...pts.map(p => p.y)) - lo, 4);
    const hi = Math.ceil(Math.max(...pts.map(p => p.y)) / step) * step;
    const x = i => m.l + (W - m.l - m.r) * (n === 1 ? 0.5 : i / (n - 1));
    const y = v => m.t + (H - m.t - m.b) * (1 - (v - lo) / (hi - lo));
    el.innerHTML = "";
    const s = svgEl("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": cfg.aria });
    for (let v = lo; v <= hi + 1e-9; v += step) {
      svgEl("line", { x1: m.l, x2: W - m.r, y1: y(v), y2: y(v), class: "grid" }, s);
      svgEl("text", { x: m.l - 8, y: y(v) + 4, "text-anchor": "end" }, s, cfg.fmt(v));
    }
    pts.forEach((p, i) => {
      if (p.x.endsWith("-01") || i === 0)
        svgEl("text", { x: x(i), y: H - 8, "text-anchor": i === 0 ? "start" : "middle" }, s,
              p.x.endsWith("-01") ? p.x.slice(0, 4) : monthName(p.x));
    });
    const d = pts.map((p, i) => (i ? "L" : "M") + x(i).toFixed(1) + " " + y(p.y).toFixed(1)).join(" ");
    svgEl("path", { d: d + ` L${x(n - 1)} ${y(lo)} L${x(0)} ${y(lo)} Z`, fill: cfg.color, opacity: 0.08 }, s);
    svgEl("path", { d, fill: "none", stroke: cfg.color, "stroke-width": 3, "stroke-linejoin": "round" }, s);
    (cfg.marks || []).forEach(mk => {
      const i = mk.i < 0 ? n + mk.i : mk.i, cx = x(i), cy = y(pts[i].y);
      svgEl("circle", { cx, cy, r: 5.5, fill: mk.color || cfg.color, stroke: "#fff", "stroke-width": 2 }, s);
      const anchor = cx > W - 90 ? "end" : cx < m.l + 60 ? "start" : "middle";
      const t = svgEl("text", { x: cx + (anchor === "end" ? 4 : 0), y: mk.below ? cy + 26 : cy - 14, "text-anchor": anchor, class: "lbl lbl-big" }, s, mk.label);
      t.setAttribute("fill", mk.color || COL.ink);
    });
    el.appendChild(s);
  }

  // ---- ARR bridge: movements stacked above and below zero, per year -------
  function bridgeChart(el, cfg) {
    const W = Math.max(300, el.clientWidth), H = cfg.height || 330;
    const m = { l: 56, r: 10, t: 34, b: 50 };
    const cats = cfg.cats, k = cats.length;
    const up = cats.map((_, j) => cfg.series.filter(s => s.values[j] > 0).reduce((a, s) => a + s.values[j], 0));
    const down = cats.map((_, j) => cfg.series.filter(s => s.values[j] < 0).reduce((a, s) => a + s.values[j], 0));
    const step = niceStep(Math.max(...up) - Math.min(0, ...down), 5);
    const hi = Math.ceil(Math.max(...up) / step) * step, lo = Math.floor(Math.min(0, ...down) / step) * step;
    const y = v => m.t + (H - m.t - m.b) * (1 - (v - lo) / (hi - lo));
    const band = (W - m.l - m.r) / k, bw = Math.min(110, band * 0.52);
    el.innerHTML = "";
    const s = svgEl("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": cfg.aria });
    for (let v = lo; v <= hi + 1e-9; v += step) {
      svgEl("line", { x1: m.l, x2: W - m.r, y1: y(v), y2: y(v), class: "grid" }, s);
      svgEl("text", { x: m.l - 8, y: y(v) + 4, "text-anchor": "end" }, s, cfg.fmt(v));
    }
    svgEl("line", { x1: m.l, x2: W - m.r, y1: y(0), y2: y(0), stroke: COL.ink, "stroke-width": 1.5 }, s);
    cats.forEach((c, j) => {
      const cx = m.l + band * (j + 0.5);
      let pos = 0, neg = 0;
      cfg.series.forEach(sr => {
        const v = sr.values[j];
        if (!v) return;
        const a = v > 0 ? pos : neg, b = a + v;
        if (v > 0) pos = b; else neg = b;
        const y0 = y(Math.max(a, b)), hgt = Math.abs(y(a) - y(b));
        svgEl("rect", { x: cx - bw / 2, y: y0, width: bw, height: Math.max(1, hgt), fill: sr.color }, s);
        if (hgt >= 17) svgEl("text", { x: cx, y: y0 + hgt / 2 + 4.5, "text-anchor": "middle", class: "lbl", fill: sr.ink || "#fff" }, s, cfg.fmt(v));
      });
      svgEl("text", { x: cx, y: y(pos) - 9, "text-anchor": "middle", class: "lbl lbl-big" }, s, "+" + cfg.fmt(cfg.net[j]) + " net");
      svgEl("text", { x: cx, y: H - 28, "text-anchor": "middle", class: "lbl" }, s, c);
      svgEl("text", { x: cx, y: H - 10, "text-anchor": "middle" }, s, "ending " + cfg.fmt(cfg.ending[j]));
    });
    el.appendChild(s);
  }

  // ---- horizontal bars (HTML, so labels wrap and scale) --------------------
  function hbars(el, cfg) {
    const max = cfg.max || Math.max(...cfg.rows.filter(r => !r.suppressed).map(r => r.value));
    el.innerHTML = '<div class="bars">' + cfg.rows.map(r => r.suppressed
      ? `<div class="bar sup"><span class="lab">${esc(r.label)}</span><div class="track"><div class="fill"></div></div><span class="val">${esc(r.supText || "<5, hidden")}</span></div>`
      : `<div class="bar"><span class="lab">${esc(r.label)}</span><div class="track"><div class="fill" style="width:${(100 * Math.max(0, r.value) / max).toFixed(1)}%;background:${r.color || COL.gray}"></div>${
          cfg.ref ? `<div class="ref" style="left:${(100 * cfg.ref.value / max).toFixed(1)}%"></div>` : ""}</div><span class="val">${esc(r.text)}</span></div>`).join("") + "</div>" +
      (cfg.ref ? `<div class="reflabel">┆ dashed line: ${esc(cfg.ref.label)}</div>` : "");
  }

  // ---- diverging bars around zero (pay gap by level) -----------------------
  function diverging(el, cfg) {
    const lim = cfg.limit;
    el.innerHTML = '<div class="bars div">' + cfg.rows.map(r => {
      if (r.suppressed)
        return `<div class="bar sup"><span class="lab">${esc(r.label)}</span><div class="track"><div class="axis"></div></div><span class="val">&lt;5, hidden</span></div>`;
      const w = Math.min(50, 50 * Math.abs(r.value) / lim);
      const side = r.value < 0 ? `right:50%` : `left:50%`;
      return `<div class="bar"><span class="lab">${esc(r.label)}</span><div class="track"><div class="${r.value < 0 ? "neg" : "pos"}" style="${side};width:${w.toFixed(1)}%;background:${r.color || COL.gray}"></div><div class="axis"></div></div><span class="val">${(r.value > 0 ? "+" : "") + r.value.toFixed(1)}%</span></div>`;
    }).join("") + "</div>";
  }

  // ---- one 100% bar ---------------------------------------------------------
  function split(el, cfg) {
    const total = cfg.segments.reduce((a, s) => a + s.value, 0);
    el.innerHTML = '<div class="split" role="img" aria-label="' + esc(cfg.aria) + '">' + cfg.segments.map(s => {
      const w = 100 * s.value / total;
      return `<div style="width:${w.toFixed(2)}%;background:${s.color};${s.ink ? "color:" + s.ink : ""}">${w >= 8 ? Math.round(w) + "%" : ""}</div>`;
    }).join("") + '</div><div class="splitkeys">' + cfg.segments.map(s =>
      `<span><i class="dot" style="background:${s.color}"></i><b>${Math.round(100 * s.value / total)}%</b> ${esc(s.label)}</span>`).join("") + "</div>";
  }

  // ---- the charts each page asks for (data-chart="name") --------------------
  const R = D.revenue, P = D.people;
  const CAT = { new_logo: ["New logo", COL.blue], cross_sell: ["Cross-sell", COL.green], upsell: ["Upsell", "#0d7a3c"],
                scheduled: ["Renewal", COL.ink], downgrade: ["Downgrade", COL.yellow], churn: ["Churn", COL.red] };
  const RECON = { missing_in_netsuite: "Missing in NetSuite", amount_mismatch: "Amount mismatch", orphan_in_netsuite: "Orphan in NetSuite",
                  currency_rounding: "Currency rounding", timing_difference: "Timing difference", partially_invoiced: "Partially invoiced" };
  const CHARTS = {
    arr_trend: el => lineChart(el, { points: R.arr_trend.map(r => ({ x: r.ym, y: r.arr })), color: COL.blue,
      fmt: v => "$" + v + "M", aria: "ARR by month",
      marks: [{ i: -1, label: "$" + R.arr_trend[R.arr_trend.length - 1].arr.toFixed(1) + "M", color: COL.blue }] }),
    arr_bridge: el => bridgeChart(el, { cats: R.bridge.map(b => String(b.yr)), aria: "ARR movement by year",
      series: [
        { name: "New logo", color: COL.blue, values: R.bridge.map(b => b.new_logo / 1e6) },
        { name: "Expansion", color: COL.green, values: R.bridge.map(b => b.expansion / 1e6) },
        { name: "Downgrade", color: COL.yellow, ink: COL.ink, values: R.bridge.map(b => b.downgrade / 1e6) },
        { name: "Churn", color: COL.red, values: R.bridge.map(b => b.churn / 1e6) }],
      net: R.bridge.map(b => b.net_new / 1e6), ending: R.bridge.map(b => b.ending / 1e6),
      fmt: v => (v < 0 ? "-$" : "$") + Math.abs(v).toFixed(1) + "M" }),
    usage_split: el => split(el, { aria: "Subscription-months by utilization", segments: [
      { label: "over entitlement: expansion list", value: R.usage.over_ent, color: COL.green },
      { label: "healthy, 50 to 100%", value: R.usage.healthy, color: "#c9ced8", ink: COL.ink },
      { label: "under half: churn risk", value: R.usage.under_util, color: COL.red }] }),
    bookings_cat: el => hbars(el, { rows: R.bookings_cat.map(r => ({ label: (CAT[r.category] || [r.category])[0], value: r.acv,
      color: (CAT[r.category] || [0, COL.gray])[1], text: fmtM(r.acv) })) }),
    bookings_seg: el => hbars(el, { rows: R.bookings_seg.map(r => ({ label: r.segment, value: r.acv,
      color: r.segment === "Mid-Market" ? COL.blue : COL.gray, text: fmtM(r.acv) })) }),
    recon: el => hbars(el, { rows: R.recon.filter(r => r.at_risk >= 1000).map(r => ({ label: RECON[r.category] || r.category,
      value: r.at_risk, color: r.category === "missing_in_netsuite" ? COL.red : COL.gray, text: fmtM(r.at_risk) + " · " + r.n })) }),
    rpe: el => {
      const pts = P.rpe.filter(r => r.ym >= "2024-01").map(r => ({ x: r.ym, y: r.arr_per_employee }));
      const peak = pts.reduce((a, p, i) => (p.y > pts[a].y ? i : a), 0);
      lineChart(el, { points: pts, color: COL.blue, yMin: 140000, fmt: fmtK, aria: "ARR per employee by month",
        marks: [{ i: peak, label: "peak " + fmtK(pts[peak].y), color: COL.blue },
                { i: -1, label: fmtK(pts[pts.length - 1].y), color: COL.red, below: true }] });
    },
    attrition: el => {
      const all = P.departments.find(d => d.department === "All departments");
      hbars(el, { max: 0.35, ref: { value: all.voluntary_attrition_rate_ttm, label: "company, " + pct(all.voluntary_attrition_rate_ttm) },
        rows: P.departments.filter(d => d.department !== "All departments").map(d => d.is_suppressed
          ? { label: d.department, suppressed: true, supText: "<5, hidden" }
          : { label: d.department, value: d.voluntary_attrition_rate_ttm, text: pct(d.voluntary_attrition_rate_ttm),
              color: d.department === "Customer Success" ? COL.red : COL.gray }) });
    },
    pay_gap: el => diverging(el, { limit: 8, rows: P.pay_equity.filter(r => r.gender === "Woman" && r.job_level !== "All").map(r => r.is_suppressed || r.gap_vs_men_pct == null
      ? { label: r.job_level, suppressed: true }
      : { label: r.job_level, value: r.gap_vs_men_pct, color: r.gap_vs_men_pct <= -4 ? COL.red : COL.gray }) })
  };
  const drawn = [];
  document.querySelectorAll("[data-chart]").forEach(el => {
    const f = CHARTS[el.dataset.chart];
    if (f) { f(el); drawn.push([el, f]); }
  });
  let t;
  window.addEventListener("resize", () => { clearTimeout(t); t = setTimeout(() => drawn.forEach(([el, f]) => f(el)), 150); });

  // ---- who sees what ----------------------------------------------------------
  const VERB = { full: "visible", pseudonymize: "pseudonymized", mask: "masked", band: "banded", flag: "away flag only", hide: "hidden" };
  function cell(col, c) {
    if (c.t === "hide") return `<td class="locked"><span class="lock">${LOCK}hidden</span></td>`;
    if (c.v == null) return `<td><span class="none">${col.key === "current_leave_type" ? "none" : ""}</span></td>`;
    if (c.t === "full") {
      const v = col.key === "base_salary" ? "$" + Number(c.v).toLocaleString("en-US") : c.v;
      return `<td>${esc(v)}</td>`;
    }
    return `<td><span class="tx${c.t === "band" ? " band" : ""}">${esc(c.v)}</span></td>`;
  }
  function whoSeesWhat(root) {
    const A = D.access, roles = Object.keys(A.views).concat(["ai_agent"]);
    const label = r => r === "ai_agent" ? "AI agent" : A.views[r].label;
    const bot = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><rect x="4" y="7" width="16" height="12"/><path d="M12 3v4M9 12h.01M15 12h.01M9 16h6"/></svg>';
    root.querySelector(".roles").innerHTML = roles.map(r =>
      `<button type="button" data-role="${r}" aria-pressed="false">${r === "ai_agent" ? bot : ""}${esc(label(r))}</button>`).join("");
    const eng = A.ai.departments.find(d => d.department === "Engineering");
    const small = A.ai.departments.find(d => d.is_suppressed);
    root.querySelector(".ai-bars").innerHTML = "";
    hbars(root.querySelector(".ai-bars"), { rows: A.ai.departments.map(d => d.is_suppressed
      ? { label: d.department, suppressed: true, supText: "<5" }
      : { label: d.department, value: d.headcount, text: String(d.headcount) }) });
    root.querySelector(".chat").innerHTML =
      `<div class="q">What's the average base pay in Engineering?</div>
       <div class="a ok"><span class="why">Answered · band only</span>${esc(eng.avg_base_pay_band)}, across ${eng.headcount} people.</div>
       <div class="q">And on the ${esc(small ? small.department : "smallest")} team?</div>
       <div class="a no"><span class="why">Declined · fewer than 5 people</span>Any number about a group that small could identify someone.</div>
       <div class="q">Who is on medical leave?</div>
       <div class="a no"><span class="why">Declined · health information</span>Leave is visible to HR only. I have no person-level rows.</div>`;
    root.querySelector("thead").innerHTML = "<tr>" + A.columns.map(c => `<th><i class="dot ${c.cls}"></i>${esc(c.label)}</th>`).join("") + "</tr>";
    function render(role) {
      root.querySelectorAll("[data-role]").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.role === role)));
      const ai = role === "ai_agent";
      root.querySelector(".tablebox").hidden = ai;
      root.querySelector(".keys").hidden = ai;
      root.querySelector(".ai").hidden = !ai;
      if (ai) {
        root.querySelector(".big").textContent = "No person-level rows";
        root.querySelector(".what").textContent = A.ai.description;
        root.querySelector(".rules").innerHTML = "";
        return;
      }
      const v = A.views[role];
      root.querySelector(".big").textContent = v.visible === v.total ? `All ${v.total} people` : `${v.visible} of ${v.total} people`;
      root.querySelector(".what").textContent = v.description;
      root.querySelector(".rules").innerHTML = v.rules.map(r => `<span class="rule ${r.t}">${esc(r.label)}: ${VERB[r.t]}</span>`).join("");
      root.querySelector("tbody").innerHTML = v.rows.map(row =>
        "<tr>" + A.columns.map(c => cell(c, row[c.key])).join("") + "</tr>").join("");
    }
    root.querySelectorAll("[data-role]").forEach(b => b.addEventListener("click", () => render(b.dataset.role)));
    render(roles[0]);
  }
  document.querySelectorAll(".wsw").forEach(whoSeesWhat);

  // ---- how it's built: tap a model, see its lineage ---------------------------
  function lineageMap(root) {
    const L = D.lineage, byId = {}, deps = {}, kids = {};
    L.nodes.forEach(n => { byId[n.id] = n; deps[n.id] = n.deps; });
    L.nodes.forEach(n => n.deps.forEach(d => (kids[d] = kids[d] || []).push(n.id)));
    const map = root.querySelector(".lmap"), info = root.querySelector(".linfo");
    map.innerHTML = L.layers.map(l => {
      const ns = L.nodes.filter(n => n.layer === l.key);
      return `<div class="lcol"><h3>${esc(l.label)} <span>${ns.length}</span></h3><div class="sub">${esc(l.sub)}</div><div class="lnodes">` +
        ns.map(n => `<button type="button" class="ln ${n.domain}" data-id="${esc(n.id)}" aria-pressed="false">${n.system ? `<small>${esc(n.system)}</small>` : ""}${esc(n.name)}</button>`).join("") +
        "</div></div>";
    }).join("");
    const svg = document.createElementNS(NS, "svg");
    svg.setAttribute("class", "lsvg");
    svg.setAttribute("aria-hidden", "true");
    map.prepend(svg);
    const walk = (start, next) => {
      const seen = new Set(), stack = [...(next[start] || [])];
      while (stack.length) { const x = stack.pop(); if (!seen.has(x)) { seen.add(x); (next[x] || []).forEach(y => stack.push(y)); } }
      return seen;
    };
    let current = null;
    function draw() {
      svg.innerHTML = "";
      const cols = getComputedStyle(map).gridTemplateColumns.split(" ").length;
      if (!current || cols < 5) return;   // lines only when all five layers sit side by side
      const box = map.getBoundingClientRect(), up = walk(current, deps), down = walk(current, kids);
      L.nodes.forEach(n => n.deps.forEach(d => {
        const onUp = (n.id === current || up.has(n.id)) && up.has(d);
        const onDown = (d === current || down.has(d)) && down.has(n.id);
        if (!onUp && !onDown) return;
        const a = map.querySelector(`[data-id="${CSS.escape(d)}"]`), b = map.querySelector(`[data-id="${CSS.escape(n.id)}"]`);
        if (!a || !b) return;
        const ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect();
        const y1 = ra.top + ra.height / 2 - box.top, y2 = rb.top + rb.height / 2 - box.top;
        let path;
        if (Math.abs(ra.left - rb.left) < 4) {          // same layer: loop out to the left
          const x = ra.left - box.left;
          path = `M${x} ${y1} C${x - 22} ${y1} ${x - 22} ${y2} ${x} ${y2}`;
        } else {
          const x1 = ra.right - box.left, x2 = rb.left - box.left, dx = Math.max(16, (x2 - x1) / 2);
          path = `M${x1} ${y1} C${x1 + dx} ${y1} ${x2 - dx} ${y2} ${x2} ${y2}`;
        }
        svgEl("path", { d: path, stroke: byId[n.id].domain === "people" ? COL.red : COL.blue }, svg);
      }));
    }
    function select(id) {
      current = id;
      const n = byId[id], up = walk(id, deps), down = walk(id, kids);
      map.classList.add("tracing");
      map.querySelectorAll(".ln").forEach(b => {
        const x = b.dataset.id;
        b.classList.toggle("sel", x === id); b.classList.toggle("up", up.has(x)); b.classList.toggle("down", down.has(x));
        b.setAttribute("aria-pressed", String(x === id));
      });
      const layer = L.layers.find(l => l.key === n.layer).label;
      const meta = [layer, n.mat, n.schema, n.access, "owner: " + n.owner].filter(Boolean).map(esc).join(" · ");
      info.innerHTML = `<div><div class="nm">${esc(n.name)}</div><div class="meta">${meta}</div><p>${esc(n.desc || "")}</p></div>` +
        `<div class="counts"><span><b>${up.size}</b>upstream</span><span><b>${down.size}</b>downstream</span><span><b>${n.tests}</b>tests</span>` +
        (n.cols ? `<span><b>${n.cols}</b>documented columns</span>` : "") + "</div>";
      draw();
    }
    map.addEventListener("click", e => { const b = e.target.closest(".ln"); if (b) select(b.dataset.id); });
    let t2;
    window.addEventListener("resize", () => { clearTimeout(t2); t2 = setTimeout(draw, 150); });
    const start = L.nodes.find(n => n.name === "fct_arr") || L.nodes[0];
    select(start.id);
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(draw);
  }
  document.querySelectorAll(".lineage").forEach(lineageMap);
})();

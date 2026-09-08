const STATUS = {
  ok: { icon: "✓", label: "All clear" },
  caution: { icon: "⚠", label: "Minor issues" },
  action: { icon: "✕", label: "Needs attention" },
  unknown: { icon: "?", label: "Status unavailable" },
};

const FRIENDLY_ERROR = "This page could not load its data. Please try again later.";

const el = (tag, cls, text) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text != null) n.textContent = text;
  return n;
};

// Accepts "2025-07-31", "07/31/2025", or an ISO timestamp; falls back to the input.
function fmtDate(raw) {
  if (!raw) return null;
  let d;
  if (/^\d{4}-\d{2}-\d{2}$/.test(raw)) d = new Date(`${raw}T00:00:00`);
  else if (/^\d{2}\/\d{2}\/\d{4}$/.test(raw)) {
    const [m, day, y] = raw.split("/");
    d = new Date(`${y}-${m}-${day}T00:00:00`);
  } else d = new Date(raw);
  if (Number.isNaN(d.getTime())) return raw;
  return d.toLocaleDateString("en-US", { dateStyle: "long" });
}

const chip = (kind, label) => {
  const c = el("span", `chip ${kind}`);
  const dot = el("span", "dot");
  dot.setAttribute("aria-hidden", "true");
  c.append(dot, el("span", null, label));
  return c;
};

function renderVerdict(v, meta) {
  const card = document.getElementById("verdict");
  card.textContent = "";
  card.classList.add(v.status);
  const s = STATUS[v.status] ?? STATUS.unknown;
  const line = el("p", "status-line");
  const icon = el("span", null, s.icon);
  icon.setAttribute("aria-hidden", "true");
  line.append(icon, el("span", null, s.label));
  card.append(line, el("p", "headline", v.headline));

  if (v.open_violations > 0) {
    card.append(el("p", "quarters",
      `${v.open_violations} requirement${v.open_violations === 1 ? " is" : "s are"} currently unresolved — see the list below.`));
  }
  if (v.quarters) {
    const q = v.quarters;
    card.append(el("p", "quarters",
      q.with_violation === 0
        ? `No violations on record in any of the last ${q.total} quarters EPA tracks.`
        : `${q.with_violation} of the last ${q.total} quarters EPA tracks had a violation on record.`));
  }
  // EPA's federal data is a quarterly snapshot; never imply same-day freshness.
  const asof = fmtDate(meta.generated_at);
  card.append(el("p", "asof",
    `Checked against EPA records on ${asof}. EPA data is updated quarterly and can lag ` +
    `state records by several months.` +
    (v.last_inspection ? ` Last state site visit: ${fmtDate(v.last_inspection)}.` : "")));
}

// The build stamps dates; the day count is computed here so it ticks daily
// between weekly builds. UTC math avoids DST off-by-ones.
function daysSince(iso) {
  const t = Date.parse(`${iso}T00:00:00Z`);
  if (Number.isNaN(t)) return null;
  return Math.max(0, Math.floor((Date.now() - t) / 86400000));
}

const REPORTING_STATUS = {
  ok: { icon: "✓", label: "On schedule" },
  caution: { icon: "⚠", label: "Possibly overdue" },
  unknown: { icon: "?", label: "Unknown" },
};

function renderReporting(rep) {
  const card = document.getElementById("reporting");
  card.hidden = false;
  card.classList.add(rep.status);
  const s = REPORTING_STATUS[rep.status] ?? REPORTING_STATUS.unknown;
  const line = el("p", "status-line");
  const icon = el("span", null, s.icon);
  icon.setAttribute("aria-hidden", "true");
  line.append(icon, el("span", null, s.label));
  card.append(line);

  const days = rep.latest_measurement_date ? daysSince(rep.latest_measurement_date) : null;
  if (days != null) {
    card.append(el("p", "days", days.toLocaleString("en-US")));
    card.append(el("p", "days-label",
      `day${days === 1 ? "" : "s"} since the newest publicly available water-quality ` +
      "measurement for this system"));
    const desc = rep.latest_measurement_desc ?? "the most recent measurement was";
    card.append(el("p", "note",
      `${desc.charAt(0).toUpperCase()}${desc.slice(1)} ${fmtDate(rep.latest_measurement_date)}.`));
  } else {
    card.append(el("p", "days-label",
      "We could not determine when measured results were last shared publicly."));
  }
  if (rep.schedule_note) card.append(el("p", "note", rep.schedule_note));
  if (rep.ccr_citation?.note) card.append(el("p", "note", rep.ccr_citation.note));
}

// Severity meter: the fill carries state, the track is a lighter step of the
// same hue. The value always travels as text beside it — never color alone.
function meterRow(label, pct, valueText) {
  const row = el("div", "meter-row");
  const meter = el("div", "meter");
  meter.setAttribute("aria-hidden", "true");
  const fill = el("div", "fill");
  const p = pct ?? 0;
  fill.style.width = `${Math.min(p, 100)}%`;
  if (p > 0) fill.style.minWidth = "2px";
  if (p >= 100) meter.classList.add("over");
  else if (p >= 50) meter.classList.add("warn");
  meter.append(fill);
  row.append(el("span", "meter-label", label), meter, el("span", "meter-value", valueText));
  return row;
}

function renderResults(res) {
  if (!res) return; // card stays hidden; the transparency section explains gaps
  document.getElementById("results-card").hidden = false;
  const mount = document.getElementById("results");
  for (const c of res.contaminants) {
    mount.append(el("h3", "contaminant", c.label));
    mount.append(el("p", "limit-note",
      `Federal limit (${c.limit_label}): ${c.limit} ${c.unit}`));
    for (const p of c.periods) {
      mount.append(meterRow(
        `${fmtDate(p.start) ?? "?"} – ${fmtDate(p.end)}`,
        p.pct_of_limit,
        p.non_detect ? "Not detected" : `${p.display} — ${p.pct_of_limit}% of the limit`,
      ));
    }
  }
  if (!res.copper_published) {
    mount.append(el("p", "footnote",
      "Copper results are not published for this system in EPA’s federal data."));
  }
}

function renderPfas(p) {
  if (!p) return;
  document.getElementById("pfas-card").hidden = false;
  const mount = document.getElementById("pfas");
  mount.append(el("p", null,
    `${p.tested} contaminants were tested; ${p.never_detected} were never detected. ` +
    "Detected contaminants, compared with federal limits where they exist:"));
  for (const c of p.contaminants) {
    const head = el("div", "viol-head");
    head.append(el("h3", "contaminant", c.name));
    if (c.limit == null) head.append(chip("nolimit", "No federal limit set"));
    else if (c.pct_of_limit >= 100) head.append(chip("over", "Above the finalized limit"));
    mount.append(head);
    if (c.limit != null) {
      mount.append(el("p", "limit-note", `Federal limit (${c.limit_label}): ${c.limit} ${c.unit}`));
      mount.append(meterRow(
        "Highest single result",
        c.pct_of_limit,
        `${c.max.value} ${c.unit} — ${c.pct_of_limit}% of the limit`,
      ));
    }
    let caption = `Detected in ${c.detections} of ${c.samples} samples; highest was ` +
      `${c.max.value} ${c.unit}`;
    if (c.max.location) caption += ` at ${c.max.location}`;
    if (c.max.date) caption += ` on ${fmtDate(c.max.date)}`;
    caption += ".";
    if (c.entry_point_averages?.length) {
      caption += " Average by treatment plant: " + c.entry_point_averages
        .map((a) => `${a.location}: ${a.value} ${c.unit}`).join("; ") + ".";
    }
    mount.append(el("p", "result-caption", caption));
  }
  if (p.note) mount.append(el("p", "footnote", p.note));
}

// Site names arrive as "703 Blue Bell Laundry": lead with the place, keep the code.
const siteName = (s) => {
  const m = /^(\d{3})\s+(.+)$/.exec(s ?? "");
  return m ? `${m[2]} (site ${m[1]})` : s;
};

function renderRtk(r) {
  if (!r?.verdict) return;
  document.getElementById("rtk").hidden = false;
  const s = STATUS[r.verdict.status] ?? STATUS.unknown;
  const card = document.getElementById("rtk-verdict");
  card.classList.add(r.verdict.status);
  const line = el("p", "status-line");
  const icon = el("span", null, s.icon);
  icon.setAttribute("aria-hidden", "true");
  line.append(icon, el("span", null, `Lab results, ${fmtDate(r.bacteria.first)} – ${fmtDate(r.bacteria.last)}`));
  card.append(line, el("p", "headline", r.verdict.headline));
  card.append(el("p", "asof",
    `${r.samples} lab samples obtained through a Right-to-Know Law request to Ephrata Borough, ` +
    "answered August 25, 2026. Results were read automatically from the lab's PDF reports " +
    "(M.J. Reider Associates, PA DEP lab #06-00003) and compared with federal limits by this site, " +
    "not by the authority."));

  // Bacteria: counts, then each positive with its follow-up outcome.
  const b = r.bacteria;
  const bm = document.getElementById("rtk-bacteria");
  const tiles = el("div", "tiles");
  for (const [label, value] of [["Routine samples", b.routine_samples], ["Sites", b.sites],
    ["Positive results", b.positives.length]]) {
    const t = el("div", "tile");
    t.append(el("p", "label", label), el("p", "value", String(value)));
    tiles.append(t);
  }
  bm.append(tiles);
  if (b.positives.length) {
    const ul = el("ul", "events");
    for (const p of b.positives) {
      const li = el("li");
      const head = el("div", "viol-head");
      head.append(el("span", "viol-what", `${siteName(p.name)} — ${p.ecoli ? "E. coli" : "total coliform"} found`));
      const clear = p.repeats > 0 && p.repeats_clear;
      head.append(chip(clear ? "resolved" : "health", clear ? "Re-tested clear" : "Follow-up not clear"));
      head.append(el("span", "viol-date", fmtDate(p.date)));
      li.append(head);
      li.append(el("p", "viol-explainer", p.repeats
        ? `${p.repeats} repeat samples on ${fmtDate(p.repeat_date)} were all ${clear ? "clear" : "not clear"}.`
        : "No repeat samples appear in the records provided."));
      ul.append(li);
    }
    bm.append(ul);
    bm.append(el("p", "footnote",
      "A single E. coli result that re-tests clear is not a violation under EPA's coliform rule, " +
      "but it is the kind of result residents are rarely told about. Whether the authority " +
      "issued a public notice is not in these records."));
  }
  const det = el("details");
  det.append(el("summary", null, "All sites tested"));
  const tbl = el("table", "plain-table");
  const hr = el("tr");
  for (const h of ["Site", "Tests", "Positive"]) hr.append(el("th", null, h));
  tbl.append(hr);
  for (const st of b.by_site) {
    const tr = el("tr");
    tr.append(el("td", null, siteName(st.name) || `site ${st.site}`));
    tr.append(el("td", "num", String(st.tests)), el("td", "num", String(st.positives)));
    tbl.append(tr);
  }
  det.append(tbl);
  bm.append(det);

  // Health limits: detected ones get a meter, the rest fold into one line.
  const hm = document.getElementById("rtk-health");
  const detected = r.health.filter((e) => e.detected);
  const nd = r.health.filter((e) => !e.detected);
  for (const e of detected) {
    const head = el("div", "viol-head");
    head.append(el("h3", "contaminant", e.label));
    if (e.max_pct >= 100) head.append(chip("over", "Above the limit"));
    hm.append(head);
    hm.append(el("p", "limit-note", `Federal limit: ${e.limit} ${e.unit}`));
    hm.append(meterRow("Highest result", e.max_pct, `${e.max.display} — ${e.max_pct}% of the limit`));
    hm.append(el("p", "result-caption", e.results.filter((x) => x.tap)
      .map((x) => `${siteName(x.location)}, ${fmtDate(x.date)}: ${x.display}`).join(". ") + "."));
  }
  if (detected.some((e) => e.unit === "ng/L")) hm.append(el("p", "footnote", r.pfas_note));
  if (nd.length) {
    const d = el("details");
    d.append(el("summary", null, `${nd.length} more regulated contaminants were tested and not detected`));
    const ul = el("ul", "monitored");
    for (const e of nd) ul.append(el("li", null, `${e.label} (limit ${e.limit} ${e.unit}, ${e.tap_samples} samples)`));
    d.append(ul);
    hm.append(d);
  }

  // Aesthetic: raw vs finished per plant.
  const am = document.getElementById("rtk-aesthetic");
  for (const e of r.aesthetic) {
    if (!e.by_plant.length) continue;
    const head = el("div", "viol-head");
    head.append(el("h3", "contaminant", e.label));
    if (e.max_pct >= 100) head.append(chip("open", "Above the guideline in treated water"));
    am.append(head);
    am.append(el("p", "limit-note", `Guideline: ${e.limit} ${e.unit}`));
    for (const p of e.by_plant) {
      const short = p.name.replace(/ \(.*\)$/, "");
      if (p.raw) {
        const row = meterRow(`${short}, untreated`, p.raw.pct, `${p.raw.display} — ${p.raw.pct}%`);
        row.querySelector(".meter").className = "meter raw";
        am.append(row);
      }
      am.append(p.finished
        ? meterRow(`${short}, treated`, p.finished.pct, `${p.finished.display} — ${p.finished.pct}%`)
        : meterRow(`${short}, treated`, 0, "Not detected"));
    }
  }
  if (r.hardness) {
    am.append(el("h3", "contaminant", "Hardness"));
    am.append(el("p", "result-caption",
      `Treated water measured ${r.hardness.min}–${r.hardness.max} mg/L as calcium carbonate. ` +
      "Anything over 180 counts as “very hard” on the USGS scale: expect scale in kettles and " +
      "more soap needed. There is no health limit."));
  }

  // Not tap water: one collapsed block per location.
  const nm = document.getElementById("rtk-not-tap");
  for (const loc of r.not_tap) {
    const d = el("details");
    d.append(el("summary", null, loc.location));
    const ul = el("ul", "monitored");
    for (const x of loc.results) {
      ul.append(el("li", null, x.limit != null
        ? `${x.label}: ${x.display} (${x.pct}% of the ${x.unit === "ng/L" ? "limit" : "guideline"} for tap water)`
        : `${x.label}: ${x.display}`));
    }
    d.append(ul);
    nm.append(d);
  }
}

function renderTransparency(t) {
  const mount = document.getElementById("transparency");
  if (t.monitored?.length) {
    mount.append(el("p", "result-caption",
      "Rules and contaminants EPA currently tracks for this system:"));
    const ul = el("ul", "monitored");
    for (const m of t.monitored) ul.append(el("li", null, m));
    mount.append(ul);
  }
  if (t.dfr_url) {
    const link = el("p", "result-caption");
    const a = el("a", null, "EPA’s detailed facility report");
    a.href = t.dfr_url;
    link.append(a, el("span", null, " has the full federal compliance record."));
    mount.append(link);
  }
}

function renderTiles(system) {
  const tiles = document.getElementById("tiles");
  const num = (x) => (typeof x === "number" ? x.toLocaleString("en-US") : "—");
  const items = [
    ["People served", num(system.population_served)],
    ["Homes & businesses", num(system.service_connections)],
    ["Main water source", system.primary_source ?? "—"],
    ["County", system.counties_served ?? "—"],
  ];
  for (const [label, value] of items) {
    const t = el("div", "tile");
    t.append(el("p", "label", label), el("p", "value", value));
    tiles.append(t);
  }
}

function renderViolations(violations) {
  const list = document.getElementById("violations");
  if (!violations) {
    list.append(el("li", null, "Violation records are unavailable right now."));
    return;
  }
  if (!violations.length) {
    list.append(el("li", null, "No violations on record in the recent EPA data."));
    return;
  }
  for (const v of violations) {
    const li = el("li");
    const head = el("div", "viol-head");
    head.append(el("span", "viol-what", v.what));
    // Category and status are orthogonal; a fixed health-based violation
    // must read as fixed, not as a live alarm.
    head.append(chip(v.health_based ? "health" : "paperwork",
      v.health_based ? "Health-based" : "Paperwork"));
    head.append(chip(v.resolved ? "resolved" : "open", v.resolved ? "Resolved" : "Unresolved"));
    head.append(el("span", "viol-date", fmtDate(v.begin_date) ?? ""));
    li.append(head);
    let extra = v.explainer;
    if (v.about && v.about !== v.rule) extra += ` (Related to: ${v.about.toLowerCase()}.)`;
    if (v.resolved && v.resolved_date) extra += ` Fixed as of ${fmtDate(v.resolved_date)}.`;
    li.append(el("p", "viol-explainer", extra));
    // Only MCL-style violations carry a number; show it whenever one exists.
    if (v.measure != null) {
      const unit = v.measure_unit ? ` ${v.measure_unit}` : "";
      let m = `Measured: ${v.measure}${unit}`;
      if (v.state_limit != null) m += ` (limit: ${v.state_limit}${unit})`;
      li.append(el("p", "viol-explainer", m));
    }
    list.append(li);
  }
}

function renderSources(meta) {
  const ul = document.getElementById("sources");
  const names = {
    sdwis: "EPA Safe Drinking Water Information System (Envirofacts)",
    echo: "EPA Enforcement and Compliance History Online (ECHO)",
    ucmr5: "EPA UCMR5 PFAS monitoring results",
    rtk: "Lab reports from a Right-to-Know request to Ephrata Borough",
    interpret: "Data processing",
  };
  for (const [key, s] of Object.entries(meta.sources)) {
    ul.append(el("li", null,
      `${names[key] ?? key}: ${s.ok ? `retrieved ${fmtDate(s.retrieved_at)}` : "unavailable at last update"}`));
  }
}

function showFallback(message) {
  const card = document.getElementById("verdict");
  card.textContent = "";
  card.classList.add("unknown");
  card.append(el("p", "headline", message));
}

async function main() {
  const resp = await fetch("data/water.json");
  if (!resp.ok) throw new Error(`data/water.json returned ${resp.status}`);
  const data = await resp.json();
  const degraded = Object.values(data.meta.sources).some((s) => !s.ok);
  if (degraded) document.getElementById("unavailable").hidden = false;
  renderSources(data.meta);

  if (!data.verdict) {
    showFallback("Current status could not be loaded. Please check back later.");
    return;
  }
  renderVerdict(data.verdict, data.meta);
  // Panels render independently: a bug or gap in one must not take down
  // an already-correct verdict.
  try {
    if (data.reporting) renderReporting(data.reporting);
    if (data.system) renderTiles(data.system);
    renderRtk(data.rtk ?? null);
    renderResults(data.results ?? null);
    renderPfas(data.pfas ?? null);
    renderViolations(data.violations ?? null);
    if (data.transparency) renderTransparency(data.transparency);
  } catch (e) {
    console.error("panel render failed:", e);
    document.getElementById("unavailable").hidden = false;
  }
}

main().catch((e) => {
  console.error(e);
  showFallback(FRIENDLY_ERROR);
});

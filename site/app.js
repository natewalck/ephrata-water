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

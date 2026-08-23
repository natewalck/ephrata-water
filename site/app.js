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
    list.append(li);
  }
}

function renderSources(meta) {
  const ul = document.getElementById("sources");
  const names = {
    sdwis: "EPA Safe Drinking Water Information System (Envirofacts)",
    echo: "EPA Enforcement and Compliance History Online (ECHO)",
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
    if (data.system) renderTiles(data.system);
    renderViolations(data.violations ?? null);
  } catch (e) {
    console.error("panel render failed:", e);
    document.getElementById("unavailable").hidden = false;
  }
}

main().catch((e) => {
  console.error(e);
  showFallback(FRIENDLY_ERROR);
});

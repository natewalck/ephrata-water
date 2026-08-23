const STATUS = {
  ok: { icon: "✓", label: "All clear" },
  caution: { icon: "⚠", label: "Minor issues" },
  action: { icon: "✕", label: "Needs attention" },
};

const el = (tag, cls, text) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text != null) n.textContent = text;
  return n;
};

function renderVerdict(v, meta) {
  const card = document.getElementById("verdict");
  card.textContent = "";
  card.classList.add(v.status);
  const s = STATUS[v.status] ?? STATUS.caution;
  const line = el("p", "status-line");
  line.append(el("span", null, s.icon), el("span", null, s.label));
  card.append(line, el("p", "headline", v.headline));
  const asof = new Date(meta.generated_at).toLocaleDateString("en-US", { dateStyle: "long" });
  card.append(el("p", "asof", `Based on EPA compliance data as of ${asof}. ` +
    (v.last_inspection ? `Last state site visit: ${v.last_inspection}.` : "")));
}

function renderTiles(system) {
  const tiles = document.getElementById("tiles");
  const items = [
    ["People served", system.population_served.toLocaleString("en-US")],
    ["Homes & businesses", system.service_connections.toLocaleString("en-US")],
    ["Main water source", system.primary_source],
    ["County", system.counties_served],
  ];
  for (const [label, value] of items) {
    const t = el("div", "tile");
    t.append(el("p", "label", label), el("p", "value", value ?? "—"));
    tiles.append(t);
  }
}

function renderViolations(violations) {
  const list = document.getElementById("violations");
  if (!violations.length) {
    list.append(el("li", null, "No violations on record in the recent EPA data."));
    return;
  }
  for (const v of violations) {
    const li = el("li");
    const head = el("div", "viol-head");
    head.append(el("span", "viol-what", v.what));
    const chip = el("span", `chip ${v.health_based ? "health" : v.resolved ? "resolved" : "open"}`);
    chip.append(el("span", "dot"),
      el("span", null, v.health_based ? "Health-based" : v.resolved ? "Resolved" : "Unresolved"));
    head.append(chip, el("span", "viol-date", v.begin_date ?? ""));
    li.append(head);
    let extra = v.explainer;
    if (v.about && v.about !== v.rule) extra += ` (Related to: ${v.about.toLowerCase()}.)`;
    if (v.resolved && v.resolved_date) extra += ` Fixed as of ${v.resolved_date}.`;
    li.append(el("p", "viol-explainer", extra));
    list.append(li);
  }
}

function renderSources(meta) {
  const ul = document.getElementById("sources");
  const names = {
    sdwis: "EPA Safe Drinking Water Information System (Envirofacts)",
    echo: "EPA Enforcement and Compliance History Online (ECHO)",
  };
  for (const [key, s] of Object.entries(meta.sources)) {
    ul.append(el("li", null,
      `${names[key] ?? key}: ${s.ok ? `retrieved ${s.retrieved_at}` : "unavailable at last update"}`));
  }
}

async function main() {
  const resp = await fetch("data/water.json");
  const data = await resp.json();
  const degraded = Object.values(data.meta.sources).some((s) => !s.ok);
  if (degraded) document.getElementById("unavailable").hidden = false;
  if (data.verdict) {
    renderVerdict(data.verdict, data.meta);
    renderTiles(data.system);
    renderViolations(data.violations);
  } else {
    document.getElementById("verdict").textContent =
      "Current status could not be loaded. Please check back later.";
  }
  renderSources(data.meta);
}

main().catch((e) => {
  document.getElementById("verdict").textContent = `Could not load data: ${e.message}`;
});

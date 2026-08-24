"""Plain-language layer: turn coded regulatory data into sentences and statuses.

Nothing here fetches; it maps already-retrieved records so it can be tested
offline against fixtures. Either source may be None (fetch failed): every
panel that can still be built is, and the verdict degrades to "unknown"
rather than ever asserting safety from missing evidence.
"""

from __future__ import annotations

import sys
from datetime import UTC, date, datetime, timedelta

from pipeline.common import ref_codes

# Base explainer per violation category. For any non-health-based violation
# the reassurance sentence below is appended -- distinguishing paperwork from
# unsafe water is the whole point, so no category may silently drop it.
CATEGORY_EXPLAINERS = {
    "MCL": "Water contained more of a contaminant than the legal limit allows.",
    "MRDL": "Disinfectant levels in the water were above the allowed maximum.",
    "TT": "A required treatment process was not carried out correctly.",
    "MR": "A required test or report was late, missing, or incomplete.",
    "MON": "A required water test was not done on schedule.",
    "RPT": "A required report was not filed correctly or on time.",
    "Other": "An administrative requirement was not met.",
}
PAPERWORK_NOTE = (
    "This is a paperwork problem, not a measured problem with the water itself."
)

# SDWIS violation_status values that mean the matter is closed. "Addressed"
# means under formal enforcement -- still open, so it is deliberately absent.
CLOSED_STATUSES = {"Resolved", "Archived"}

# Federal lead/copper action levels, mg/L (40 CFR 141.80). The 2024 LCR
# Improvements rule lowers lead to 0.010 mg/L with compliance ~Nov 2027;
# revisit this constant then.
LEAD_ACTION_LEVEL = 0.015
COPPER_ACTION_LEVEL = 1.3
LCR_CONTAMINANTS = {
    "PB90": ("Lead — 90th percentile of household tap samples", LEAD_ACTION_LEVEL),
    "CU90": ("Copper — 90th percentile of household tap samples", COPPER_ACTION_LEVEL),
}
# This system is on reduced triennial lead/copper monitoring (sampled 2016,
# 2019, 2022, 2025). Envirofacts is a quarterly snapshot that can lag state
# records, so allow a grace period before calling a new period overdue.
LCR_CYCLE_YEARS = 3
LCR_GRACE_DAYS = 270

# Consumer Confidence Report violations: the utility's own annual public
# water-quality report was missing (71) or inadequate (72).
CCR_VIOLATION_CODES = {"71", "72"}

# Finalized PFAS limits, ng/L (40 CFR 141 Subpart Z, April 2024). They apply
# to a running annual average per entry point with compliance ~2029-2031, and
# the PFHxS limit is under EPA reconsideration -- copy must stay hedged.
PFAS_MCL_NG_L = {"PFOA": 4.0, "PFOS": 4.0, "PFHxS": 10.0}
PFAS_NOTE = (
    "EPA finalized legal limits for PFOA and PFOS in April 2024. The limits apply to a "
    "running annual average at each treatment plant, and utilities have until 2029–2031 "
    "to comply, so a single sample above the limit is not a violation. Limits for some "
    "other PFAS are under EPA reconsideration."
)


def _date(raw: str | None) -> str | None:
    return raw.split(" ")[0] if raw else None


def _num(raw) -> float | None:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _iso(raw: str | None) -> str | None:
    """Like _date(), but only lets a real ISO date through -- these feed the
    freshness anchor, where a garbage string would compare as "newest"."""
    d = _date(raw)
    if not d:
        return None
    try:
        date.fromisoformat(d)
    except ValueError:
        return None
    return d


def _mdy(raw: str | None) -> str | None:
    """UCMR dates arrive as M/D/YYYY; normalize to ISO or drop them."""
    try:
        return datetime.strptime((raw or "").strip(), "%m/%d/%Y").date().isoformat()
    except ValueError:
        return None


def _pretty(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d:%B} {d.day}, {d.year}"


def _resolved(v: dict) -> bool:
    status = v.get("violation_status")
    if status:
        return status in CLOSED_STATUSES
    return bool(v.get("rtc_date"))


def explain_violation(v: dict, refs: dict[tuple[str, str], str]) -> dict:
    category = v.get("violation_category_code") or "Other"
    health_based = v.get("is_health_based_ind") == "Y"
    explainer = CATEGORY_EXPLAINERS.get(category, CATEGORY_EXPLAINERS["Other"])
    if not health_based:
        explainer = f"{explainer} {PAPERWORK_NOTE}"
    return {
        "id": v.get("violation_id"),
        "begin_date": _date(v.get("compl_per_begin_date")),
        "end_date": _date(v.get("compl_per_end_date")),
        "resolved_date": _date(v.get("rtc_date")),
        "resolved": _resolved(v),
        "health_based": health_based,
        "category": refs.get(("VIOLATION_CATEGORY_CODE", category), category),
        "what": refs.get(("VIOLATION_CODE", v.get("violation_code", "")), "Requirement not met"),
        "about": refs.get(("CONTAMINANT_CODE", v.get("contaminant_code", ""))),
        "rule": refs.get(("RULE_CODE", v.get("rule_code", ""))),
        "explainer": explainer,
        # Measured level vs the limit, when the state attached one (MCL
        # exceedances). Null for paperwork violations -- but a future
        # exceedance's number must never be silently dropped.
        "measure": _num(v.get("viol_measure")),
        "measure_unit": v.get("unit_of_measure"),
        "state_limit": _num(v.get("state_mcl")),
    }


def _quarters(history: str | None) -> dict | None:
    if not history:
        return None
    return {"total": len(history), "with_violation": sum(c != "_" for c in history)}


def verdict(echo_system: dict | None, violations: list[dict] | None) -> dict:
    """The one-sentence answer. Fails toward "unknown", never toward "safe":
    a green verdict requires ECHO's flags to be present and clean."""
    open_violations = [v for v in violations or [] if not v["resolved"]]
    open_health = [v for v in open_violations if v["health_based"]]
    open_paperwork = [v for v in open_violations if not v["health_based"]]

    if open_health or (echo_system and echo_system.get("HealthFlag") == "Yes"):
        status, headline = (
            "action",
            "The water system currently has a health-based violation. Read the details below.",
        )
    elif echo_system and echo_system.get("SNCFlag") == "1":
        status, headline = (
            "action",
            "EPA lists this system as a serious violator. Read the details below.",
        )
    elif echo_system is None:
        # No compliance flags to stand on; open paperwork alone cannot
        # upgrade this to a definitive statement either way.
        status, headline = (
            "unknown",
            "The current compliance status could not be confirmed from EPA records "
            "right now. Check back later.",
        )
    elif open_paperwork:
        status, headline = (
            "caution",
            "The water currently meets all health-based standards, but the system has "
            "unresolved testing or reporting requirements.",
        )
    else:
        status, headline = (
            "ok",
            "Ephrata's water currently meets all federal health-based drinking-water standards.",
        )
    return {
        "status": status,  # ok | caution | action | unknown
        "headline": headline,
        "open_violations": len(open_violations),
        "quarters": _quarters((echo_system or {}).get("SDWA3yrComplQtrsHistory")),
        "last_inspection": (echo_system or {}).get("SDWDateLastVisit"),
    }


def lead_copper_results(samples: list[dict] | None, results: list[dict] | None) -> dict | None:
    """Join LCR_SAMPLE (period dates) to LCR_SAMPLE_RESULT (measured values)
    on sample_id and compare against the federal action level. Returns None
    when either table is missing/empty or nothing joins -- never a fabricated
    series."""
    if not samples or not results:
        return None
    periods = {}
    for s in samples:
        sid, end = s.get("sample_id"), _iso(s.get("sampling_end_date"))
        if sid and end:
            periods[sid] = (_iso(s.get("sampling_start_date")), end)

    # Dedupe on (sample_id, contaminant): a resubmitted result would otherwise
    # double a period. Keep the higher value -- the conservative reading.
    best: dict[tuple[str, str], tuple[float, dict]] = {}
    for r in results:
        sid, code = r.get("sample_id"), r.get("contaminant_code")
        if code not in LCR_CONTAMINANTS or sid not in periods:
            continue
        value = _num(r.get("sample_measure"))
        if value is None:
            continue
        if (sid, code) not in best or value > best[(sid, code)][0]:
            best[(sid, code)] = (value, r)

    series: dict[str, list[dict]] = {}
    units: dict[str, str] = {}
    for (sid, code), (value, r) in best.items():
        start, end = periods[sid]
        limit = LCR_CONTAMINANTS[code][1]
        unit = r.get("unit_of_measure") or "mg/L"
        units.setdefault(code, unit)
        non_detect = value == 0 or r.get("result_sign_code") == "L"
        series.setdefault(code, []).append({
            "start": start,
            "end": end,
            "value": value,
            "non_detect": non_detect,
            "pct_of_limit": 0 if non_detect else round(value / limit * 100),
            "display": "Not detected" if non_detect else f"{value:g} {unit}",
        })
    if not series:
        return None
    contaminants = [
        {
            "code": code,
            "label": LCR_CONTAMINANTS[code][0],
            "unit": units[code],
            "limit": LCR_CONTAMINANTS[code][1],
            "limit_label": "EPA action level",
            "periods": sorted(rows, key=lambda p: p["end"]),
        }
        for code, rows in series.items()
    ]
    return {
        "copper_published": "CU90" in series,
        "contaminants": sorted(contaminants, key=lambda c: c["code"], reverse=True),
    }


def pfas_results(ucmr_rows: list[dict] | None) -> dict | None:
    """Aggregate UCMR5 rows into a per-contaminant measured-vs-limit summary.

    Values arrive in µg/L; PFAS are displayed in ng/L (the unit EPA's limits
    use). Lithium stays in µg/L -- a ng/L lithium number would be nonsense.
    A "<" sign means below the minimum reporting level, i.e. not detected.
    """
    if not ucmr_rows:
        return None
    by_name: dict[str, list[dict]] = {}
    latest = None
    for r in ucmr_rows:
        name = (r.get("Contaminant") or "").strip()
        if not name:
            continue
        by_name.setdefault(name, []).append(r)
        d = _mdy(r.get("CollectionDate"))
        if d and (latest is None or d > latest):
            latest = d

    contaminants = []
    for name, rows in by_name.items():
        in_ng = name.lower() != "lithium"
        scale = 1000 if in_ng else 1

        def val(r, scale=scale):
            v = _num(r.get("AnalyticalResultValue"))
            return None if v is None else round(v * scale, 3)

        detects = [r for r in rows if r.get("AnalyticalResultsSign") == "=" and val(r) is not None]
        if not detects:
            continue
        top = max(detects, key=val)
        limit = PFAS_MCL_NG_L.get(name) if in_ng else None
        detected = set(map(id, detects))
        by_point: dict[str, list[float]] = {}
        for r in rows:
            point = (r.get("SamplePointName") or "").strip() or "Unnamed sample point"
            # Non-detects count as zero, matching the rule's running-annual-
            # average method.
            by_point.setdefault(point, []).append(val(r) if id(r) in detected else 0.0)
        mrl = next((round(m * scale, 3) for r in rows if (m := _num(r.get("MRL"))) is not None),
                   None)
        contaminants.append({
            "name": name,
            "unit": "ng/L" if in_ng else "µg/L",
            "limit": limit,
            "limit_label": "EPA maximum (finalized 2024)" if limit else None,
            "mrl": mrl,
            "samples": len(rows),
            "detections": len(detects),
            "max": {
                "value": val(top),
                "date": _mdy(top.get("CollectionDate")),
                "location": (top.get("SamplePointName") or "").strip() or None,
            },
            "pct_of_limit": round(val(top) / limit * 100) if limit else None,
            "entry_point_averages": [
                {"location": point, "value": round(sum(vals) / len(vals), 2)}
                for point, vals in sorted(by_point.items())
            ],
        })
    if not contaminants:
        return None
    contaminants.sort(key=lambda c: (c["limit"] is None, -(c["pct_of_limit"] or 0), c["name"]))
    return {
        "tested": len(by_name),
        "never_detected": len(by_name) - len(contaminants),
        "latest_sample_date": latest,
        "note": PFAS_NOTE,
        "contaminants": contaminants,
    }


def _plus_years(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year + years)
    except ValueError:  # Feb 29
        return d.replace(year=d.year + years, month=3, day=1)


def reporting_summary(
    results: dict | None,
    pfas: dict | None,
    raw_violations: list[dict] | None,
    *,
    today: date | None = None,
) -> dict:
    """Freshness facts for the "days since the public last got a measurement"
    hero. The day count itself is computed client-side so it ticks daily
    between weekly builds; everything else is derived here."""
    today = today or datetime.now(UTC).date()

    lcr_anchor = None
    for c in (results or {}).get("contaminants", []):
        for p in c["periods"]:
            if p["end"] and (lcr_anchor is None or p["end"] > lcr_anchor):
                lcr_anchor = p["end"]
    pfas_anchor = (pfas or {}).get("latest_sample_date")
    anchor = max(filter(None, [lcr_anchor, pfas_anchor]), default=None)

    if anchor is None:
        status, desc, next_by, note = "unknown", None, None, None
    else:
        desc = (
            "the most recent lead testing period reported to EPA ended"
            if anchor == lcr_anchor
            else "the most recent PFAS sample reported to EPA was collected"
        )
        if lcr_anchor is None:
            # A PFAS date alone says nothing about the ongoing monitoring
            # schedule; report the date but not an on-schedule claim.
            status, next_by, note = "unknown", None, None
        else:
            next_due = _plus_years(date.fromisoformat(lcr_anchor), LCR_CYCLE_YEARS)
            next_by = next_due.isoformat()
            overdue = today > next_due + timedelta(days=LCR_GRACE_DAYS)
            # Never "action": slow public data is a transparency problem,
            # not a health signal.
            status = "caution" if overdue else "ok"
            note = (
                "Under the federal Lead and Copper Rule, Ephrata Area Joint Authority is on "
                f"a reduced monitoring schedule, so new lead measurements only become public "
                f"about every {LCR_CYCLE_YEARS} years. "
                + (
                    f"A new testing period was due by {_pretty(next_by)} and has not "
                    "appeared in EPA's records yet."
                    if overdue
                    else f"The next testing period is due by {_pretty(next_by)}."
                )
            )

    ccr = None
    ccr_rows = [
        v for v in raw_violations or []
        if str(v.get("violation_code") or "").strip() in CCR_VIOLATION_CODES
    ]
    if ccr_rows:
        newest = max(ccr_rows, key=lambda v: v.get("compl_per_begin_date") or "")
        begin = _date(newest.get("compl_per_begin_date"))
        resolved = _date(newest.get("rtc_date"))
        year = begin[:4] if begin else "recent years"
        ccr = {
            "begin_date": begin,
            "resolved_date": resolved,
            "note": (
                f"In {year}, regulators cited Ephrata Area Joint Authority over its annual "
                "Consumer Confidence Report — the utility's own public water-quality report."
                + (f" The citation was resolved on {_pretty(resolved)}." if resolved else "")
            ),
        }

    return {
        "status": status,
        "latest_measurement_date": anchor,
        "latest_measurement_desc": desc,
        "next_expected_by": next_by,
        "schedule_note": note,
        "ccr_citation": ccr,
    }


def transparency(echo_system: dict | None, refs: dict[tuple[str, str], str]) -> dict:
    """Dynamic facts for the "what the public can and cannot see" card."""
    monitored = []
    for part in ((echo_system or {}).get("SDWAContaminants") or "").split(";"):
        part = part.strip()
        if not part:
            continue
        code, _, desc = part.partition("=")
        monitored.append(desc.strip() or refs.get(("CONTAMINANT_CODE", code.strip()), code.strip()))
    return {"monitored": monitored, "dfr_url": (echo_system or {}).get("DfrUrl")}


def _safe(section: str, fn, *args):
    """Panels degrade independently on the Python side too: a bug in one
    derived section must not take down the verdict (build.py would drop the
    whole payload if interpret() raised)."""
    try:
        return fn(*args)
    except Exception as e:  # noqa: BLE001
        print(f"warning: {section} interpretation failed: {e}", file=sys.stderr)
        return None


def interpret(sdwis: dict | None, echo: dict | None, ucmr: list[dict] | None = None) -> dict:
    refs = ref_codes()
    echo_system = echo["system"] if echo else None
    data: dict = {}
    violations = None
    if sdwis:
        violations = sorted(
            (explain_violation(v, refs) for v in sdwis["violations"]),
            key=lambda v: v["begin_date"] or "",
            reverse=True,
        )
        data["violations"] = violations
        ws = sdwis["water_system"][0]
        data["system"] = {
            "name": (ws.get("pws_name") or "Unknown system").title(),
            "pwsid": ws.get("pwsid"),
            "population_served": ws.get("population_served_count"),
            "service_connections": ws.get("service_connections_count"),
            "primary_source": (echo_system or {}).get("PrimarySourceDesc"),
            "counties_served": (echo_system or {}).get("CountiesServed"),
        }
    data["verdict"] = verdict(echo_system, violations)

    results = _safe(
        "lead/copper",
        lead_copper_results,
        (sdwis or {}).get("lcr_samples"),
        (sdwis or {}).get("lcr_sample_results"),
    )
    if results:
        data["results"] = results
    pfas = _safe("pfas", pfas_results, ucmr)
    if pfas:
        data["pfas"] = pfas
    reporting = _safe(
        "reporting", reporting_summary, results, pfas, (sdwis or {}).get("violations")
    )
    if reporting:
        data["reporting"] = reporting
    trans = _safe("transparency", transparency, echo_system, refs)
    if trans:
        data["transparency"] = trans
    return data

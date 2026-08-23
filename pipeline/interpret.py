"""Plain-language layer: turn coded regulatory data into sentences and statuses.

Nothing here fetches; it maps already-retrieved records so it can be tested
offline against fixtures. Either source may be None (fetch failed): every
panel that can still be built is, and the verdict degrades to "unknown"
rather than ever asserting safety from missing evidence.
"""

from __future__ import annotations

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


def _date(raw: str | None) -> str | None:
    return raw.split(" ")[0] if raw else None


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


def interpret(sdwis: dict | None, echo: dict | None) -> dict:
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
    return data

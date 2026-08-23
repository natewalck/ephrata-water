"""Plain-language layer: turn coded regulatory data into sentences and statuses.

Nothing here fetches; it maps already-retrieved records so it can be tested
offline against fixtures.
"""

from __future__ import annotations

from pipeline.common import ref_codes

# What a violation category means for a non-technical reader. Health-based
# categories (MCL/MRDL/TT) are worded differently from paperwork ones on
# purpose: conflating them is the #1 way water dashboards mislead people.
CATEGORY_EXPLAINERS = {
    "MCL": "Water contained more of a contaminant than the legal limit allows.",
    "MRDL": "Disinfectant levels in the water were above the allowed maximum.",
    "TT": "A required treatment process was not carried out correctly.",
    "MR": "A required test or report was late, missing, or incomplete. "
    "This is a paperwork problem, not a measured problem with the water itself.",
    "MON": "A required water test was not done on schedule. "
    "This is a paperwork problem, not a measured problem with the water itself.",
    "RPT": "A required report was not filed correctly or on time. "
    "This is a paperwork problem, not a measured problem with the water itself.",
    "Other": "An administrative requirement was not met.",
}


def _date(raw: str | None) -> str | None:
    return raw.split(" ")[0] if raw else None


def explain_violation(v: dict, refs: dict[tuple[str, str], str]) -> dict:
    category = v.get("violation_category_code") or "Other"
    health_based = v.get("is_health_based_ind") == "Y"
    resolved = v.get("rtc_date") is not None
    return {
        "id": v.get("violation_id"),
        "begin_date": _date(v.get("compl_per_begin_date")),
        "end_date": _date(v.get("compl_per_end_date")),
        "resolved_date": _date(v.get("rtc_date")),
        "resolved": resolved,
        "health_based": health_based,
        "category": refs.get(("VIOLATION_CATEGORY_CODE", category), category),
        "what": refs.get(("VIOLATION_CODE", v.get("violation_code", "")), "Requirement not met"),
        "about": refs.get(("CONTAMINANT_CODE", v.get("contaminant_code", ""))),
        "rule": refs.get(("RULE_CODE", v.get("rule_code", ""))),
        "explainer": CATEGORY_EXPLAINERS.get(category, CATEGORY_EXPLAINERS["Other"]),
    }


def verdict(echo_system: dict, violations: list[dict]) -> dict:
    """The one-sentence answer, derived from ECHO's current compliance flags."""
    health_now = echo_system.get("HealthFlag") == "Yes"
    serious = echo_system.get("SNCFlag") == "1"
    open_violations = [v for v in violations if not v["resolved"]]
    open_paperwork = [v for v in open_violations if not v["health_based"]]

    if health_now or any(v["health_based"] for v in open_violations):
        status, headline = (
            "action",
            "The water system currently has a health-based violation. Read the details below.",
        )
    elif serious:
        status, headline = (
            "action",
            "EPA lists this system as a serious violator. Read the details below.",
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
            "Ephrata's water currently meets all federal and state health-based standards.",
        )
    return {
        "status": status,  # ok | caution | action
        "headline": headline,
        "open_violations": len(open_violations),
        "quarters_history": echo_system.get("SDWA3yrComplQtrsHistory"),
        "last_inspection": echo_system.get("SDWDateLastVisit"),
    }


def interpret(sdwis: dict, echo: dict) -> dict:
    refs = ref_codes()
    violations = sorted(
        (explain_violation(v, refs) for v in sdwis["violations"]),
        key=lambda v: v["begin_date"] or "",
        reverse=True,
    )
    ws = sdwis["water_system"][0]
    return {
        "system": {
            "name": ws["pws_name"].title(),
            "pwsid": ws["pwsid"],
            "population_served": ws["population_served_count"],
            "service_connections": ws["service_connections_count"],
            "primary_source": echo["system"].get("PrimarySourceDesc"),
            "counties_served": echo["system"].get("CountiesServed"),
        },
        "verdict": verdict(echo["system"], violations),
        "violations": violations,
    }

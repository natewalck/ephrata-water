"""EPA ECHO SDW services: quarterly compliance status and enforcement summary.

Docs: https://echo.epa.gov/tools/web-services
Note: the PWSID parameter is `p_pid`; QIDs expire in ~30 minutes, so the
qid-based detail fetch happens in the same run as get_systems.
"""

from __future__ import annotations

from pipeline.common import PWSID, FetchError, get_json

BASE = "https://echodata.epa.gov/echo"

# The verdict hangs off these; validate them at the boundary so a renamed or
# dropped field degrades the source instead of silently reading as "safe".
REQUIRED_FLAGS = {"HealthFlag": {"Yes", "No"}, "SNCFlag": {"0", "1"}}


def fetch(pwsid: str = PWSID) -> dict:
    summary = get_json(f"{BASE}/sdw_rest_services.get_systems", output="JSON", p_pid=pwsid)
    if not isinstance(summary, dict):
        raise FetchError(f"ECHO get_systems: expected object, got {str(summary)[:200]}")
    results = summary.get("Results", {})
    if results.get("Message") != "Success":
        raise FetchError(f"ECHO get_systems: {results.get('Error', results)}")
    qid = results.get("QueryID")
    if not qid:
        raise FetchError("ECHO get_systems: no QueryID in response")
    detail = get_json(f"{BASE}/sdw_rest_services.get_qid", output="JSON", qid=qid)
    if not isinstance(detail, dict):
        raise FetchError(f"ECHO get_qid: expected object, got {str(detail)[:200]}")
    rows = detail.get("Results", {}).get("WaterSystems", [])
    if not rows:
        raise FetchError("ECHO get_qid returned no systems")
    system = rows[0]
    for field, allowed in REQUIRED_FLAGS.items():
        if system.get(field) not in allowed:
            raise FetchError(f"ECHO {field} missing or unrecognized: {system.get(field)!r}")
    return {"summary": results, "system": system}

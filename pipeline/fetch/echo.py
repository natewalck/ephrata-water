"""EPA ECHO SDW services: quarterly compliance status and enforcement summary.

Docs: https://echo.epa.gov/tools/web-services
Note: the PWSID parameter is `p_pid`; QIDs expire in ~30 minutes, so the
qid-based detail fetch happens in the same run as get_systems.
"""

from __future__ import annotations

from pipeline.common import PWSID, FetchError, get_json

BASE = "https://echodata.epa.gov/echo"


def fetch(pwsid: str = PWSID) -> dict:
    summary = get_json(f"{BASE}/sdw_rest_services.get_systems", output="JSON", p_pid=pwsid)
    results = summary.get("Results", {})
    if results.get("Message") != "Success":
        raise FetchError(f"ECHO get_systems: {results.get('Error', results)}")
    qid = results["QueryID"]
    detail = get_json(f"{BASE}/sdw_rest_services.get_qid", output="JSON", qid=qid)
    rows = detail.get("Results", {}).get("WaterSystems", [])
    if not rows:
        raise FetchError("ECHO get_qid returned no systems")
    return {"summary": results, "system": rows[0]}

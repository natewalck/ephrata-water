"""EPA Envirofacts SDWIS: system inventory, violations, lead/copper summaries.

Docs: https://www.epa.gov/enviro/envirofacts-data-service-api
Quarterly snapshots of state-reported data; no API key.
"""

from __future__ import annotations

from pipeline.common import PWSID, FetchError, get_json

BASE = "https://data.epa.gov/efservice"

TABLES = {
    "water_system": "WATER_SYSTEM",
    "facilities": "WATER_SYSTEM_FACILITY",
    "violations": "VIOLATION",
    "enforcement": "ENFORCEMENT_ACTION",
    "lcr_samples": "LCR_SAMPLE_RESULT",
    "geographic_areas": "GEOGRAPHIC_AREA",
}


def fetch(pwsid: str = PWSID) -> dict[str, list[dict]]:
    out = {}
    for key, table in TABLES.items():
        rows = get_json(f"{BASE}/{table}/PWSID/{pwsid}/JSON")
        # Envirofacts reports errors as 200-status JSON dicts. Never coerce
        # those to "no data" -- an error must not read as a clean record.
        if not isinstance(rows, list):
            raise FetchError(f"SDWIS {table}: expected list, got {str(rows)[:200]}")
        out[key] = rows
    # This system verifiably has one WATER_SYSTEM row and a decade of
    # violation records; zero rows for either means the query silently
    # failed, not that the water is pristine. Fail closed.
    if not out["water_system"]:
        raise FetchError("SDWIS WATER_SYSTEM returned no rows for a known-active system")
    if not out["violations"]:
        raise FetchError("SDWIS VIOLATION returned no rows; known history says otherwise")
    return out

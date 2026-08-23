"""EPA Envirofacts SDWIS: system inventory, violations, lead/copper summaries.

Docs: https://www.epa.gov/enviro/envirofacts-data-service-api
Quarterly snapshots of state-reported data; no API key.
"""

from __future__ import annotations

from pipeline.common import PWSID, get_json

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
        if not isinstance(rows, list):
            rows = []
        out[key] = rows
    return out

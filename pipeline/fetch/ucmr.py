"""EPA UCMR5 occurrence data: measured PFAS and lithium results, bulk export.

Docs: https://www.epa.gov/dwucmr/occurrence-data-unregulated-contaminant-monitoring-rule
EPA updates this zip in place (the path says 2023-08 but the content is
current). The text members are tab-delimited and latin-1 encoded -- the
"µ" in "µg/L" is not valid UTF-8, so the encoding here is load-bearing.
"""

from __future__ import annotations

import csv
import io
import tempfile
import zipfile

import requests

from pipeline.common import PWSID, FetchError, session

ZIP_URL = "https://www.epa.gov/system/files/other-files/2023-08/ucmr5-occurrence-data-by-state.zip"
DOWNLOAD_TIMEOUT = 300  # a ~13 MB file download, not an API round trip

# pfas_results() reads these; a renamed column must degrade the source,
# never silently produce an empty panel.
REQUIRED_COLUMNS = {
    "PWSID",
    "Contaminant",
    "MRL",
    "Units",
    "AnalyticalResultsSign",
    "AnalyticalResultValue",
    "CollectionDate",
    "SamplePointName",
}


def fetch(pwsid: str = PWSID) -> list[dict]:
    rows: list[dict] = []
    try:
        with tempfile.TemporaryFile() as tmp:
            with session.get(ZIP_URL, stream=True, timeout=DOWNLOAD_TIMEOUT) as resp:
                resp.raise_for_status()
                for chunk in resp.iter_content(1 << 20):
                    tmp.write(chunk)
            tmp.seek(0)
            with zipfile.ZipFile(tmp) as zf:
                # The state split ("MA_WY" / "Tribes_AK_LA") is EPA's choice and
                # could change; read every UCMR5_All_* member rather than guessing.
                members = [
                    n for n in zf.namelist() if n.startswith("UCMR5_All") and n.endswith(".txt")
                ]
                if not members:
                    raise FetchError("UCMR5 zip contains no UCMR5_All_*.txt members")
                for name in members:
                    with zf.open(name) as raw:
                        text = io.TextIOWrapper(raw, encoding="latin-1")
                        reader = csv.DictReader(text, delimiter="\t")
                        missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
                        if missing:
                            raise FetchError(f"UCMR5 {name}: missing columns {sorted(missing)}")
                        rows.extend(r for r in reader if r.get("PWSID") == pwsid)
    except (requests.RequestException, zipfile.BadZipFile, OSError) as e:
        raise FetchError(f"{ZIP_URL}: {e}") from e
    # This system verifiably participated in UCMR5 (240 rows as of Feb 2026);
    # zero rows means the filter or file broke, not that nothing was tested.
    if not rows:
        raise FetchError(f"UCMR5 export has no rows for {pwsid}")
    return rows

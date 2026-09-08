"""Build site/data/water.json from all sources. Each source fails independently.

Exit code matters: 0 means the payload has at least a usable verdict and may
be deployed; 1 means nothing useful was produced, so the deploy should be
skipped and the previously published site left standing.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from pipeline import rtk
from pipeline.common import now_utc
from pipeline.fetch import echo, sdwis, ucmr
from pipeline.interpret import interpret

SITE_DATA = Path(__file__).parent.parent / "site" / "data"
# Lab results from a Right-to-Know request: static, committed, one file per
# request. The window is the sampling period the request covered.
RTK_FILE = Path(__file__).parent / "refdata" / "rtk_2026-08.json"
RTK_WINDOW = ("2026-05-01", "2026-08-31")


def main() -> int:
    SITE_DATA.mkdir(parents=True, exist_ok=True)
    sources: dict[str, dict] = {}
    raw: dict[str, dict] = {}

    fetchers = {"sdwis": sdwis.fetch, "echo": echo.fetch, "ucmr5": ucmr.fetch}
    for name, fetcher in fetchers.items():
        # Broad catch on purpose: upstream shape drift raises KeyError and
        # friends, and any of those must degrade one source, not the build.
        try:
            raw[name] = fetcher()
            sources[name] = {"ok": True, "retrieved_at": now_utc()}
        except Exception as e:  # noqa: BLE001
            print(f"warning: {name} unavailable: {e}", file=sys.stderr)
            sources[name] = {"ok": False, "error": str(e), "retrieved_at": now_utc()}

    try:
        data = interpret(raw.get("sdwis"), raw.get("echo"), raw.get("ucmr5"))
    except Exception as e:  # noqa: BLE001
        print(f"warning: interpret failed: {e}", file=sys.stderr)
        data = {}
        sources["interpret"] = {"ok": False, "error": str(e), "retrieved_at": now_utc()}

    try:
        data["rtk"] = rtk.summarize(json.loads(RTK_FILE.read_text()), *RTK_WINDOW)
        sources["rtk"] = {"ok": True, "retrieved_at": "2026-08-25T00:00:00Z"}
    except Exception as e:  # noqa: BLE001
        print(f"warning: rtk unavailable: {e}", file=sys.stderr)
        sources["rtk"] = {"ok": False, "error": str(e), "retrieved_at": now_utc()}

    data["meta"] = {"generated_at": now_utc(), "sources": sources}
    out = SITE_DATA / "water.json"
    out.write_text(json.dumps(data, indent=1) + "\n")

    # RTK data is static and always loads; it must not make a dead-fetch build deployable.
    usable = "verdict" in data and any(s["ok"] for k, s in sources.items() if k != "rtk")
    print(f"wrote {out} ({out.stat().st_size} bytes){'' if usable else ' -- NOT deployable'}")
    return 0 if usable else 1


if __name__ == "__main__":
    sys.exit(main())

"""Build site/data/water.json from all sources. Each source fails independently.

Exit code matters: 0 means the payload has at least a usable verdict and may
be deployed; 1 means nothing useful was produced, so the deploy should be
skipped and the previously published site left standing.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from pipeline.common import now_utc
from pipeline.fetch import echo, sdwis, ucmr
from pipeline.interpret import interpret

SITE_DATA = Path(__file__).parent.parent / "site" / "data"


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

    data["meta"] = {"generated_at": now_utc(), "sources": sources}
    out = SITE_DATA / "water.json"
    out.write_text(json.dumps(data, indent=1) + "\n")

    usable = "verdict" in data and any(s["ok"] for s in sources.values())
    print(f"wrote {out} ({out.stat().st_size} bytes){'' if usable else ' -- NOT deployable'}")
    return 0 if usable else 1


if __name__ == "__main__":
    sys.exit(main())

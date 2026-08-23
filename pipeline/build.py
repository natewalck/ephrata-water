"""Build site/data/*.json from all sources. Each source fails independently."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from pipeline.common import FetchError, now_utc
from pipeline.fetch import echo, sdwis
from pipeline.interpret import interpret

SITE_DATA = Path(__file__).parent.parent / "site" / "data"


def main() -> int:
    SITE_DATA.mkdir(parents=True, exist_ok=True)
    sources: dict[str, dict] = {}
    raw: dict[str, dict] = {}

    for name, fetcher in {"sdwis": sdwis.fetch, "echo": echo.fetch}.items():
        try:
            raw[name] = fetcher()
            sources[name] = {"ok": True, "retrieved_at": now_utc()}
        except FetchError as e:
            print(f"warning: {name} unavailable: {e}", file=sys.stderr)
            sources[name] = {"ok": False, "error": str(e), "retrieved_at": now_utc()}

    # On any source failure the build degrades: the site shows an unavailable banner.
    ok = all(s["ok"] for s in sources.values())
    data = interpret(raw["sdwis"], raw["echo"]) if ok else {}

    data["meta"] = {"generated_at": now_utc(), "sources": sources}
    out = SITE_DATA / "water.json"
    out.write_text(json.dumps(data, indent=1) + "\n")
    print(f"wrote {out} ({out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Shared plumbing for all fetchers."""

from __future__ import annotations

import csv
from datetime import UTC, datetime
from pathlib import Path

import requests

PWSID = "PA7360045"
TIMEOUT = 60
REFDATA = Path(__file__).parent / "refdata"

session = requests.Session()
session.headers["User-Agent"] = "ephrata-water (github.com/natewalck/ephrata-water)"


class FetchError(Exception):
    """A source could not be retrieved; the build degrades that panel."""


def get_json(url: str, **params) -> object:
    try:
        resp = session.get(url, params=params or None, timeout=TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except (requests.RequestException, ValueError) as e:
        raise FetchError(f"{url}: {e}") from e


def now_utc() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def ref_codes() -> dict[tuple[str, str], str]:
    """(value_type, code) -> description, from the vendored SDWA reference CSV."""
    out: dict[tuple[str, str], str] = {}
    with open(REFDATA / "sdwa_ref_codes.csv", newline="") as f:
        for row in csv.DictReader(f):
            out[(row["VALUE_TYPE"], row["VALUE_CODE"])] = row["VALUE_DESCRIPTION"]
    return out

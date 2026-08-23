"""build.py degradation: one source down -> partial payload, exit 0;
everything down -> no deploy (exit 1)."""

import json

import pytest

from pipeline import build
from pipeline.common import FetchError


@pytest.fixture
def out_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(build, "SITE_DATA", tmp_path)
    return tmp_path


def _load(out_dir):
    return json.loads((out_dir / "water.json").read_text())


def test_one_source_down_still_deploys(out_dir, monkeypatch):
    monkeypatch.setattr(build.sdwis, "fetch", lambda: {
        "water_system": [{"pws_name": "TEST", "pwsid": "X", "population_served_count": 1,
                          "service_connections_count": 1}],
        "violations": [],
    })
    monkeypatch.setattr(build.echo, "fetch", lambda: (_ for _ in ()).throw(FetchError("down")))
    assert build.main() == 0
    data = _load(out_dir)
    assert data["meta"]["sources"]["echo"]["ok"] is False
    assert data["verdict"]["status"] == "unknown"
    assert data["system"]["name"] == "Test"


def test_unexpected_exception_degrades_not_crashes(out_dir, monkeypatch):
    # Shape drift raises KeyError and friends, not just FetchError.
    monkeypatch.setattr(build.sdwis, "fetch", lambda: (_ for _ in ()).throw(KeyError("gone")))
    monkeypatch.setattr(build.echo, "fetch", lambda: {"system": {
        "HealthFlag": "No", "SNCFlag": "0"}})
    assert build.main() == 0
    data = _load(out_dir)
    assert data["meta"]["sources"]["sdwis"]["ok"] is False
    assert data["verdict"]["status"] == "ok"


def test_all_sources_down_exits_nonzero(out_dir, monkeypatch):
    monkeypatch.setattr(build.sdwis, "fetch", lambda: (_ for _ in ()).throw(FetchError("down")))
    monkeypatch.setattr(build.echo, "fetch", lambda: (_ for _ in ()).throw(FetchError("down")))
    assert build.main() == 1

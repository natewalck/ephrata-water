"""build.py degradation: one source down -> partial payload, exit 0;
everything down -> no deploy (exit 1)."""

import json

import pytest

from pipeline import build
from pipeline.common import FetchError


@pytest.fixture
def out_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(build, "SITE_DATA", tmp_path)
    # UCMR is down unless a test wires it up: keeps every test offline.
    monkeypatch.setattr(build.ucmr, "fetch", lambda: (_ for _ in ()).throw(FetchError("down")))
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


def _fixture(name):
    from pathlib import Path

    return json.loads((Path(__file__).parent / "fixtures" / name).read_text())


def test_new_keys_survive_build(out_dir, monkeypatch):
    monkeypatch.setattr(build.sdwis, "fetch", lambda: {
        "water_system": [_fixture("sdwis_water_system.json")],
        "violations": _fixture("sdwis_violations.json"),
        "lcr_samples": _fixture("lcr_samples.json"),
        "lcr_sample_results": _fixture("lcr_sample_results.json"),
    })
    monkeypatch.setattr(build.echo, "fetch", lambda: {"system": _fixture("echo_system.json")})
    monkeypatch.setattr(build.ucmr, "fetch", lambda: _fixture("ucmr5_rows.json"))
    assert build.main() == 0
    data = _load(out_dir)
    assert data["results"]["contaminants"][0]["code"] == "PB90"
    assert data["pfas"]["contaminants"][0]["name"] == "PFOA"
    assert data["reporting"]["status"] in {"ok", "caution"}
    assert data["transparency"]["monitored"]
    assert data["meta"]["sources"]["ucmr5"]["ok"] is True


def test_empty_lcr_tables_still_deploy(out_dir, monkeypatch):
    monkeypatch.setattr(build.sdwis, "fetch", lambda: {
        "water_system": [_fixture("sdwis_water_system.json")],
        "violations": [],
        "lcr_samples": [],
        "lcr_sample_results": [],
    })
    monkeypatch.setattr(build.echo, "fetch", lambda: {"system": {
        "HealthFlag": "No", "SNCFlag": "0"}})
    assert build.main() == 0
    data = _load(out_dir)
    assert "results" not in data
    assert data["reporting"]["status"] == "unknown"
    assert data["verdict"]["status"] == "ok"


def test_ucmr_down_degrades_only_that_source(out_dir, monkeypatch):
    monkeypatch.setattr(build.sdwis, "fetch", lambda: {
        "water_system": [_fixture("sdwis_water_system.json")],
        "violations": _fixture("sdwis_violations.json"),
    })
    monkeypatch.setattr(build.echo, "fetch", lambda: {"system": _fixture("echo_system.json")})
    assert build.main() == 0
    data = _load(out_dir)
    assert data["meta"]["sources"]["ucmr5"]["ok"] is False
    assert "pfas" not in data
    assert data["verdict"]["status"] in {"ok", "caution"}

"""Fetchers must fail closed: an error response can never read as clean data."""

import pytest

from pipeline.common import FetchError
from pipeline.fetch import echo, sdwis


def test_sdwis_error_dict_raises(monkeypatch):
    # Envirofacts reports errors as 200-status JSON dicts.
    monkeypatch.setattr(
        "pipeline.fetch.sdwis.get_json", lambda url: {"error": "table not available"}
    )
    with pytest.raises(FetchError, match="expected list"):
        sdwis.fetch()


def test_sdwis_empty_water_system_raises(monkeypatch):
    monkeypatch.setattr("pipeline.fetch.sdwis.get_json", lambda url: [])
    with pytest.raises(FetchError, match="no rows"):
        sdwis.fetch()


def test_echo_missing_flags_raise(monkeypatch):
    def fake(url, **params):
        if "get_systems" in url:
            return {"Results": {"Message": "Success", "QueryID": "1"}}
        return {"Results": {"WaterSystems": [{"PWSName": "X"}]}}  # no HealthFlag/SNCFlag

    monkeypatch.setattr("pipeline.fetch.echo.get_json", fake)
    with pytest.raises(FetchError, match="HealthFlag"):
        echo.fetch()


def test_echo_unrecognized_flag_value_raises(monkeypatch):
    def fake(url, **params):
        if "get_systems" in url:
            return {"Results": {"Message": "Success", "QueryID": "1"}}
        return {"Results": {"WaterSystems": [{"HealthFlag": "Maybe", "SNCFlag": "0"}]}}

    monkeypatch.setattr("pipeline.fetch.echo.get_json", fake)
    with pytest.raises(FetchError, match="HealthFlag"):
        echo.fetch()

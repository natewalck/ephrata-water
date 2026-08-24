"""Fetchers must fail closed: an error response can never read as clean data."""

import io
import zipfile

import pytest

from pipeline.common import FetchError
from pipeline.fetch import echo, sdwis, ucmr


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


def test_sdwis_lcr_tables_mapped_correctly():
    # A silent swap of these two would join values to the wrong periods.
    assert sdwis.TABLES["lcr_samples"] == "LCR_SAMPLE"
    assert sdwis.TABLES["lcr_sample_results"] == "LCR_SAMPLE_RESULT"


# --- UCMR5 bulk export ---

UCMR_HEADER = (
    "PWSID\tPWSName\tSamplePointName\tCollectionDate\tContaminant\tMRL\tUnits"
    "\tAnalyticalResultsSign\tAnalyticalResultValue"
)
UCMR_ROWS = (
    "PA7360045\tEPHRATA AREA JOINT AUTHORITY\tFilter Plant Finished Water\t6/18/2024"
    "\tPFOA\t0.004\tµg/L\t=\t0.0052\n"
    "PA1090001\tAQUA PA BRISTOL\tEntry Point\t6/18/2024\tPFOA\t0.004\tµg/L\t<\t"
)


class FakeResp:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def raise_for_status(self):
        pass

    def iter_content(self, size):
        yield self.body


def _serve(monkeypatch, body):
    class FakeSession:
        def get(self, url, **kwargs):
            return FakeResp(body)

    monkeypatch.setattr("pipeline.fetch.ucmr.session", FakeSession())


def _zip_bytes(members):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, text in members.items():
            # latin-1 on purpose: the real file's µ is not valid UTF-8.
            zf.writestr(name, text.encode("latin-1"))
    return buf.getvalue()


def test_ucmr_filters_to_system(monkeypatch):
    _serve(monkeypatch, _zip_bytes({"UCMR5_All_MA_WY.txt": f"{UCMR_HEADER}\n{UCMR_ROWS}"}))
    rows = ucmr.fetch()
    assert len(rows) == 1
    assert rows[0]["Contaminant"] == "PFOA"
    assert rows[0]["Units"] == "µg/L"  # latin-1 decoded intact


def test_ucmr_reads_every_member(monkeypatch):
    _serve(monkeypatch, _zip_bytes({
        "UCMR5_All_MA_WY.txt": f"{UCMR_HEADER}\n{UCMR_ROWS}",
        "UCMR5_All_Tribes_AK_LA.txt": f"{UCMR_HEADER}\n{UCMR_ROWS}",
        "UCMR5_ZIPCodes.txt": "not a results file",
    }))
    assert len(ucmr.fetch()) == 2


def test_ucmr_zero_rows_raises(monkeypatch):
    header_only = f"{UCMR_HEADER}\nPA1090001\tOTHER\tEP\t1/1/2024\tPFOA\t0.004\tµg/L\t<\t"
    _serve(monkeypatch, _zip_bytes({"UCMR5_All_MA_WY.txt": header_only}))
    with pytest.raises(FetchError, match="no rows"):
        ucmr.fetch()


def test_ucmr_missing_columns_raise(monkeypatch):
    _serve(monkeypatch, _zip_bytes({"UCMR5_All_MA_WY.txt": "PWSID\tContaminant\nPA7360045\tPFOA"}))
    with pytest.raises(FetchError, match="missing columns"):
        ucmr.fetch()


def test_ucmr_non_zip_raises(monkeypatch):
    _serve(monkeypatch, b"<html>maintenance page</html>")
    with pytest.raises(FetchError):
        ucmr.fetch()


def test_ucmr_no_members_raises(monkeypatch):
    _serve(monkeypatch, _zip_bytes({"README.txt": "empty"}))
    with pytest.raises(FetchError, match="no UCMR5_All"):
        ucmr.fetch()

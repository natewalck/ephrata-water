import json
from datetime import date
from pathlib import Path

import pytest

from pipeline.common import ref_codes
from pipeline.interpret import (
    explain_violation,
    interpret,
    lead_copper_results,
    pfas_results,
    reporting_summary,
    transparency,
    verdict,
)

FIXTURES = Path(__file__).parent / "fixtures"
REFS = ref_codes()


def load(name):
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture
def echo_system():
    return load("echo_system.json")


@pytest.fixture
def sdwis_data():
    return {
        "water_system": [load("sdwis_water_system.json")],
        "violations": load("sdwis_violations.json"),
    }


def test_refdata_loads():
    assert REFS[("VIOLATION_CATEGORY_CODE", "MR")] == "Monitoring and Reporting"
    assert REFS[("CONTAMINANT_CODE", "2920")] == "CARBON, TOTAL"


def test_explain_monitoring_violation():
    v = explain_violation(load("violation_mr.json"), REFS)
    assert v["health_based"] is False
    assert v["resolved"] is True
    assert v["resolved_date"] == "2019-05-01"
    assert v["what"] == "Monitoring and Reporting (DBP)"
    assert "paperwork" in v["explainer"]


def test_explain_unknown_codes_degrade_gracefully():
    v = explain_violation({"violation_code": "99x", "contaminant_code": "zz"}, REFS)
    assert v["what"] == "Requirement not met"
    assert v["about"] is None


def test_other_category_still_gets_paperwork_reassurance():
    # The live CCR violation hits the "Other" category; residents must still
    # be told it is not a water-quality problem.
    v = explain_violation({"violation_category_code": "Other", "is_health_based_ind": "N"}, REFS)
    assert "not a measured problem with the water itself" in v["explainer"]


def test_health_based_violation_gets_no_reassurance():
    v = explain_violation({"violation_category_code": "MCL", "is_health_based_ind": "Y"}, REFS)
    assert "paperwork" not in v["explainer"]


def test_empty_rtc_date_is_not_resolved():
    v = explain_violation({"rtc_date": ""}, REFS)
    assert v["resolved"] is False


def test_violation_status_beats_rtc_date():
    raw = {"violation_status": "Addressed", "rtc_date": "2020-01-01 00:00:00"}
    v = explain_violation(raw, REFS)
    assert v["resolved"] is False  # "Addressed" = under enforcement, still open
    v = explain_violation({"violation_status": "Archived", "rtc_date": None}, REFS)
    assert v["resolved"] is True


# --- verdict: must never fail open ---


def test_verdict_empty_echo_is_unknown_not_ok():
    # Missing compliance flags must read as "we don't know", never "safe".
    v = verdict(None, [])
    assert v["status"] == "unknown"
    assert "could not be confirmed" in v["headline"]


def test_verdict_all_clear(echo_system):
    v = verdict(echo_system, [])
    assert v["status"] == "ok"
    assert "federal health-based" in v["headline"]
    assert "state" not in v["headline"]  # only federal data is consulted


def test_verdict_open_paperwork_is_caution_not_alarm(echo_system):
    v = verdict(echo_system, [{"resolved": False, "health_based": False}])
    assert v["status"] == "caution"


def test_verdict_health_flag_alone_is_action(echo_system):
    v = verdict({**echo_system, "HealthFlag": "Yes"}, [])
    assert v["status"] == "action"


def test_verdict_open_health_violation_alone_is_action(echo_system):
    v = verdict(echo_system, [{"resolved": False, "health_based": True}])
    assert v["status"] == "action"


def test_verdict_serious_violator_is_action(echo_system):
    v = verdict({**echo_system, "SNCFlag": "1"}, [])
    assert v["status"] == "action"


def test_verdict_quarters_parsed(echo_system):
    v = verdict(echo_system, [])
    q = v["quarters"]
    assert q["total"] == len(echo_system["SDWA3yrComplQtrsHistory"])
    assert q["with_violation"] == sum(
        c != "_" for c in echo_system["SDWA3yrComplQtrsHistory"]
    )


# --- interpret: per-source degradation ---


def test_interpret_full(sdwis_data, echo_system):
    data = interpret(sdwis_data, {"system": echo_system})
    assert data["system"]["name"] == "Ephrata Area Joint Authority"
    assert data["system"]["population_served"] == 24500
    assert len(data["violations"]) == len(sdwis_data["violations"])
    assert data["verdict"]["status"] in {"ok", "caution"}


def test_interpret_without_echo_degrades_to_unknown(sdwis_data):
    data = interpret(sdwis_data, None)
    assert "violations" in data  # SDWIS panels still render
    assert data["system"]["primary_source"] is None
    assert data["verdict"]["status"] == "unknown"


def test_interpret_without_sdwis_keeps_echo_verdict(echo_system):
    data = interpret(None, {"system": echo_system})
    assert "violations" not in data
    assert "system" not in data
    assert data["verdict"]["status"] == "ok"


# --- lead/copper measured results ---


@pytest.fixture
def lcr_samples():
    return load("lcr_samples.json")


@pytest.fixture
def lcr_results():
    return load("lcr_sample_results.json")


@pytest.fixture
def ucmr_rows():
    return load("ucmr5_rows.json")


def test_lead_series_joins_and_derives(lcr_samples, lcr_results):
    res = lead_copper_results(lcr_samples, lcr_results)
    lead = res["contaminants"][0]
    assert lead["code"] == "PB90"
    assert lead["limit"] == 0.015
    ends = [p["end"] for p in lead["periods"]]
    assert ends == ["2016-09-30", "2019-09-30", "2022-09-30", "2025-09-30"]  # ascending
    latest = lead["periods"][-1]
    assert latest["value"] == 0.00152  # string coerced to float
    assert latest["pct_of_limit"] == 10
    assert latest["display"] == "0.00152 mg/L"
    assert lead["periods"][2]["pct_of_limit"] == 8


def test_zero_and_sign_l_are_non_detect(lcr_samples, lcr_results):
    lead = lead_copper_results(lcr_samples, lcr_results)["contaminants"][0]
    for p in lead["periods"][:2]:  # 2016 (value 0), 2019 (sign "L")
        assert p["non_detect"] is True
        assert p["display"] == "Not detected"
        assert p["pct_of_limit"] == 0


def test_unjoinable_and_foreign_rows_dropped(lcr_samples, lcr_results):
    # Orphan sample, no-join result, and the non-lead/copper WQ01 row must
    # all vanish without inflating the series.
    lead = lead_copper_results(lcr_samples, lcr_results)["contaminants"][0]
    assert len(lead["periods"]) == 4
    assert all(p["value"] != 0.5 for p in lead["periods"])


def test_missing_lcr_tables_return_none(lcr_samples):
    assert lead_copper_results(None, None) is None
    assert lead_copper_results([], []) is None
    assert lead_copper_results(lcr_samples, []) is None


def test_copper_not_published_flag(lcr_samples, lcr_results):
    assert lead_copper_results(lcr_samples, lcr_results)["copper_published"] is False


def test_explain_violation_carries_measure():
    v = explain_violation(load("violation_mcl_measured.json"), REFS)
    assert v["measure"] == 0.021
    assert v["measure_unit"] == "mg/L"
    assert v["state_limit"] == 0.015
    v = explain_violation(load("violation_mr.json"), REFS)
    assert v["measure"] is None
    assert v["state_limit"] is None


# --- PFAS (UCMR5) ---


def test_pfas_converts_and_compares(ucmr_rows):
    p = pfas_results(ucmr_rows)
    pfoa = p["contaminants"][0]  # highest pct of limit sorts first
    assert pfoa["name"] == "PFOA"
    assert pfoa["unit"] == "ng/L"
    assert pfoa["limit"] == 4.0
    assert pfoa["max"]["value"] == 5.8  # 0.0058 µg/L -> ng/L
    assert pfoa["max"]["date"] == "2024-09-17"
    assert pfoa["max"]["location"] == "Filter Plant Finished Water"
    assert pfoa["pct_of_limit"] == 145
    assert pfoa["samples"] == 6
    assert pfoa["detections"] == 4
    pfos = p["contaminants"][1]
    assert pfos["name"] == "PFOS"
    assert pfos["pct_of_limit"] == 115


def test_pfas_entry_point_averages_count_non_detects_as_zero(ucmr_rows):
    pfoa = pfas_results(ucmr_rows)["contaminants"][0]
    avgs = {a["location"]: a["value"] for a in pfoa["entry_point_averages"]}
    assert avgs["Filter Plant Finished Water"] == 2.75  # (5.2 + 5.8 + 0 + 0) / 4
    assert avgs["Fulton St. Finished Water"] == 4.65


def test_pfas_unregulated_get_no_limit(ucmr_rows):
    p = pfas_results(ucmr_rows)
    by_name = {c["name"]: c for c in p["contaminants"]}
    assert by_name["PFBS"]["limit"] is None
    assert by_name["PFX-FUTURE"]["limit"] is None  # unknown analyte still listed
    lithium = by_name["lithium"]
    assert lithium["limit"] is None
    assert lithium["unit"] == "µg/L"  # ng/L lithium would be nonsense
    assert lithium["max"]["value"] == 9.23


def test_pfas_summary_counts(ucmr_rows):
    p = pfas_results(ucmr_rows)
    assert p["tested"] == 7
    assert p["never_detected"] == 2  # PFNA, HFPO-DA: only "<" rows
    assert all(c["name"] not in {"PFNA", "HFPO-DA"} for c in p["contaminants"])
    assert p["latest_sample_date"] == "2025-03-24"


def test_pfas_note_stays_hedged(ucmr_rows):
    # A single sample above the limit is not a violation; the copy must say so.
    note = pfas_results(ucmr_rows)["note"]
    assert "annual average" in note
    assert "2029" in note


def test_pfas_empty_returns_none():
    assert pfas_results(None) is None
    assert pfas_results([]) is None


# --- reporting freshness ---


def test_reporting_on_schedule(lcr_samples, lcr_results, ucmr_rows, sdwis_data):
    rep = reporting_summary(
        lead_copper_results(lcr_samples, lcr_results),
        pfas_results(ucmr_rows),
        sdwis_data["violations"],
        today=date(2026, 8, 24),
    )
    assert rep["status"] == "ok"
    assert rep["latest_measurement_date"] == "2025-09-30"  # LCR beats the PFAS date
    assert "lead" in rep["latest_measurement_desc"]
    assert rep["next_expected_by"] == "2028-09-30"
    assert "Ephrata Area Joint Authority" in rep["schedule_note"]
    assert "Borough" not in rep["schedule_note"]
    assert "3 years" in rep["schedule_note"]


def test_reporting_overdue_is_caution_never_action(lcr_samples, lcr_results):
    rep = reporting_summary(
        lead_copper_results(lcr_samples, lcr_results), None, None, today=date(2029, 8, 1)
    )
    assert rep["status"] == "caution"
    assert "has not appeared" in rep["schedule_note"]


def test_reporting_unknown_never_fabricates():
    rep = reporting_summary(None, None, None, today=date(2026, 8, 24))
    assert rep["status"] == "unknown"
    assert rep["latest_measurement_date"] is None
    assert rep["next_expected_by"] is None


def test_reporting_malformed_dates_degrade_to_unknown(lcr_results):
    garbage = [{"sample_id": "PBCU09202504858", "sampling_end_date": "not a date"}]
    assert lead_copper_results(garbage, lcr_results) is None
    rep = reporting_summary(
        lead_copper_results(garbage, lcr_results), None, None, today=date(2026, 8, 24)
    )
    assert rep["status"] == "unknown"


def test_reporting_pfas_date_alone_reports_but_stays_unknown(ucmr_rows):
    # A PFAS date can't stand in for the ongoing LCR schedule.
    rep = reporting_summary(None, pfas_results(ucmr_rows), None, today=date(2026, 8, 24))
    assert rep["latest_measurement_date"] == "2025-03-24"
    assert "PFAS" in rep["latest_measurement_desc"]
    assert rep["status"] == "unknown"
    assert rep["next_expected_by"] is None


def test_ccr_citation_surfaces(sdwis_data):
    rep = reporting_summary(None, None, sdwis_data["violations"], today=date(2026, 8, 24))
    ccr = rep["ccr_citation"]
    assert ccr["begin_date"] == "2025-10-01"
    assert ccr["resolved_date"] == "2025-12-02"
    assert "Consumer Confidence Report" in ccr["note"]
    assert "Ephrata Area Joint Authority" in ccr["note"]
    rep = reporting_summary(None, None, [{"violation_code": "27"}], today=date(2026, 8, 24))
    assert rep["ccr_citation"] is None


# --- transparency ---


def test_transparency_parses_echo_contaminants(echo_system):
    t = transparency(echo_system, REFS)
    assert len(t["monitored"]) == 5
    assert t["monitored"][0] == "Interim Enhanced Surface Water Treatment Rule"
    assert "CARBON, TOTAL" in t["monitored"]
    assert t["dfr_url"].startswith("https://echo.epa.gov/")


def test_transparency_degrades_on_missing_echo():
    t = transparency(None, REFS)
    assert t == {"monitored": [], "dfr_url": None}


# --- interpret wiring ---


def test_interpret_new_keys(sdwis_data, echo_system, lcr_samples, lcr_results, ucmr_rows):
    full = {**sdwis_data, "lcr_samples": lcr_samples, "lcr_sample_results": lcr_results}
    data = interpret(full, {"system": echo_system}, ucmr_rows)
    assert data["results"]["contaminants"][0]["code"] == "PB90"
    assert data["pfas"]["contaminants"][0]["name"] == "PFOA"
    assert data["reporting"]["latest_measurement_date"] == "2025-09-30"
    assert data["transparency"]["dfr_url"]
    assert data["verdict"]["status"] in {"ok", "caution"}


def test_interpret_without_lcr_keys_still_works(sdwis_data, echo_system):
    # Old-shaped SDWIS payloads (no LCR tables) must not break anything.
    data = interpret(sdwis_data, {"system": echo_system})
    assert "results" not in data
    assert "pfas" not in data
    assert data["reporting"]["status"] == "unknown"
    assert data["reporting"]["ccr_citation"] is not None  # CCR row is in the fixture
    assert data["verdict"]["status"] in {"ok", "caution"}

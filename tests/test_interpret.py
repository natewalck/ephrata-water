import json
from pathlib import Path

import pytest

from pipeline.common import ref_codes
from pipeline.interpret import explain_violation, interpret, verdict

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

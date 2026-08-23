import json
from pathlib import Path

from pipeline.common import ref_codes
from pipeline.interpret import explain_violation, verdict

FIXTURES = Path(__file__).parent / "fixtures"
REFS = ref_codes()


def load(name):
    return json.loads((FIXTURES / name).read_text())


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


def test_verdict_all_clear():
    v = verdict({"HealthFlag": "No", "SNCFlag": "0"}, [])
    assert v["status"] == "ok"


def test_verdict_open_paperwork_is_caution_not_alarm():
    open_mr = {"resolved": False, "health_based": False}
    v = verdict({"HealthFlag": "No", "SNCFlag": "0"}, [open_mr])
    assert v["status"] == "caution"
    assert "meets all health-based standards" in v["headline"]


def test_verdict_health_violation_is_action():
    open_mcl = {"resolved": False, "health_based": True}
    v = verdict({"HealthFlag": "Yes", "SNCFlag": "0"}, [open_mcl])
    assert v["status"] == "action"

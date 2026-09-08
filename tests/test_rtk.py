"""RTK parser: the three things that must not silently break -- a positive
bacteria sample and its repeats, rows after a Surrogates subheader, and the
raw/finished split that keeps untreated water out of the tap verdict."""

from pipeline import rtk

CERT = """
    Attention:      Scott Mohn                     Project:        Week 2 Monthly TC
       Lab ID: 2505680-03      Collected By: Client        Sampled: 07/07/26 08:40      Received: 07/07/26 13:50
 Sample Desc: 703 Blue Bell Laundry                        PADEP Type: D-Distribution
         Notes:                                              PWSID: 7360045       Loc ID: 703
Microbiology
  Escherichia coli                     Present /100mL             1.00             SM 9223 B               7/7/26         7/8/26                   JMW      N/A    1
  Total Coliform                       Present /100mL             1.00             SM 9223 B               7/7/26         7/8/26                   JMW      N/A    1
    Attention:      Scott Mohn                     Project:        300 Plant Weekly (NON-DEP)
       Lab ID: 2537177-01     Collected By: Client        Sampled: 06/15/26 06:45      Received: 06/16/26 13:58
 Sample Desc: 300 Church Ave. Filter Plant                 Sample Type: Grab
Total Metals
  Manganese                             <0.005     mg/L           0.005       EPA 200.7 Rev 4.4              06/19/26                              HRG      N/A   0.05   PASS
       Lab ID: 2537177-02     Collected By: Client        Sampled: 06/15/26 06:40      Received: 06/16/26 13:58
 Sample Desc: 300 Raw                                      Sample Type: Grab
Total Metals
  Manganese                             0.077     mg/L           0.005       EPA 200.7 Rev 4.4              06/19/26                              HRG      N/A   0.05   FAIL
    Attention:      Scott Mohn                     Project:        103 EP Triennial SOC 2nd&3rd Q
       Lab ID: 2630308-01     Collected By: Client        Sampled: 07/29/26 09:00      Received: 07/29/26 10:40
 Sample Desc: 103 Entry Point Steinmetz Well               PADEP Type: E-Entry Point
Organics
  Carbofuran                            <0.010     mg/L           0.010       EPA 531.1 Rev 3.1              08/11/26                              IMM      N/A   0.04
Surrogates
  4-Bromo-3,5-Dimethylphenyl              109%                   70-130        EPA 531.1 Rev 3.1              08/11/26                              IMM
  Diquat                                <0.004     mg/L           0.004       EPA 549.2 Rev 1.0              08/07/26                              IMM      N/A   0.02
  Phosphorus as P, Total                  0.46     mg/L           0.01        SM 4500-P F                    07/29/26                     MS1      JMW      N/A   N/A
Notes and Definitions
  Fail    Result greater than EPA maximum contaminant level.
               7360045 3100       TOTAL COLIFORM PRESENCE         331        1.0       070826     703              070726    D        0840     06003    2505680-03      KISTLERC_1
               7360045 3114       E. COLIFORM PRESENCE            331        1.0       070826     703              070726    D        0840     06003    2505680-03      KISTLERC_1
               7360045 3100       TOTAL COLIFORM PRESENCE         331        1.0       070826     703              070726    D        0840     06003    2505680-03      KISTLERC_1
               7360045 3100       TOTAL COLIFORM PRESENCE         331        0.0       070926     703              070826    C        1150     06003    2632002-01      KISTLERC_1
               7360045 3114       E. COLIFORM PRESENCE            331        0.0       070926     703              070826    C        1150     06003    2632002-01      KISTLERC_1
               7360045 3100       TOTAL COLIFORM PRESENCE         331        0.0       071526     704              071426    D        0950     06003    2632533-01      KISTLERC_2
               7360045 3114       E. COLIFORM PRESENCE            331        0.0       071526     704              071426    D        0950     06003    2632533-01      KISTLERC_2
"""


def test_parse_and_summarize():
    parsed = rtk.parse(CERT)
    by_id = {s["lab_id"]: s for s in parsed["samples"]}
    assert set(by_id) == {"2505680-03", "2537177-01", "2537177-02", "2630308-01"}
    assert by_id["2505680-03"]["loc"] == "703"
    assert [r["present"] for r in by_id["2505680-03"]["results"]] == [True, True]
    # Rows after "Surrogates" belong to the enclosing section; % rows are skipped.
    names = [r["analyte"] for r in by_id["2630308-01"]["results"]]
    assert names == ["Carbofuran", "Diquat", "Phosphorus as P, Total"]
    assert by_id["2630308-01"]["results"][0]["lab_mcl"] == 0.04
    # Duplicated DEP printouts collapse to one row per sample and organism.
    assert len(parsed["dep_rows"]) == 6

    out = rtk.summarize(parsed, "2026-05-01", "2026-08-31")
    b = out["bacteria"]
    assert b["routine_samples"] == 2 and b["sites"] == 2
    assert len(b["positives"]) == 1
    p = b["positives"][0]
    assert p["site"] == "703" and p["ecoli"] and p["repeats"] == 1 and p["repeats_clear"]
    assert out["verdict"]["status"] == "caution"

    mn = next(e for e in out["aesthetic"] if e["label"] == "Manganese")
    assert mn["detected"] == 0  # the FAIL was raw water; finished was non-detect
    assert mn["by_plant"][0]["raw"]["value"] == 0.077
    assert [n["location"] for n in out["not_tap"]] == ["300 Raw"]
    assert any(e["label"] == "Diquat" and e["limit"] == 0.02 for e in out["health"])
    assert any(e["label"] == "Phosphorus as P, Total" for e in out["other"])

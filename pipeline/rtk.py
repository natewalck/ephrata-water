"""Lab results obtained by Right-to-Know request, parsed from the lab's PDF.

Two document shapes appear in the response packet: M.J. Reider Certificates
of Analysis (one row per analyte, with units and the lab's own MCL column)
and PA DEP e-government submission printouts (coded rows, heavily duplicated
across packets). Certificates carry chemistry; DEP rows are the complete
bacteria record, including repeat samples whose certificates were not in the
packet.

Usage: pdftotext -layout response.pdf - | python -m pipeline.rtk > pipeline/refdata/rtk_YYYY-MM.json
The parsed JSON is committed; summarize() runs at build time.
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from datetime import date, datetime

# ---------------------------------------------------------------- standards
# Federal limits only. kind: health = primary MCL (40 CFR 141), aesthetic =
# secondary MCL (40 CFR 143.3, taste/odor/staining guideline), none = no
# limit. Values in the lab's own unit for that analyte.
HEALTH, AESTHETIC, NONE = "health", "aesthetic", "none"
STANDARDS: dict[str, tuple[str, float | None, str]] = {
    # analyte (as printed by the lab): (kind, limit, plain-language label)
    "Nitrate as N": (HEALTH, 10, "Nitrate"),
    "Nitrite as N": (HEALTH, 1, "Nitrite"),
    "Total Trihalomethanes (TTHMs)": (HEALTH, 0.080, "Total trihalomethanes (TTHM)"),
    "Total Haloacetic Acids (HAA)": (HEALTH, 0.060, "Haloacetic acids (HAA5)"),
    "Perfluorooctanoic acid (PFOA)": (HEALTH, 4.0, "PFOA"),
    "Perfluorooctanesulfonic Acid": (HEALTH, 4.0, "PFOS"),
    "Perfluorohexanesulfonic Acid": (HEALTH, 10.0, "PFHxS"),
    "Perfluorononanoic Acid (PFNA)": (HEALTH, 10.0, "PFNA"),
    "HFPODA": (HEALTH, 10.0, "HFPO-DA (GenX)"),
    "Perfluorobutanesulfonic Acid": (NONE, None, "PFBS"),
    # Uranium MCL is 30 ug/L; the lab reports pCi/L. 30 ug/L of natural
    # uranium is about 20 pCi/L (EPA's 0.67 pCi/ug conversion).
    "Uranium": (HEALTH, 20, "Uranium"),
    "2,3,7,8-TCDD": (HEALTH, 30, "Dioxin (2,3,7,8-TCDD)"),
    "Solids, Total Dissolved": (AESTHETIC, 500, "Total dissolved solids"),
    "Sulfate": (AESTHETIC, 250, "Sulfate"),
    "Chloride": (AESTHETIC, 250, "Chloride"),
    "Iron": (AESTHETIC, 0.3, "Iron"),
    "Manganese": (AESTHETIC, 0.05, "Manganese"),
    "Aluminum": (AESTHETIC, 0.2, "Aluminum"),
    "Zinc": (AESTHETIC, 5, "Zinc"),
    "Total Hardness as CaCO3": (NONE, None, "Hardness"),
}
# Pesticides, solvents and other synthetic organics: the lab prints the
# federal MCL in its Min/Max column and those match 40 CFR 141.61, so any
# Organics-section analyte not listed above is a health standard at the
# lab's printed limit.

PFAS_NOTE = (
    "Federal PFAS limits (April 2024) apply to a running annual average at each "
    "treatment plant, so a single result near the limit is not a violation. The lab "
    "report prints Pennsylvania's older limits of 14 and 18 ng/L."
)

# Locations whose samples are not drinking water. 300/301/303 "Raw" is
# untreated source water; the reject outfall is nanofiltration brine.
NOT_TAP = re.compile(r"\bRaw\b|Reject Outfall|Field Blank", re.I)
PLANTS = {
    "300": "Church Ave. filter plant (Cocalico Creek)",
    "301": "Fulton Street plant (Well #1)",
    "303": "Well #4 nanofiltration",
}
DEP_CONTAM = {"3100": "Total coliform", "3114": "E. coli"}
DEP_SAMPLE_TYPE = {
    "D": "routine", "C": "repeat", "S": "special", "R": "raw", "P": "plant",
}

# ------------------------------------------------------------------ parsing
RE_LAB = re.compile(r"Lab ID:\s+(\d{7}-\d{2})\s+Collected By:.*?Sampled:\s+(\d\d/\d\d/\d\d)")
RE_CONT = re.compile(r"Lab ID:\s+(\d{7}-\d{2}) Continued")
RE_DESC = re.compile(r"Sample Desc:\s*(.*?)\s*(?:(?:PADEP|Sample) Type:\s*(.*?))?\s*$")
RE_LOC = re.compile(r"Loc ID:\s*(\S+)")
RE_PROJECT = re.compile(r"Project(?: Info)?:\s+(.*?)\s*$")
RE_SECTION = re.compile(
    r"^\s*(General Chemistry|Total Metals|Microbiology|Organics|Subcontracted|Volatiles|"
    r"Preparation Methods|Notes and Definitions|Payment Terms)\s*$"
)
RE_ROW = re.compile(
    r"^\s{1,4}(?P<name>[A-Z0-9][^\s].*?)\s{2,}"
    r"(?P<result>[<>]?\d[\d.]*(?: \(\+/- [\d.]+\))?|Absent|Present)\s+"
    r"(?P<unit>mg/L|ug/L|ng/L|pg/L|pCi/L|/100mL|mg)\s+"
    r"(?P<rl>[\d.]+)\s+"
    r"(?P<method>(?:EPA|SM|CALCULATED)\S*(?: [\w.-]+)*?)\s+"
    r"(?P<analyzed>\d{1,2}/\d{1,2}/\d\d)"
    r"(?P<rest>.*)$"
)
RE_TRAIL = re.compile(r"N/A\s+(?P<mcl>[\d.]+|N/A)\s*(?P<pf>PASS|FAIL)?\s*$")
RE_DEP = re.compile(
    r"^\s*7360045\s+(?P<contam>\d{4})\s+(?P<name>.*?)\s{2,}(?P<method>\d{3})\s+"
    r"(?P<result>[\d.]+)\s+(?P<analysis>\d{6})\s+(?P<loc>\d{3})\s+(?P<sampled>\d{6})\s+"
    r"(?P<type>[A-Z])\s+(?P<time>\d{4})\s+"
)
DATA_SECTIONS = {"General Chemistry", "Total Metals", "Microbiology", "Organics",
                 "Subcontracted", "Volatiles"}


def _d(mmddyy: str) -> str:
    return datetime.strptime(mmddyy, "%m/%d/%y").date().isoformat()


def _d6(mmddyy: str) -> str:
    return datetime.strptime(mmddyy, "%m%d%y").date().isoformat()


def parse(text: str) -> dict:
    samples: dict[str, dict] = {}
    dep: dict[tuple, dict] = {}
    cur: dict | None = None
    project = ""
    section = ""
    for line in text.splitlines():
        if m := RE_PROJECT.search(line):
            project = m.group(1)
            continue
        if m := RE_LAB.search(line):
            cur = samples.setdefault(m.group(1), {
                "lab_id": m.group(1), "sampled": _d(m.group(2)), "project": project,
                "desc": "", "type": "", "loc": "", "results": [],
            })
            section = ""
            continue
        if m := RE_CONT.search(line):
            cur = samples.get(m.group(1))
            section = ""
            continue
        if cur is not None and (m := RE_DESC.search(line)):
            cur["desc"] = m.group(1).strip("_ ")
            cur["type"] = (m.group(2) or "").strip()
            continue
        if cur is not None and (m := RE_LOC.search(line)):
            cur["loc"] = m.group(1)
            continue
        if m := RE_SECTION.match(line):
            section = m.group(1)
            continue
        if m := RE_DEP.match(line):
            g = m.groupdict()
            key = (g["contam"], g["loc"], g["sampled"], g["time"], g["type"])
            dep[key] = {
                "contam": g["name"].strip(), "code": g["contam"], "loc": g["loc"],
                "sampled": _d6(g["sampled"]), "time": g["time"],
                "type": DEP_SAMPLE_TYPE.get(g["type"], g["type"]),
                "result": float(g["result"]),
            }
            continue
        if cur is None or section not in DATA_SECTIONS:
            continue
        if m := RE_ROW.match(line):
            g = m.groupdict()
            trail = RE_TRAIL.search(g["rest"])
            raw = g["result"].split(" ")[0]
            # The lab prints screened-out PCBs as 0.00 rather than "<".
            nd = raw.startswith("<") or raw in ("Absent", "0.00")
            value = None if raw in ("Absent", "Present") else float(raw.lstrip("<>"))
            cur["results"].append({
                "analyte": g["name"].strip(), "section": section,
                "value": value, "nd": nd, "present": raw == "Present",
                "unit": "mg/L" if g["unit"] == "mg" else g["unit"],
                "reporting_limit": float(g["rl"]),
                "lab_mcl": (None if not trail or trail.group("mcl") == "N/A"
                            else float(trail.group("mcl"))),
                "lab_flag": trail.group("pf") if trail else None,
            })
    return {"samples": sorted(samples.values(), key=lambda s: (s["sampled"], s["lab_id"])),
            "dep_rows": sorted(dep.values(), key=lambda r: (r["sampled"], r["loc"], r["code"]))}


# ---------------------------------------------------------------- summarize
def _pct(value: float | None, limit: float | None) -> int | None:
    if value is None or not limit:
        return None
    return round(100 * value / limit)


def _fmt(v: float | None, nd: bool, unit: str, rl: float) -> str:
    if nd:
        return f"Not detected (below {rl:g} {unit})"
    return f"{v:g} {unit}"


def summarize(parsed: dict, start: str, end: str) -> dict:
    """Build the site payload for one request window (ISO dates, inclusive)."""
    samples = [s for s in parsed["samples"] if start <= s["sampled"] <= end]
    dep = [r for r in parsed["dep_rows"] if start <= r["sampled"] <= end]
    site_names = {s["loc"]: s["desc"] for s in samples if s["loc"] and s["desc"]}

    # Bacteria: DEP rows are the complete record. One event per sample
    # (both organisms share a sample), positives carry their repeat samples.
    by_sample: dict[tuple, dict] = {}
    for r in dep:
        if r["code"] not in DEP_CONTAM:
            continue
        ev = by_sample.setdefault((r["loc"], r["sampled"], r["time"], r["type"]), {
            "site": r["loc"], "date": r["sampled"], "type": r["type"],
            "coliform": False, "ecoli": False,
        })
        if r["result"] > 0:
            ev["coliform" if r["code"] == "3100" else "ecoli"] = True
    events = list(by_sample.values())
    routine = [e for e in events if e["type"] == "routine"]
    positives = []
    for e in sorted(routine, key=lambda e: e["date"]):
        if not (e["coliform"] or e["ecoli"]):
            continue
        repeats = [
            {"date": r["date"], "clear": not (r["coliform"] or r["ecoli"])}
            for r in events if r["type"] == "repeat" and r["site"] == e["site"]
            and e["date"] < r["date"] <= _plus_days(e["date"], 7)
        ]
        positives.append({
            "site": e["site"], "name": site_names.get(e["site"], f"site {e['site']}"),
            "date": e["date"], "ecoli": e["ecoli"],
            "repeats": len(repeats), "repeats_clear": all(r["clear"] for r in repeats),
            "repeat_date": min((r["date"] for r in repeats), default=None),
        })
    sites = sorted({e["site"] for e in routine})
    by_site = [{
        "site": s, "name": site_names.get(s, ""),
        "tests": sum(1 for e in routine if e["site"] == s),
        "positives": sum(1 for e in routine if e["site"] == s and (e["coliform"] or e["ecoli"])),
    } for s in sites]
    bacteria = {
        "routine_samples": len(routine), "sites": len(sites), "positives": positives,
        "by_site": by_site,
        "first": min((e["date"] for e in routine), default=None),
        "last": max((e["date"] for e in routine), default=None),
    }

    # Chemistry from certificates, grouped per analyte.
    health: dict[str, dict] = {}
    aesthetic: dict[str, dict] = {}
    other: dict[str, dict] = {}
    for s in samples:
        tap = not NOT_TAP.search(s["desc"])
        for r in s["results"]:
            if r["unit"] == "/100mL":
                continue
            kind, limit, label = STANDARDS.get(r["analyte"], (None, None, r["analyte"]))
            if kind is None:  # unlisted: organics carry the federal MCL in the lab column
                limit = r["lab_mcl"] if r["section"] == "Organics" else None
                kind = HEALTH if limit else NONE
            bucket = {HEALTH: health, AESTHETIC: aesthetic, NONE: other}[kind]
            entry = bucket.setdefault(r["analyte"], {
                "analyte": r["analyte"], "label": label, "unit": r["unit"],
                "limit": limit, "results": [],
            })
            entry["results"].append({
                "location": s["desc"], "loc": s["loc"], "date": s["sampled"], "tap": tap,
                "value": r["value"], "nd": r["nd"],
                "display": _fmt(r["value"], r["nd"], r["unit"], r["reporting_limit"]),
                "pct": None if r["nd"] else _pct(r["value"], limit),
            })

    def finish(bucket: dict) -> list[dict]:
        out = []
        for e in bucket.values():
            tap = [x for x in e["results"] if x["tap"]]
            if not tap:
                continue
            det = [x for x in tap if not x["nd"]]
            e["tap_samples"] = len(tap)
            e["detected"] = len(det)
            e["max"] = max(det, key=lambda x: x["value"]) if det else None
            e["max_pct"] = e["max"]["pct"] if e["max"] else None
            e["results"].sort(key=lambda x: (x["loc"], x["date"]))
            # Raw vs finished at each plant, so treatment is visible.
            plants = {}
            for x in e["results"]:
                code = x["location"][:3]
                if code not in PLANTS:
                    continue
                side = "finished" if x["tap"] else "raw"
                p = plants.setdefault(code, {"plant": code, "name": PLANTS[code]})
                if not x["nd"] and (side not in p or x["value"] > p[side]["value"]):
                    p[side] = x
            e["by_plant"] = [p for p in plants.values() if "finished" in p or "raw" in p]
            out.append(e)
        return sorted(out, key=lambda e: (-(e["max_pct"] or -1), e["label"]))

    # What the packet says about water that is not drinking water.
    not_tap: dict[str, list] = defaultdict(list)
    for bucket in (health, aesthetic, other):
        for e in bucket.values():
            hits = [x for x in e["results"] if not x["tap"] and not x["nd"]]
            for loc in {x["location"] for x in hits}:
                top = max((x for x in hits if x["location"] == loc), key=lambda x: x["value"])
                not_tap[loc].append({"label": e["label"], "display": top["display"],
                                     "limit": e["limit"], "unit": e["unit"], "pct": top["pct"]})

    hardness = other.get("Total Hardness as CaCO3")
    hardness_summary = None
    if hardness:
        fin = [x["value"] for x in hardness["results"] if x["tap"] and x["value"] is not None]
        if fin:
            hardness_summary = {"min": min(fin), "max": max(fin), "unit": "mg/L"}

    return {
        "period": {"start": start, "end": end},
        "verdict": _verdict(bacteria, finish_health := finish(health)),
        "samples": len(samples),
        "bacteria": bacteria,
        "health": finish_health,
        "aesthetic": finish(aesthetic),
        "other": finish(other),
        "hardness": hardness_summary,
        "not_tap": [{"location": k, "results": sorted(v, key=lambda x: -(x["pct"] or 0))}
                    for k, v in sorted(not_tap.items())],
        "plants": PLANTS,
        "pfas_note": PFAS_NOTE,
    }


def _verdict(bacteria: dict, health: list[dict]) -> dict:
    """Period status: health limits and bacteria only; aesthetics never drive it."""
    over = [e["label"] for e in health if (e["max_pct"] or 0) >= 100]
    pos = bacteria["positives"]
    unresolved = [p for p in pos if not (p["repeats"] and p["repeats_clear"])]
    span = f"{bacteria['first']} to {bacteria['last']}"
    if over or unresolved:
        what = ", ".join(over) or "bacteria"
        return {"status": "action", "span": span,
                "headline": f"Lab results show {what} above a health-based limit in this period."}
    if pos:
        sites = len({p["site"] for p in pos})
        return {"status": "caution", "span": span,
                "headline": f"Every chemical result was within federal health limits. E. coli "
                            f"was found at {sites} distribution site{'s' if sites != 1 else ''}; "
                            "repeat samples the next day were all clear."}
    return {"status": "ok", "span": span,
            "headline": "Every result was within federal health limits and no bacteria "
                        "were found."}


def _plus_days(iso: str, n: int) -> str:
    from datetime import timedelta
    return (date.fromisoformat(iso) + timedelta(days=n)).isoformat()


if __name__ == "__main__":
    json.dump(parse(sys.stdin.read()), sys.stdout, indent=1)
    sys.stdout.write("\n")

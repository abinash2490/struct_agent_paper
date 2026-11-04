"""
Export the benchmark case matrix (manuscript Table 3) from benchmark_cases.json.

Usage
-----
    python research_paper/benchmarks/export_case_table.py
writes research_paper/manuscript/tables/table_4_1_benchmark_cases.md and copies it into 04_experimental_setup.md
between its '<!-- table: table_4_1_benchmark_cases.md -->' and '<!-- /table -->' markers.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from research_paper.benchmarks.case_schema import BenchmarkCase, load_cases  # noqa: E402

OUTPUT = REPO_ROOT / "research_paper" / "manuscript" / "tables" / "table_4_1_benchmark_cases.md"
SECTION = REPO_ROOT / "research_paper" / "manuscript" / "04_experimental_setup.md"
REGIME = {"gravity": "Gravity", "modal": "Modal", "fixture": "Analyses of the CAE file"}
# Display titles where the case file's name is not the manuscript's wording (the case file is benchmark data)
TITLES = {
    "A07": "Resizing an overstressed heavy-storage portal frame",
    "A08": "Resizing a frame under response spectrum demands",
    "B03": "3D frame modal analysis",
    "B08": "Resizing a 3D frame under ELF seismic loads",
    "C05": "Floor plan to seismic design (4-story mall, drawing in feet and inches)",
}
PROBES = {"units": "design, US units", "infeasible": "probe: infeasible", "underspecified": "probe: missing input",
          "contradictory": "probe: contradiction"}
TASKS = {"design": "design", "analyze": "analysis", "check": "design check", "reflection": "resizing"}


def _num(x: float) -> str:
    """At most four significant figures, thousands separated."""
    return f"{float(f'{x:.4g}'):,.6f}".rstrip("0").rstrip(".")


def _units(case: BenchmarkCase):
    force, length = (u.strip() for u in case.spec.units.split(","))
    return force, length


def _task(case: BenchmarkCase) -> str:
    t = case.taxonomy
    task = PROBES[t.probe] if t.probe else TASKS[t.task]
    if case.reference_solution is not None and case.reference_solution.initial_dcr is not None:
        task += f" (trial DCR {case.reference_solution.initial_dcr:.3f})"
    return task


def _geometry(case: BenchmarkCase) -> str:
    spec = case.spec
    if spec.cae is not None:
        program = {"sap2000": "SAP2000", "etabs": "ETABS"}[spec.cae.format]
        return f"{program} file `{Path(spec.cae.file).name}`"
    g = spec.geometry
    _, unit = _units(case)
    bays = "/".join(f"{w:g}" for w in g.bay_widths_x)
    if g.dimension == "3d":
        bays += " × " + "/".join(f"{w:g}" for w in g.bay_widths_y)
    stories = "/".join(f"{h:g}" for h in g.story_heights)
    text = f"{g.dimension.upper()}; bays {bays} {unit}; stories {stories} {unit}"
    if g.support == "pinned":
        text += "; pinned bases"
    if spec.plan_image:
        text = f"plan drawing `{Path(spec.plan_image).name}`; " + text
    return text


def _loading(case: BenchmarkCase) -> str:
    seis = case.spec.seismic
    if seis is None:
        return REGIME[case.taxonomy.regime]
    if seis.procedure in ("elf", "rsa_code"):
        kind = "ELF" if seis.procedure == "elf" else "Response spectrum (ASCE 7-22)"
        dirs = "X and Y, 100 %–30 %" if len(seis.directions) > 1 else "X"
        return f"{kind}; S<sub>DS</sub> = {seis.sds:g}, S<sub>D1</sub> = {seis.sd1:g}, R = {seis.r_factor:g}; {dirs}"
    gm = seis.ground_motion
    kind = "Response spectrum of a record" if seis.procedure == "rsa_record" else "Linear response history"
    station = re.sub(r"\s*\(Chopra, Dynamics of Structures, Appendix 6\)", "", gm.station)
    source = " (Chopra, 2017, App. 6)" if station != gm.station else ""
    return f"{kind}: {gm.event}, {station}, component {gm.component}{source}"


def _reference(case: BenchmarkCase) -> str:
    b, r = case.baseline_design, case.reference_solution
    force, length = _units(case)
    if b is not None:
        if not b.feasible:
            return f"infeasible: none of the {b.candidates} section pairs is compliant"
        (c, _), (bb, bh) = b.sections.column, b.sections.beam
        state = b.design.governing_limit_state
        state = re.sub(r"\s*\((?:ACI|ASCE)[^)]*\)\s*$", "", state)  # code reference
        state = re.sub(r"^(?:Joint|Story) \d+ \([xy]\): ", "", state)  # location
        state = {"Column axial-flexure (P-M) interaction": "column axial–flexural interaction",
                 "Beam flexure": "beam flexure",
                 "strong column / weak beam sum(Mnc) >= 1.2 sum(Mnb)": "strong-column/weak-beam",
                 "joint shear": "joint shear",
                 "design story drift Cd*delta_xe/Ie <= Delta_a": "story drift"}.get(state, state)
        if length == "ft":  # sections on the 2 in grid read as inches
            dims = f"columns {c * 12:.0f} in, beams {bb * 12:.0f} × {bh * 12:.0f} in"
        else:
            dims = f"columns {c:g} {length}, beams {bb:g} × {bh:g} {length}"
        return f"{dims}; concrete {_num(b.concrete_volume)} {length}³; DCR {b.design.governing_dcr:.4f} ({state})"
    if r is not None:
        symbols = (("total_weight", "W", force), ("base_shear", "V<sub>b</sub>", force),
                   ("fundamental_period", "T<sub>1</sub>", "s"), ("governing_dcr", "DCR", ""))
        return "; ".join(f"{s} = {_num(r.metrics[k])}{' ' + u if u else ''}" for k, s, u in symbols if k in r.metrics)
    return "behavioral probe (no reference)"


def main() -> None:
    lines = [
        "| Case | Task | Difficulty | Geometry or input | Loading and analysis | Minimum-volume baseline or reference values |",
        "|---|:---:|:---:|---|---|---|",
    ]
    for case in load_cases():
        cid = case.id.split("_")[0]
        lines.append(
            f"| **{cid}** {TITLES.get(cid, case.name)} | {_task(case)} | {case.difficulty.label} ({case.difficulty.score}) "
            f"| {_geometry(case)} | {_loading(case)} | {_reference(case)} |"
        )
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT}")
    if not SECTION.exists():  # the manuscript is not part of the public repository
        return
    text = SECTION.read_text(encoding="utf-8")
    start, end = f"<!-- table: {OUTPUT.name} -->", "<!-- /table -->"
    i = text.find(start)
    if i != -1:
        j = text.index(end, i)
        SECTION.write_text(text[:i + len(start)] + "\n" + "\n".join(lines) + "\n" + text[j:], encoding="utf-8")
        print(f"synced {SECTION}")


if __name__ == "__main__":
    main()

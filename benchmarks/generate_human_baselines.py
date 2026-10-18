"""
Deterministic Human Baseline Generator & Verification Harness
=============================================================

Establishes reproducible, ACI 318 code-compliant conventional engineering baseline
designs for all benchmark cases requiring design.

For each case:
1. Provisions standard human-engineered column and beam cross-sections.
2. Applies gravity, seismic ELF, Response Spectrum, or time-history loads.
3. Solves the structural system using fem2d, fem3d, and structdyn.
4. Performs ACI 318 code checks to guarantee DCR <= 1.0.
5. Computes the baseline concrete volume (V_baseline).
6. Writes the verified baseline data into `research paper/benchmarks/benchmark_cases.json`.

Usage:
    python "research paper/benchmarks/generate_human_baselines.py"
"""

import json
from pathlib import Path
from typing import Any, Dict

from struct_agent.tools.model import create_frame_model
from struct_agent.tools.loads import apply_gravity_loads, apply_lateral_loads, generate_load_combinations
from struct_agent.validation.model import validate_model
from struct_agent.tools.analysis import run_analysis
from struct_agent.tools.dynamics import run_response_spectrum, run_time_history
from struct_agent.tools.design import run_design
from struct_agent.tools.link import import_from_sap2000


HUMAN_BASELINES_CATALOG: Dict[str, Dict[str, Any]] = {
    # -------------------------------------------------------------
    # Group A: 2D Plane Frames
    # -------------------------------------------------------------
    "A01_Portal_Frame_Office": {
        "num_bays": 1, "bay_width": 6.0, "num_stories": 1, "story_height": 3.5, "dimension": "2d",
        "col_b": 0.35, "col_h": 0.35, "beam_b": 0.30, "beam_h": 0.50,
        "occupancy": "office", "tributary_width": 4.0, "analysis": "static"
    },
    "A02_Portal_Frame_Storage": {
        "num_bays": 1, "bay_width": 8.0, "num_stories": 1, "story_height": 4.0, "dimension": "2d",
        "col_b": 0.40, "col_h": 0.40, "beam_b": 0.35, "beam_h": 0.65,
        "occupancy": "storage_heavy", "tributary_width": 4.5, "analysis": "static"
    },
    "A03_2Bay_2Story_Office": {
        "num_bays": 2, "bay_width": 5.0, "num_stories": 2, "story_height": 3.2, "dimension": "2d",
        "col_b": 0.40, "col_h": 0.40, "beam_b": 0.30, "beam_h": 0.45,
        "occupancy": "office", "tributary_width": 5.0, "analysis": "static"
    },
    "A04_2Bay_3Story_Residential": {
        "num_bays": 2, "bay_width": 6.0, "num_stories": 3, "story_height": 3.0, "dimension": "2d",
        "col_b": 0.40, "col_h": 0.40, "beam_b": 0.30, "beam_h": 0.50,
        "occupancy": "residential", "tributary_width": 4.5, "analysis": "static"
    },
    "A06_2D_Response_Spectrum_ASCE7": {
        "num_bays": 2, "bay_width": 6.0, "num_stories": 3, "story_height": 3.5, "dimension": "2d",
        "col_b": 0.45, "col_h": 0.45, "beam_b": 0.35, "beam_h": 0.55,
        "occupancy": "office", "tributary_width": 4.5, "analysis": "rsa_asce7",
        "sds": 1.0, "sd1": 0.6, "scale_factor": 9.80665 / 5.0
    },
    "A07_2D_RSA_Ground_Motion": {
        "num_bays": 3, "bay_width": 5.5, "num_stories": 4, "story_height": 3.5, "dimension": "2d",
        "col_b": 0.50, "col_h": 0.50, "beam_b": 0.35, "beam_h": 0.55,
        "occupancy": "office", "tributary_width": 4.5, "analysis": "rsa_gm",
        "ground_motion": "northridge"
    },
    "A08_2D_Overstressed_Portal_Reflection": {
        "num_bays": 1, "bay_width": 7.0, "num_stories": 1, "story_height": 3.5, "dimension": "2d",
        "col_b": 0.40, "col_h": 0.40, "beam_b": 0.35, "beam_h": 0.60,
        "occupancy": "storage_heavy", "tributary_width": 6.0, "analysis": "static"
    },

    # -------------------------------------------------------------
    # Group B: 3D Space Frames
    # -------------------------------------------------------------
    "B02_3D_3x2_3Story_Gravity": {
        "num_bays": 3, "bay_width": 5.0, "num_stories": 3, "story_height": 3.2, "dimension": "3d",
        "bays_x": 3, "bays_y": 2, "bay_width_x": 5.0, "bay_width_y": 6.0,
        "col_b": 0.45, "col_h": 0.45, "beam_b": 0.30, "beam_h": 0.50,
        "occupancy": "office", "tributary_width": 5.0, "analysis": "static"
    },
    "B03_3D_2x2_Seismic_ELF": {
        "num_bays": 2, "bay_width": 6.0, "num_stories": 3, "story_height": 3.5, "dimension": "3d",
        "bays_x": 2, "bays_y": 2, "bay_width_x": 6.0, "bay_width_y": 6.0,
        "col_b": 0.80, "col_h": 0.80, "beam_b": 0.45, "beam_h": 0.85,
        "occupancy": "office", "tributary_width": 6.0, "analysis": "static",
        "lateral": True, "lateral_sds": 1.2, "lateral_sd1": 0.5, "r_factor": 5.0
    },
    "B05_3D_Response_Spectrum_X": {
        "num_bays": 2, "bay_width": 6.0, "num_stories": 3, "story_height": 3.5, "dimension": "3d",
        "bays_x": 2, "bays_y": 2, "bay_width_x": 6.0, "bay_width_y": 6.0,
        "col_b": 0.50, "col_h": 0.50, "beam_b": 0.35, "beam_h": 0.55,
        "occupancy": "office", "tributary_width": 6.0, "analysis": "rsa_asce7",
        "sds": 1.1, "sd1": 0.55, "scale_factor": 9.80665 / 5.0
    },
    "B06_3D_Response_Spectrum_MultiDir": {
        "num_bays": 3, "bay_width": 5.0, "num_stories": 3, "story_height": 3.2, "dimension": "3d",
        "bays_x": 3, "bays_y": 2, "bay_width_x": 5.0, "bay_width_y": 6.0,
        "col_b": 0.50, "col_h": 0.50, "beam_b": 0.35, "beam_h": 0.55,
        "occupancy": "office", "tributary_width": 5.0, "analysis": "rsa_gm",
        "ground_motion": "elcentro", "scale_factor": 9.80665 / 5.0
    },
    "B07_3D_HighSeismic_Reflection": {
        "num_bays": 2, "bay_width": 6.0, "num_stories": 2, "story_height": 3.5, "dimension": "3d",
        "bays_x": 2, "bays_y": 2, "bay_width_x": 6.0, "bay_width_y": 6.0,
        "col_b": 0.65, "col_h": 0.65, "beam_b": 0.35, "beam_h": 0.60,
        "occupancy": "office", "tributary_width": 6.0, "analysis": "static",
        "lateral": True, "lateral_sds": 1.2, "lateral_sd1": 0.5, "r_factor": 5.0
    },
    "B08_3D_Asymmetric_Seismic": {
        "num_bays": 2, "bay_width": 6.0, "num_stories": 3, "story_height": 3.5, "dimension": "3d",
        "bays_x": 2, "bays_y": 2, "bay_width_x": 6.0, "bay_width_y": 6.0,
        "col_b": 0.75, "col_h": 0.75, "beam_b": 0.40, "beam_h": 0.70,
        "occupancy": "office", "tributary_width": 6.0, "analysis": "static",
        "lateral": True, "lateral_sds": 1.0, "lateral_sd1": 0.4, "r_factor": 5.0
    },

    # -------------------------------------------------------------
    # Group C: Advanced Dynamic & Interop Pipelines
    # -------------------------------------------------------------
    "C01_Dynamics_ElCentro_TimeHistory": {
        "num_bays": 2, "bay_width": 6.0, "num_stories": 3, "story_height": 3.5, "dimension": "2d",
        "col_b": 0.55, "col_h": 0.55, "beam_b": 0.40, "beam_h": 0.65,
        "occupancy": "office", "tributary_width": 5.0, "analysis": "time_history",
        "ground_motion": "elcentro"
    },
    "C03_CAE_SAP2000_RoundTrip": {
        "source": "sap2000",
        "s2k_path": "struct_link/tests/fixtures/sample_frame.s2k",
        "analysis": "static"
    },
    "C06_Vision_To_Seismic_Design_Pipeline": {
        "num_bays": 2, "bay_width": 6.0, "num_stories": 3, "story_height": 3.2, "dimension": "3d",
        "bays_x": 2, "bays_y": 2, "bay_width_x": 6.0, "bay_width_y": 5.0,
        "col_b": 0.65, "col_h": 0.65, "beam_b": 0.40, "beam_h": 0.65,
        "occupancy": "office", "tributary_width": 5.0, "analysis": "static",
        "lateral": True, "lateral_sds": 1.2, "lateral_sd1": 0.5, "r_factor": 5.0
    },
    "C07_Seismic_TimeHistory_Dynamic_Reflection": {
        "num_bays": 2, "bay_width": 6.0, "num_stories": 3, "story_height": 3.5, "dimension": "2d",
        "col_b": 0.55, "col_h": 0.55, "beam_b": 0.40, "beam_h": 0.65,
        "occupancy": "office", "tributary_width": 5.0, "analysis": "time_history",
        "ground_motion": "elcentro"
    },
    "C08_Full_Pipeline_Autonomous_CAD_Production": {
        "num_bays": 2, "bay_width": 5.0, "num_stories": 2, "story_height": 3.2, "dimension": "2d",
        "col_b": 0.40, "col_h": 0.40, "beam_b": 0.30, "beam_h": 0.50,
        "occupancy": "office", "tributary_width": 5.0, "analysis": "rsa_asce7",
        "sds": 1.0, "sd1": 0.6, "scale_factor": 9.80665 / 5.0
    },
}


def calculate_concrete_volume(project: Any) -> float:
    """Calculate total concrete volume in cubic meters from elements."""
    if not project or not hasattr(project, "model"):
        return 0.0
    nodes_map = {n.id: n for n in getattr(project.model, "nodes", [])}
    sections_map = {s.id: s for s in getattr(project.model, "sections", [])}
    vol = 0.0
    for elem in getattr(project.model, "elements", []):
        sec = sections_map.get(getattr(elem, "section_id", None))
        a = 0.0
        if sec:
            a = getattr(sec, "A", 0.0) or getattr(sec, "area", 0.0)
            if not a:
                b = getattr(sec, "b", 0.0) or getattr(sec, "width", 0.0)
                h = getattr(sec, "h", 0.0) or getattr(sec, "height", 0.0) or getattr(sec, "depth", 0.0)
                a = b * h
        a = a or 0.15
        ni = nodes_map.get(getattr(elem, "start_node", None))
        nj = nodes_map.get(getattr(elem, "end_node", None))
        length = 0.0
        if ni and nj:
            xi, yi, zi = getattr(ni, "x", 0.0), getattr(ni, "y", 0.0), getattr(ni, "z", 0.0)
            xj, yj, zj = getattr(nj, "x", 0.0), getattr(nj, "y", 0.0), getattr(nj, "z", 0.0)
            length = ((xj - xi)**2 + (yj - yi)**2 + (zj - zi)**2)**0.5
        vol += float(a) * float(length)
    return round(vol, 3)


def verify_and_update_baselines():
    repo_root = Path(__file__).resolve().parents[2]
    cases_json_path = repo_root / "research paper" / "benchmarks" / "benchmark_cases.json"

    print("=" * 95)
    print(" VERIFYING HUMAN PRACTICE CODE-COMPLIANT BASELINES (ACI 318)")
    print("=" * 95)
    print(f"{'Case ID':44s} | {'Gov DCR':8s} | {'V_base (m3)':12s} | Status")
    print("-" * 95)

    verified_baselines = {}

    for cid, cfg in HUMAN_BASELINES_CATALOG.items():
        if cfg.get("source") == "sap2000":
            res = import_from_sap2000(s2k_path=repo_root / cfg["s2k_path"])
            proj = res.data["project"]
        else:
            res = create_frame_model(
                num_bays=cfg["num_bays"], bay_width=cfg["bay_width"],
                num_stories=cfg["num_stories"], story_height=cfg["story_height"],
                dimension=cfg["dimension"],
                col_b=cfg.get("col_b", 0.4), col_h=cfg.get("col_h", 0.4),
                beam_b=cfg.get("beam_b", 0.3), beam_h=cfg.get("beam_h", 0.5)
            )
            proj = res.data["project"]
            apply_gravity_loads(proj, occupancy=cfg.get("occupancy", "office"), tributary_width=cfg.get("tributary_width", 5.0))
            if cfg.get("lateral"):
                apply_lateral_loads(proj, sds=cfg.get("lateral_sds", 0.75), sd1=cfg.get("lateral_sd1", 0.4), r_factor=cfg.get("r_factor", 5.0))

        generate_load_combinations(proj)
        validate_model(proj)

        if cfg["analysis"] == "static":
            run_analysis(proj, analysis_case_id="linear_static")
        elif cfg["analysis"] == "rsa_asce7":
            run_response_spectrum(proj, analysis_case_id="rsa_asce7", sds=cfg.get("sds", 1.0), sd1=cfg.get("sd1", 0.6), scale_factor=cfg.get("scale_factor"), direction="x")
        elif cfg["analysis"] == "rsa_gm":
            run_response_spectrum(proj, analysis_case_id="rsa_gm", ground_motion=cfg.get("ground_motion", "elcentro"), scale_factor=cfg.get("scale_factor"), direction="x")
        elif cfg["analysis"] == "time_history":
            run_time_history(proj, analysis_case_id="time_hist", ground_motion=cfg.get("ground_motion", "elcentro"), direction="x")

        res_design = run_design(proj, design_case_id="aci318")
        dcr = res_design.data.get("governing_dcr") if (res_design.ok and res_design.data) else None
        vol = calculate_concrete_volume(proj)
        is_pass = (dcr is not None and dcr <= 1.0)
        status = "VERIFIED [OK]" if is_pass else "FAILED"
        dcr_str = f"{dcr:.3f}" if dcr is not None else "None"
        print(f"{cid:44s} | {dcr_str:8s} | {vol:10.3f} m3 | {status}")
        assert is_pass, f"Baseline for {cid} failed compliance check: DCR={dcr}"

        verified_baselines[cid] = {
            "volume_m3": vol,
            "governing_dcr": round(dcr, 3),
            "col_dimensions": [cfg.get("col_b"), cfg.get("col_h")] if "col_b" in cfg else None,
            "beam_dimensions": [cfg.get("beam_b"), cfg.get("beam_h")] if "beam_b" in cfg else None,
        }

    # Load and update benchmark_cases.json
    with open(cases_json_path, "r", encoding="utf-8") as f:
        cases = json.load(f)

    for c in cases:
        cid = c["id"]
        if cid in verified_baselines:
            base_info = verified_baselines[cid]
            c["baseline_concrete_volume_m3"] = base_info["volume_m3"]
            c["baseline_design"] = {
                "governing_dcr": base_info["governing_dcr"],
                "columns": base_info["col_dimensions"],
                "beams": base_info["beam_dimensions"],
            }
        else:
            c["baseline_concrete_volume_m3"] = None

    with open(cases_json_path, "w", encoding="utf-8") as f:
        json.dump(cases, f, indent=2)

    print("=" * 95)
    print(f"Successfully verified all {len(verified_baselines)} baselines and updated {cases_json_path.name}!")
    print("=" * 95)


if __name__ == "__main__":
    verify_and_update_baselines()

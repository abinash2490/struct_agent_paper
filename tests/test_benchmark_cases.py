"""
Unit tests for research_paper/benchmarks/benchmark_cases.json schema and data integrity.
"""

from __future__ import annotations

from pathlib import Path
import pytest
from oracle_verifier import get_canonical_baseline_volumes


def test_benchmark_cases_count_and_groups(benchmark_cases: list[dict]):
    assert len(benchmark_cases) == 24, f"Expected exactly 24 benchmark cases, got {len(benchmark_cases)}"

    groups = {"Group_A_2D": 0, "Group_B_3D": 0, "Group_C_Advanced": 0}
    for case in benchmark_cases:
        group = case.get("group")
        cid = case.get("id") or case.get("case_id")
        assert group in groups, f"Unexpected group '{group}' in case {cid}"
        groups[group] += 1

    assert groups["Group_A_2D"] == 8, f"Expected 8 Group_A_2D cases, got {groups['Group_A_2D']}"
    assert groups["Group_B_3D"] == 8, f"Expected 8 Group_B_3D cases, got {groups['Group_B_3D']}"
    assert groups["Group_C_Advanced"] == 8, f"Expected 8 Group_C_Advanced cases, got {groups['Group_C_Advanced']}"


def test_design_cases_governing_limit_states_and_dcrs(benchmark_cases: list[dict]):
    design_cases = [c for c in benchmark_cases if c.get("baseline_design") is not None]
    assert len(design_cases) == 16, f"Expected exactly 16 design cases, got {len(design_cases)}"

    for case in design_cases:
        cid = case.get("id") or case.get("case_id")
        des = case["baseline_design"]
        dcr = des.get("governing_dcr")
        assert dcr is not None, f"Case {cid} missing governing_dcr in baseline_design"
        assert 0.0 < dcr <= 1.00, f"Case {cid} governing_dcr {dcr} must be in (0.0, 1.00]"

        gov_mem = des.get("governing_member_id")
        assert gov_mem, f"Case {cid} missing governing_member_id in baseline_design"

        gov_ls = des.get("governing_limit_state")
        assert gov_ls, f"Case {cid} missing governing_limit_state in baseline_design"
        assert "ACI 318" in gov_ls, f"Case {cid} governing_limit_state '{gov_ls}' must cite ACI 318"

        vol = case.get("baseline_concrete_volume_m3")
        assert vol is not None and vol > 0.0, f"Case {cid} must have positive baseline_concrete_volume_m3"


def test_canonical_baseline_volumes_linkage(benchmark_cases_path: Path):
    canonical_vols = get_canonical_baseline_volumes(str(benchmark_cases_path))
    assert len(canonical_vols) == 16, f"Expected 16 canonical baseline volumes, got {len(canonical_vols)}"

    for cid, vol in canonical_vols.items():
        assert vol is not None and vol > 0.0, f"Volume for {cid} must be positive"
        assert round(vol, 3) == vol, f"Volume {vol} for {cid} not rounded to 3 decimal places"


def test_referenced_fixture_files_exist(benchmark_cases: list[dict], benchmarks_dir: Path, repo_root: Path):
    for case in benchmark_cases:
        cid = case.get("id") or case.get("case_id")
        img_rel = case.get("image_path")
        if img_rel:
            p1 = benchmarks_dir / img_rel
            p2 = repo_root / img_rel
            assert p1.exists() or p2.exists(), f"Image path '{img_rel}' for case {cid} not found on disk"


def test_target_constraints_structure(benchmark_cases: list[dict]):
    for case in benchmark_cases:
        cid = case.get("id") or case.get("case_id")
        tc = case.get("target_constraints")
        assert isinstance(tc, dict), f"Case {cid} target_constraints must be a dict"
        assert "dimension" in tc, f"Case {cid} missing dimension in target_constraints"
        assert tc["dimension"] in ["2d", "3d"], f"Case {cid} dimension must be '2d' or '3d'"
        assert "stories" in tc, f"Case {cid} missing stories in target_constraints"
        assert tc["stories"] >= 1, f"Case {cid} stories must be >= 1"

    # Specific assertions for C05 & C06 vision cases
    c05 = next(c for c in benchmark_cases if c["id"] == "C05_Vision_FloorPlan_Draft_Ingestion")
    for key in ("bay_width", "bay_width_x", "bay_width_y"):
        assert key not in c05["target_constraints"], f"Key '{key}' should not be in C05 target_constraints"
    assert c05["target_constraints"]["bays_x"] == 3
    assert c05["target_constraints"]["bays_y"] == 3

    c06 = next(c for c in benchmark_cases if c["id"] == "C06_Vision_To_Seismic_Design_Pipeline")
    for key in ("bay_width", "bay_width_x", "bay_width_y"):
        assert key not in c06["target_constraints"], f"Key '{key}' should not be in C06 target_constraints"
    assert c06["target_constraints"]["bays_x"] == 4
    assert c06["target_constraints"]["bays_y"] == 3

    # Assert B01 naming
    b01 = next(c for c in benchmark_cases if c["id"] == "B01_3D_2x2_2Story_Gravity")
    assert b01["name"] == "3D Space Frame (2x2, 2-Story Gravity)"
    assert not any(c["id"] == "B01_3D_2x2_2Story_Residential" for c in benchmark_cases)

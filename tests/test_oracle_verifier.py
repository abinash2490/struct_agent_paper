"""
Unit tests for research_paper/benchmarks/oracle_verifier.py.
"""

from __future__ import annotations

from pathlib import Path
import pytest
from oracle_verifier import OracleVerifier, ORACLE_CASES_CATALOG
from struct_core import Project, Node, BeamElement, RectangularSection, Material


def test_catalog_contains_all_24_cases():
    assert len(ORACLE_CASES_CATALOG) == 24
    expected_prefixes = ["A0", "B0", "C0"]
    for prefix in expected_prefixes:
        cases = [c for c in ORACLE_CASES_CATALOG if c.startswith(prefix)]
        assert len(cases) == 8, f"Expected 8 cases starting with {prefix}, found {len(cases)}"


def test_sanity_bounds_rejection(repo_root: Path):
    verifier = OracleVerifier(repo_root=repo_root)
    # col_b = 0.05m (< 0.15m min bound)
    res_under = verifier.evaluate("A01_Portal_Frame_Office", col_b=0.05, col_h=0.3, beam_b=0.3, beam_h=0.4)
    assert not res_under.valid_sections
    assert res_under.calculation_hallucination_rate_pct == 100.0

    # col_b = 4.0m (> 3.0m max bound)
    res_over = verifier.evaluate("A01_Portal_Frame_Office", col_b=4.0, col_h=0.3, beam_b=0.3, beam_h=0.4)
    assert not res_over.valid_sections
    assert res_over.calculation_hallucination_rate_pct == 100.0


def test_2d_gravity_oracle_evaluation(repo_root: Path):
    verifier = OracleVerifier(repo_root=repo_root)
    claims = {
        "claimed_total_weight_kN": 45.0,
        "claimed_governing_dcr": 0.85,
    }
    res = verifier.evaluate(
        "A01_Portal_Frame_Office",
        col_b=0.35,
        col_h=0.35,
        beam_b=0.30,
        beam_h=0.50,
        claims=claims,
    )
    assert res.valid_sections
    assert res.total_weight_kN is not None and res.total_weight_kN > 0.0
    assert res.governing_dcr is not None
    assert "total_weight_kN" in res.active_metrics
    assert "governing_dcr" in res.active_metrics
    assert res.material_economy_ratio is not None


def test_2d_modal_non_design_oracle(repo_root: Path):
    verifier = OracleVerifier(repo_root=repo_root)
    claims = {
        "claimed_total_weight_kN": 250.0,
        "claimed_fundamental_period_s": 0.35,
    }
    res = verifier.evaluate(
        "A05_2D_Modal_Dynamics",
        col_b=0.40,
        col_h=0.40,
        beam_b=0.30,
        beam_h=0.50,
        claims=claims,
    )
    assert res.valid_sections
    assert res.governing_dcr is None  # Non-design case
    assert res.fundamental_period_s is not None and res.fundamental_period_s > 0.0
    assert "fundamental_period_s" in res.active_metrics


def test_3d_seismic_elf_oracle(repo_root: Path):
    verifier = OracleVerifier(repo_root=repo_root)
    res = verifier.evaluate(
        "B03_3D_2x2_Seismic_ELF",
        col_b=0.60,
        col_h=0.60,
        beam_b=0.40,
        beam_h=0.65,
    )
    assert res.valid_sections
    assert res.base_shear_kN is not None and res.base_shear_kN > 0.0
    assert "base_shear_kN" in res.active_metrics
    assert res.governing_dcr is not None


def test_cae_fixtures_oracle(repo_root: Path):
    verifier = OracleVerifier(repo_root=repo_root)
    res_c03 = verifier.evaluate(
        "C03_CAE_SAP2000_RoundTrip",
        claims={"claimed_total_weight_kN": 988.96, "claimed_base_shear_kN": 132.37, "claimed_fundamental_period_s": 0.453}
    )
    assert res_c03.valid_sections
    assert res_c03.total_weight_kN is not None
    assert res_c03.base_shear_kN is not None
    assert res_c03.fundamental_period_s is not None
    assert res_c03.period_t2_s is not None
    assert res_c03.period_t3_s is not None
    assert res_c03.governing_dcr is None
    assert res_c03.code_compliant is None

    res_c04 = verifier.evaluate(
        "C04_CAE_ETABS_RoundTrip",
        claims={"claimed_total_weight_kN": 988.96, "claimed_base_shear_kN": 132.37, "claimed_fundamental_period_s": 0.458}
    )
    assert res_c04.valid_sections
    assert res_c04.total_weight_kN is not None
    assert res_c04.base_shear_kN is not None
    assert res_c04.fundamental_period_s is not None
    assert res_c04.period_t2_s is not None
    assert res_c04.period_t3_s is not None
    assert res_c04.governing_dcr is None
    assert res_c04.code_compliant is None


def test_reflection_dcr0_overstressed(repo_root: Path):
    verifier = OracleVerifier(repo_root=repo_root)
    # A08 starts with undersized 300x300 columns and 300x450 beams
    res = verifier.evaluate(
        "A08_2D_Overstressed_Portal_Reflection",
        col_b=0.30,
        col_h=0.30,
        beam_b=0.30,
        beam_h=0.45,
    )
    assert res.valid_sections
    assert res.governing_dcr is not None and res.governing_dcr > 1.0
    assert not res.code_compliant
    assert abs(res.governing_dcr - 3.952) < 0.05


def test_governing_limit_state_reporting(repo_root: Path):
    verifier = OracleVerifier(repo_root=repo_root)
    res = verifier.evaluate(
        "A01_Portal_Frame_Office",
        col_b=0.35,
        col_h=0.35,
        beam_b=0.30,
        beam_h=0.50,
    )
    assert res.governing_member_type in ["beam", "column"]
    assert res.governing_limit_state is not None
    assert "ACI 318" in res.governing_limit_state


def test_prompt_to_schema_fidelity_comprehensive(repo_root: Path):
    from benchmark_utils import evaluate_prompt_to_schema_fidelity
    from struct_agent.tools.model import create_frame_model
    from struct_agent.tools.loads import apply_gravity_loads

    case_a01 = {
        "id": "A01_Portal_Frame_Office",
        "target_constraints": {
            "dimension": "2d",
            "bays": 1,
            "stories": 1,
            "bay_width": 6.0,
            "story_height": 3.5,
            "occupancy": "office",
        },
    }

    res_a01 = create_frame_model(num_bays=1, bay_width=6.0, num_stories=1, story_height=3.5, dimension="2d")
    proj_a01 = res_a01.data["project"]
    apply_gravity_loads(proj_a01, occupancy="office", superimposed_dead=1.5, tributary_width=4.0)

    ok, det = evaluate_prompt_to_schema_fidelity(proj_a01, case_a01)
    assert ok, f"A01 fidelity check failed: {det}"
    assert det.get("dimension_match") is True
    assert det.get("stories_match") is True
    assert det.get("story_height_match") is True
    assert det.get("bays_match") is True
    assert det.get("bay_width_match") is True


def test_vision_c05_irregular_spans_fidelity():
    """Verify that C05 with irregular spans from floor_plan_3story_school.PNG passes PSFR."""
    from benchmark_utils import evaluate_prompt_to_schema_fidelity
    from struct_core import Project, Node, Support, ElasticMaterial

    proj = Project()
    proj.model.materials.append(ElasticMaterial(id=1, name="Concrete", E=2.5e7, nu=0.2, rho=24.0))
    x_coords = [0.0, 8.484, 12.654, 21.138]  # Spans: 8.484m, 4.170m, 8.484m (3 bays)
    y_coords = [0.0, 2.600, 5.250, 9.901]   # Spans: 2.600m, 2.650m, 4.651m (3 bays)
    z_coords = [0.0, 3.5, 7.0, 10.5]        # 3 stories at 3.5m

    nid = 1
    for z in z_coords:
        for x in x_coords:
            for y in y_coords:
                node = Node(id=nid, x=x, y=y, z=z)
                proj.model.nodes.append(node)
                if abs(z) < 1e-4:
                    proj.model.supports.append(Support(node_id=nid, ux=True, uy=True, uz=True, rx=True, ry=True, rz=True))
                nid += 1

    case_c05 = {
        "id": "C05_Vision_FloorPlan_Draft_Ingestion",
        "target_constraints": {
            "vision": True,
            "dimension": "3d",
            "bays_x": 3,
            "bays_y": 3,
            "stories": 3,
            "story_height": 3.5,
            "occupancy": "office",
            "support_type": "fixed",
        },
    }

    ok, det = evaluate_prompt_to_schema_fidelity(proj, case_c05)
    assert ok, f"C05 irregular spans fidelity check failed: {det}"
    assert det.get("bays_x_match") is True
    assert det.get("bays_y_match") is True
    assert det.get("stories_match") is True
    assert det.get("dimension_match") is True


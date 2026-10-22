"""
Unit tests for research_paper/benchmarks/benchmark_utils.py.
"""

from __future__ import annotations

from pathlib import Path
import pytest
from struct_core import Project, Node, BeamElement, RectangularSection, ElasticMaterial
from benchmark_utils import (
    calculate_concrete_volume,
    parse_numerical_claims_from_text,
    compute_material_economy,
)
from struct_link import read_project


def test_calculate_concrete_volume_standard_objects():
    proj = Project()
    n1 = Node(id="N1", x=0.0, y=0.0, z=0.0)
    n2 = Node(id="N2", x=0.0, y=0.0, z=3.0)
    proj.model.nodes = [n1, n2]

    mat = ElasticMaterial(id="CONC", name="Concrete", E=2.5e10, nu=0.2, rho=2400.0)
    proj.model.materials = [mat]

    sec = RectangularSection(id="C1", name="300x300", b=0.3, h=0.3)
    proj.model.sections = [sec]

    elem = BeamElement(id="E1", start_node="N1", end_node="N2", section_id="C1", material_id="CONC")
    proj.model.elements = [elem]

    vol = calculate_concrete_volume(proj, strict=True)
    assert abs(vol - 0.27) < 1e-4


def test_calculate_concrete_volume_fallback_schemas():
    class DummyNode:
        def __init__(self, node_id, x, y, z):
            self.id = node_id
            self.x, self.y, self.z = x, y, z

    class DummyElem:
        def __init__(self, elem_id, node_i, node_j, area):
            self.id = elem_id
            self.node_i = node_i
            self.node_j = node_j
            self.area = area

    class DummyModel:
        def __init__(self):
            self.nodes = [DummyNode("1", 0, 0, 0), DummyNode("2", 0, 0, 4)]
            self.elements = [DummyElem("E1", "1", "2", 0.12)]
            self.sections = []

    class DummyProject:
        def __init__(self):
            self.model = DummyModel()

    proj = DummyProject()
    vol = calculate_concrete_volume(proj, strict=True)
    assert abs(vol - (4.0 * 0.12)) < 1e-4


def test_calculate_concrete_volume_strict_mode_zero_area():
    class DummyNode:
        def __init__(self, x, y, z):
            self.x, self.y, self.z = x, y, z

    class DummyElemZero:
        def __init__(self, node_i, node_j):
            self.node_i = node_i
            self.node_j = node_j
            self.area = 0.0

    class DummyModel:
        def __init__(self):
            self.nodes = {"1": DummyNode(0, 0, 0), "2": DummyNode(0, 0, 3)}
            self.elements = {"E1": DummyElemZero("1", "2")}
            self.sections = {}

    class DummyProject:
        def __init__(self):
            self.model = DummyModel()

    proj = DummyProject()

    with pytest.raises(ValueError, match="invalid cross-section area"):
        calculate_concrete_volume(proj, strict=True)

    # When strict=False, does not raise and returns 0.0
    vol_relaxed = calculate_concrete_volume(proj, strict=False)
    assert vol_relaxed == 0.0


def test_calculate_concrete_volume_cae_fixture(fixtures_dir: Path):
    s2k_path = fixtures_dir / "sample_frame.s2k"
    assert s2k_path.exists(), f"Fixture not found: {s2k_path}"

    proj = read_project(s2k_path)
    assert proj is not None and hasattr(proj, "model")

    vol = calculate_concrete_volume(proj, strict=False)
    assert vol > 0.0, f"Expected positive volume from imported CAE project, got {vol}"


def test_parse_numerical_claims_robustness():
    # 1. Unicode subscripts and integers
    text1 = "The fundamental period T₁ is 0.42 s, and governing DCR = 1 with base shear Vb = 120 kN."
    claims1 = parse_numerical_claims_from_text(text1)
    assert claims1.get("fundamental_period_s") == 0.42
    assert claims1.get("governing_dcr") == 1.0
    assert claims1.get("base_shear_kN") == 120.0

    # 2. Word boundaries avoiding false matches
    text2 = "Using lightweight concrete, the total weight of the structure is 350.5 kN."
    claims2 = parse_numerical_claims_from_text(text2)
    assert claims2.get("total_weight_kN") == 350.5

    # 3. Higher modal periods T2, T3
    text3 = "Modal analysis results: T1: 0.85s, T2: 0.28s, T3: 0.15s. Weight: 450 kN."
    claims3 = parse_numerical_claims_from_text(text3)
    assert claims3.get("fundamental_period_s") == 0.85
    assert claims3.get("period_t2_s") == 0.28
    assert claims3.get("period_t3_s") == 0.15
    assert claims3.get("total_weight_kN") == 450.0

    # 4. Negative values
    text4 = "Max drift displacement: -0.015 m under lateral earthquake loading."
    claims4 = parse_numerical_claims_from_text(text4)
    assert claims4.get("peak_displacement_m") == -0.015


def test_compute_material_economy():
    assert compute_material_economy(1.5, 2.0) == 0.75
    assert compute_material_economy(None, 2.0) is None
    assert compute_material_economy(1.5, None) is None
    assert compute_material_economy(1.5, 0.0) is None

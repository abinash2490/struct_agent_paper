"""
Deterministic Oracle Verifier for LLM Structural Engineering Benchmarking
========================================================================

Eliminates the equifinality/indeterminacy critique and self-weight coupling
issue in LLM benchmarking.

Rather than penalizing an LLM for not matching an arbitrary human baseline section,
the Oracle Verifier:
1. Takes the exact cross-section geometry proposed by the LLM (col_b, col_h, beam_b, beam_h).
2. Enforces physical sanity bounds: b, h in [0.15 m, 1.50 m].
3. Executes our deterministic solvers (fem2d, fem3d, structdyn, aci318) on that exact geometry.
4. Computes true ground-truth Oracle values:
   - W_oracle: Total structural weight (kN) via FEA support reactions.
   - V_b,oracle: Base shear (kN) under lateral loads (RSA, ELF, or dynamics).
   - T_1,oracle: Fundamental natural vibration period (s) via eigenvalue solver.
     (Note: T_1 is mandatory for dynamic/modal regimes; higher modes (T_2, T_3), modal mass ratio,
      and peak roof displacement are mandatory for A05, B04, C01, C02, C03, C04 (per their required_metrics)
      and optional-if-claimed for other cases).
   - DCR_oracle: Maximum governing Demand-Capacity Ratio via ACI 318 code checks.
5. Scores Calculation Hallucination Rate (CHR) strictly as precision over claims made:
   - CHR = (|wrong claims| / |claims made|) * 100%.
   - Does NOT penalize omission as calculation hallucination (omissions are tracked separately
     in omitted_metrics and claim_completeness_pct = |claims made| / |expected active metrics|).
   - Flags any >10% deviation between claimed values and Oracle values as a calculation hallucination.
6. Assesses true Code Compliance Rate (CCR) based on DCR_oracle <= 1.00.
7. For C03 and C04 (commercial CAE fixtures), evaluates W_oracle, V_b,oracle, and modal periods (T_1, T_2, T_3) directly on the fixture models.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from .benchmark_utils import calculate_concrete_volume, get_canonical_baseline_volumes
except ImportError:
    from research_paper.benchmarks.benchmark_utils import (
        calculate_concrete_volume,
        get_canonical_baseline_volumes,
    )

from struct_agent.tools.analysis import run_analysis
from struct_agent.tools.design import run_design
from struct_agent.tools.dynamics import run_response_spectrum, run_time_history
from struct_agent.tools.link import import_from_etabs, import_from_sap2000
from struct_agent.tools.loads import (
    apply_gravity_loads,
    apply_lateral_loads,
    define_mass_source,
    generate_load_combinations,
)
from struct_agent.tools.model import create_frame_model
from struct_agent.validation.model import validate_model


# ---------------------------------------------------------------------------
# Complete 24-Case Parameterization Catalog
# Covers all 16 design cases + all 8 non-design cases.
# ---------------------------------------------------------------------------
ORACLE_CASES_CATALOG: Dict[str, Dict[str, Any]] = {
    # -----------------------------------------------------------------------
    # Group A: 2D Plane Frames (8 Cases)
    # -----------------------------------------------------------------------
    "A01_Portal_Frame_Office": {
        "num_bays": 1, "bay_width": 6.0, "num_stories": 1, "story_height": 3.5, "dimension": "2d",
        "occupancy": "office", "tributary_width": 4.0, "analysis": "static",
        "design_required": True, "lateral": False, "is_dynamic": False,
        "default_col": (0.35, 0.35), "default_beam": (0.30, 0.50),
    },
    "A02_Portal_Frame_Storage": {
        "num_bays": 1, "bay_width": 8.0, "num_stories": 1, "story_height": 4.0, "dimension": "2d",
        "occupancy": "storage_heavy", "tributary_width": 4.5, "analysis": "static",
        "design_required": True, "lateral": False, "is_dynamic": False,
        "default_col": (0.50, 0.50), "default_beam": (0.35, 0.65),
    },
    "A03_2Bay_2Story_Office": {
        "num_bays": 2, "bay_width": 5.0, "num_stories": 2, "story_height": 3.2, "dimension": "2d",
        "occupancy": "office", "tributary_width": 5.0, "analysis": "static",
        "design_required": True, "lateral": False, "is_dynamic": False,
        "default_col": (0.40, 0.40), "default_beam": (0.30, 0.45),
    },
    "A04_2Bay_3Story_Residential": {
        "num_bays": 2, "bay_width": 6.0, "num_stories": 3, "story_height": 3.0, "dimension": "2d",
        "occupancy": "residential", "tributary_width": 4.5, "analysis": "static",
        "design_required": True, "lateral": False, "is_dynamic": False,
        "default_col": (0.40, 0.40), "default_beam": (0.30, 0.50),
    },
    "A05_2D_Modal_Dynamics": {
        "num_bays": 2, "bay_width": 6.0, "num_stories": 3, "story_height": 3.5, "dimension": "2d",
        "occupancy": "office", "tributary_width": 4.5, "analysis": "modal",
        "design_required": False, "lateral": False, "is_dynamic": True,
        "required_metrics": ["fundamental_period_s", "period_t2_s", "period_t3_s", "modal_mass_ratio"],
        "default_col": (0.40, 0.40), "default_beam": (0.30, 0.50),
    },
    "A06_2D_Response_Spectrum_ASCE7": {
        "num_bays": 2, "bay_width": 6.0, "num_stories": 3, "story_height": 3.5, "dimension": "2d",
        "occupancy": "office", "tributary_width": 4.5, "analysis": "rsa_asce7",
        "sds": 1.0, "sd1": 0.6, "scale_factor": 9.80665 / 5.0,
        "design_required": True, "lateral": True, "is_dynamic": True,
        "default_col": (0.45, 0.45), "default_beam": (0.35, 0.55),
    },
    "A07_2D_RSA_Ground_Motion": {
        "num_bays": 3, "bay_width": 5.5, "num_stories": 4, "story_height": 3.5, "dimension": "2d",
        "occupancy": "office", "tributary_width": 4.5, "analysis": "rsa_gm",
        "ground_motion": "northridge",
        "design_required": True, "lateral": True, "is_dynamic": True,
        "default_col": (0.50, 0.50), "default_beam": (0.35, 0.55),
    },
    "A08_2D_Overstressed_Portal_Reflection": {
        "num_bays": 1, "bay_width": 7.0, "num_stories": 1, "story_height": 3.5, "dimension": "2d",
        "occupancy": "storage_heavy", "tributary_width": 6.0, "analysis": "static",
        "design_required": True, "lateral": False, "is_dynamic": False,
        "default_col": (0.50, 0.50), "default_beam": (0.40, 0.70),
    },

    # -----------------------------------------------------------------------
    # Group B: 3D Space Frames (8 Cases)
    # -----------------------------------------------------------------------
    "B01_3D_2x2_2Story_Gravity": {
        "num_bays": 2, "bay_width": 6.0, "num_stories": 2, "story_height": 3.5, "dimension": "3d",
        "bays_x": 2, "bays_y": 2, "bay_width_x": 6.0, "bay_width_y": 6.0,
        "occupancy": "residential", "tributary_width": None, "analysis": "static",
        "design_required": False, "lateral": False, "is_dynamic": False,
        "default_col": (0.40, 0.40), "default_beam": (0.30, 0.50),
    },
    "B02_3D_3x2_3Story_Gravity": {
        "num_bays": 3, "bay_width": 5.0, "num_stories": 3, "story_height": 3.2, "dimension": "3d",
        "bays_x": 3, "bays_y": 2, "bay_width_x": 5.0, "bay_width_y": 6.0,
        "occupancy": "office", "tributary_width": None, "analysis": "static",
        "design_required": True, "lateral": False, "is_dynamic": False,
        "default_col": (0.45, 0.45), "default_beam": (0.30, 0.50),
    },
    "B03_3D_2x2_Seismic_ELF": {
        "num_bays": 2, "bay_width": 6.0, "num_stories": 3, "story_height": 3.5, "dimension": "3d",
        "bays_x": 2, "bays_y": 2, "bay_width_x": 6.0, "bay_width_y": 6.0,
        "occupancy": "office", "tributary_width": None, "analysis": "static",
        "lateral": True, "lateral_sds": 1.2, "lateral_sd1": 0.5, "r_factor": 5.0,
        "design_required": True, "is_dynamic": False,
        "default_col": (0.80, 0.80), "default_beam": (0.45, 0.85),
    },
    "B04_3D_Modal_Dynamics": {
        "num_bays": 2, "bay_width": 6.0, "num_stories": 3, "story_height": 3.5, "dimension": "3d",
        "bays_x": 2, "bays_y": 2, "bay_width_x": 6.0, "bay_width_y": 6.0,
        "occupancy": "office", "tributary_width": None, "analysis": "modal",
        "design_required": False, "lateral": False, "is_dynamic": True,
        "required_metrics": ["fundamental_period_s", "period_t2_s", "period_t3_s", "modal_mass_ratio"],
        "default_col": (0.45, 0.45), "default_beam": (0.30, 0.50),
    },
    "B05_3D_Response_Spectrum_X": {
        "num_bays": 2, "bay_width": 6.0, "num_stories": 3, "story_height": 3.5, "dimension": "3d",
        "bays_x": 2, "bays_y": 2, "bay_width_x": 6.0, "bay_width_y": 6.0,
        "occupancy": "office", "tributary_width": None, "analysis": "rsa_asce7",
        "sds": 1.1, "sd1": 0.55, "scale_factor": 9.80665 / 5.0,
        "design_required": True, "lateral": True, "is_dynamic": True,
        "default_col": (0.80, 0.80), "default_beam": (0.40, 0.65),
    },
    "B06_3D_Response_Spectrum_MultiDir": {
        "num_bays": 3, "bay_width": 5.0, "num_stories": 3, "story_height": 3.2, "dimension": "3d",
        "bays_x": 3, "bays_y": 2, "bay_width_x": 5.0, "bay_width_y": 6.0,
        "occupancy": "office", "tributary_width": None, "analysis": "rsa_gm",
        "ground_motion": "elcentro", "scale_factor": 9.80665 / 5.0,
        "design_required": True, "lateral": True, "is_dynamic": True,
        "default_col": (0.50, 0.50), "default_beam": (0.35, 0.55),
    },
    "B07_3D_HighSeismic_Reflection": {
        "num_bays": 2, "bay_width": 6.0, "num_stories": 2, "story_height": 3.5, "dimension": "3d",
        "bays_x": 2, "bays_y": 2, "bay_width_x": 6.0, "bay_width_y": 6.0,
        "occupancy": "office", "tributary_width": None, "analysis": "static",
        "lateral": True, "lateral_sds": 1.2, "lateral_sd1": 0.5, "r_factor": 5.0,
        "design_required": True, "is_dynamic": False,
        "default_col": (0.65, 0.65), "default_beam": (0.35, 0.60),
    },
    "B08_3D_BiDirectional_Seismic": {
        "num_bays": 2, "bay_width": 6.0, "num_stories": 3, "story_height": 3.5, "dimension": "3d",
        "bays_x": 2, "bays_y": 2, "bay_width_x": 6.0, "bay_width_y": 6.0,
        "occupancy": "office", "tributary_width": None, "analysis": "static",
        "lateral": True, "lateral_sds": 1.0, "lateral_sd1": 0.4, "r_factor": 5.0,
        "design_required": True, "is_dynamic": False,
        "default_col": (0.75, 0.75), "default_beam": (0.40, 0.70),
    },

    # -----------------------------------------------------------------------
    # Group C: Advanced Dynamic, Multimodal & Interoperability (8 Cases)
    # -----------------------------------------------------------------------
    "C01_Dynamics_ElCentro_TimeHistory": {
        "num_bays": 2, "bay_width": 6.0, "num_stories": 3, "story_height": 3.5, "dimension": "2d",
        "occupancy": "office", "tributary_width": 5.0, "analysis": "time_history",
        "ground_motion": "elcentro",
        "design_required": False, "lateral": True, "is_dynamic": True,
        "required_metrics": ["fundamental_period_s", "base_shear_kN", "peak_displacement_m"],
        "default_col": (0.50, 0.50), "default_beam": (0.35, 0.55),
    },
    "C02_Dynamics_Northridge_TimeHistory": {
        "num_bays": 2, "bay_width": 6.0, "num_stories": 2, "story_height": 3.5, "dimension": "3d",
        "bays_x": 2, "bays_y": 2, "bay_width_x": 6.0, "bay_width_y": 6.0,
        "occupancy": "office", "tributary_width": None, "analysis": "time_history",
        "ground_motion": "northridge",
        "design_required": False, "lateral": True, "is_dynamic": True,
        "required_metrics": ["fundamental_period_s", "base_shear_kN", "peak_displacement_m"],
        "default_col": (0.50, 0.50), "default_beam": (0.35, 0.55),
    },
    "C03_CAE_SAP2000_RoundTrip": {
        "source": "sap2000",
        "s2k_path": "research_paper/benchmarks/fixtures/exported_seismic_frame.s2k",
        "dimension": "3d", "num_stories": 2, "bays_x": 2, "bays_y": 1,
        "analysis": "cae_interop",
        "design_required": False, "lateral": True, "is_dynamic": True,
        "required_metrics": ["fundamental_period_s", "period_t2_s", "period_t3_s", "base_shear_kN"],
        "default_col": (0.30, 0.40), "default_beam": (0.25, 0.40),
    },
    "C04_CAE_ETABS_RoundTrip": {
        "source": "etabs",
        "e2k_path": "research_paper/benchmarks/fixtures/exported_seismic_frame.e2k",
        "dimension": "3d", "num_stories": 2, "bays_x": 2, "bays_y": 1,
        "analysis": "cae_interop",
        "design_required": False, "lateral": True, "is_dynamic": True,
        "required_metrics": ["fundamental_period_s", "period_t2_s", "period_t3_s", "base_shear_kN"],
        "default_col": (0.30, 0.40), "default_beam": (0.25, 0.40),
    },
    "C05_Vision_FloorPlan_Draft_Ingestion": {
        "num_bays": 3, "bay_width": 6.0, "num_stories": 3, "story_height": 3.5, "dimension": "3d",
        "bays_x": 3, "bays_y": 3, "bay_width_x": 6.0, "bay_width_y": 6.0,
        "occupancy": "office", "tributary_width": None, "analysis": "static",
        "design_required": False, "lateral": False, "is_dynamic": False,
        "default_col": (0.45, 0.45), "default_beam": (0.30, 0.50),
    },
    "C06_Vision_To_Seismic_Design_Pipeline": {
        "num_bays": 4, "bay_width": 3.735, "num_stories": 4, "story_height": 3.2, "dimension": "3d",
        "bays_x": 4, "bays_y": 3, "bay_width_x": 3.735, "bay_width_y": 3.66,
        "occupancy": "retail", "tributary_width": None, "analysis": "static",
        "lateral": True, "lateral_sds": 1.2, "lateral_sd1": 0.5, "r_factor": 5.0,
        "design_required": True, "is_dynamic": False,
        "default_col": (0.55, 0.55), "default_beam": (0.35, 0.55),
    },
    "C07_2D_Dynamic_Reflection": {
        "num_bays": 2, "bay_width": 6.0, "num_stories": 3, "story_height": 3.5, "dimension": "2d",
        "occupancy": "office", "tributary_width": 5.0, "analysis": "static",
        "lateral": True, "lateral_sds": 1.5, "lateral_sd1": 0.75, "r_factor": 5.0,
        "design_required": True, "is_dynamic": False,
        "default_col": (0.50, 0.50), "default_beam": (0.35, 0.55),
    },
    "C08_Full_Pipeline_Autonomous_CAD_Production": {
        "num_bays": 2, "bay_width": 5.0, "num_stories": 2, "story_height": 3.2, "dimension": "2d",
        "occupancy": "office", "tributary_width": 5.0, "analysis": "rsa_asce7",
        "sds": 1.0, "sd1": 0.6, "scale_factor": 9.80665 / 5.0,
        "design_required": True, "lateral": True, "is_dynamic": True,
        "default_col": (0.40, 0.40), "default_beam": (0.30, 0.50),
    },
}

# Synchronize baseline volumes dynamically from benchmark_cases.json (canonical source)
try:
    _canonical_vols = get_canonical_baseline_volumes()
    for _cid, _cfg in ORACLE_CASES_CATALOG.items():
        _cfg["baseline_vol"] = _canonical_vols.get(_cid, None)
except Exception:
    pass


@dataclass
class OracleResult:
    """
    Standardized result payload from the Oracle Verifier.
    """
    case_id: str
    valid_sections: bool
    sanitized_sections: Dict[str, float]
    total_weight_kN: Optional[float] = None
    base_shear_kN: Optional[float] = None
    fundamental_period_s: Optional[float] = None
    period_t2_s: Optional[float] = None
    period_t3_s: Optional[float] = None
    modal_mass_ratio: Optional[float] = None
    governing_dcr: Optional[float] = None
    governing_member_id: Optional[str] = None
    governing_member_type: Optional[str] = None
    governing_limit_state: Optional[str] = None
    peak_displacement_m: Optional[float] = None
    concrete_volume_m3: float = 0.0
    material_economy_ratio: Optional[float] = None
    code_compliant: Optional[bool] = None
    active_metrics: List[str] = field(default_factory=list)
    expected_metrics: List[str] = field(default_factory=list)
    claims_made: List[str] = field(default_factory=list)
    hallucinated_metrics: List[str] = field(default_factory=list)
    omitted_metrics: List[str] = field(default_factory=list)
    metric_errors: Dict[str, float] = field(default_factory=dict)
    calculation_hallucination_rate_pct: float = 0.0
    error_message: Optional[str] = None



class OracleVerifier:
    """
    Deterministic structural mechanics verifier for benchmark evaluation.
    """

    MIN_SECTION_DIM_M = 0.15
    MAX_SECTION_DIM_M = 1.50
    CHR_TOLERANCE = 0.10  # 10% tolerance for numerical hallucination

    def __init__(self, repo_root: Optional[Path] = None):
        self.repo_root = repo_root or Path(__file__).resolve().parents[2]

    def validate_section_sanity(
        self,
        col_b: Optional[float],
        col_h: Optional[float],
        beam_b: Optional[float],
        beam_h: Optional[float],
    ) -> Tuple[bool, Dict[str, float], Optional[str]]:
        """
        Enforce physical bounds on candidate member sizes: b, h in [0.15m, 1.50m].
        """
        dims = {"col_b": col_b, "col_h": col_h, "beam_b": beam_b, "beam_h": beam_h}
        sanitized: Dict[str, float] = {}

        for k, v in dims.items():
            if v is None:
                return False, {}, f"Missing required dimension '{k}'."
            try:
                val = float(v)
            except (TypeError, ValueError):
                return False, {}, f"Invalid non-numeric dimension '{k}': {v}."

            if math.isnan(val) or math.isinf(val):
                return False, {}, f"Non-finite dimension '{k}': {val}."
            if val < self.MIN_SECTION_DIM_M or val > self.MAX_SECTION_DIM_M:
                return False, {}, (
                    f"Member dimension '{k}' = {val:.3f}m outside realistic bounds "
                    f"[{self.MIN_SECTION_DIM_M}m, {self.MAX_SECTION_DIM_M}m]."
                )
            sanitized[k] = round(val, 3)

        return True, sanitized, None

    def evaluate(
        self,
        case_id: str,
        col_b: Optional[float] = None,
        col_h: Optional[float] = None,
        beam_b: Optional[float] = None,
        beam_h: Optional[float] = None,
        claims: Optional[Dict[str, Any]] = None,
    ) -> OracleResult:
        """
        Run deterministic physics verification on candidate sections for case_id.
        """
        claims = claims or {}
        cfg = ORACLE_CASES_CATALOG.get(case_id)
        if not cfg:
            return OracleResult(
                case_id=case_id,
                valid_sections=False,
                sanitized_sections={},
                error_message=f"Unknown case_id: {case_id} not found in ORACLE_CASES_CATALOG.",
                calculation_hallucination_rate_pct=100.0,
                code_compliant=False,
            )

        requires_design = cfg.get("design_required", True)
        is_lateral = cfg.get("lateral", False)
        is_dynamic = cfg.get("is_dynamic", False)
        base_vol = cfg.get("baseline_vol")

        # -------------------------------------------------------------------
        # 1. Section Sanity Check
        # -------------------------------------------------------------------
        is_cae_fixture = cfg.get("source") in ("sap2000", "etabs")

        if is_cae_fixture:
            # CAE fixtures have their own predefined sections
            valid_secs = True
            sanitized_dims = {
                "col_b": cfg.get("default_col", (0.3, 0.4))[0],
                "col_h": cfg.get("default_col", (0.3, 0.4))[1],
                "beam_b": cfg.get("default_beam", (0.25, 0.4))[0],
                "beam_h": cfg.get("default_beam", (0.25, 0.4))[1],
            }
            sanity_err = None
        else:
            # Require the candidate cross-section dimensions explicitly
            if col_b is None or col_h is None or beam_b is None or beam_h is None:
                return OracleResult(
                    case_id=case_id,
                    valid_sections=False,
                    sanitized_sections={},
                    error_message=(
                        f"Missing required cross-section dimensions: "
                        f"col_b={col_b}, col_h={col_h}, beam_b={beam_b}, beam_h={beam_h}."
                    ),
                    code_compliant=False if requires_design else None,
                    calculation_hallucination_rate_pct=100.0,
                )

            valid_secs, sanitized_dims, sanity_err = self.validate_section_sanity(
                col_b, col_h, beam_b, beam_h
            )

        if not valid_secs:
            return OracleResult(
                case_id=case_id,
                valid_sections=False,
                sanitized_sections={},
                error_message=sanity_err,
                code_compliant=False if requires_design else None,
                calculation_hallucination_rate_pct=100.0,
            )

        # -------------------------------------------------------------------
        # 2. Build Structural Model
        # -------------------------------------------------------------------
        try:
            if cfg.get("source") == "sap2000":
                res_import = import_from_sap2000(s2k_path=self.repo_root / cfg["s2k_path"])
                proj = res_import.data["project"]
            elif cfg.get("source") == "etabs":
                res_import = import_from_etabs(e2k_path=self.repo_root / cfg["e2k_path"])
                proj = res_import.data["project"]
            else:
                res_model = create_frame_model(
                    num_bays=cfg["num_bays"],
                    bay_width=cfg["bay_width"],
                    num_stories=cfg["num_stories"],
                    story_height=cfg["story_height"],
                    dimension=cfg["dimension"],
                    bays_x=cfg.get("bays_x"),
                    bays_y=cfg.get("bays_y"),
                    bay_width_x=cfg.get("bay_width_x"),
                    bay_width_y=cfg.get("bay_width_y"),
                    col_b=sanitized_dims["col_b"],
                    col_h=sanitized_dims["col_h"],
                    beam_b=sanitized_dims["beam_b"],
                    beam_h=sanitized_dims["beam_h"],
                )
                proj = res_model.data["project"]
                apply_gravity_loads(
                    proj,
                    occupancy=cfg.get("occupancy", "office"),
                    tributary_width=cfg.get("tributary_width"),
                )
                if cfg.get("lateral"):
                    apply_lateral_loads(
                        proj,
                        sds=cfg.get("lateral_sds", 0.75),
                        sd1=cfg.get("lateral_sd1", 0.4),
                        r_factor=cfg.get("r_factor", 5.0),
                    )
                if cfg.get("analysis") == "modal":
                    # Self-weight + SDL per prompt & ASCE 7-22 Section 12.7.2 (Live = 0%)
                    define_mass_source(proj, factors={"DEAD": 1.0})

            if not is_cae_fixture:
                generate_load_combinations(proj)
            validate_model(proj)

        except Exception as exc:
            return OracleResult(
                case_id=case_id,
                valid_sections=True,
                sanitized_sections=sanitized_dims,
                error_message=f"Model assembly/validation exception: {exc}",
                code_compliant=False if requires_design else None,
                calculation_hallucination_rate_pct=100.0,
            )

        # -------------------------------------------------------------------
        # 3. Deterministic Solver Execution
        # -------------------------------------------------------------------
        w_oracle: Optional[float] = None
        vb_oracle: Optional[float] = None
        t1_oracle: Optional[float] = None
        t2_oracle: Optional[float] = None
        t3_oracle: Optional[float] = None
        modal_mass_ratio_oracle: Optional[float] = None
        peak_disp_oracle: Optional[float] = None
        dcr_oracle: Optional[float] = None
        gov_member_id: Optional[str] = None
        gov_member_type: Optional[str] = None
        gov_limit_state: Optional[str] = None

        try:
            analysis_type = cfg.get("analysis", "static")

            if is_cae_fixture:
                # CAE fixtures (SAP2000 / ETABS) have pre-configured load cases and modal setup
                run_analysis(proj, analysis_case_id="DEAD", load_case_id="DEAD")
                r_dead = proj.analysis_results.get("DEAD")
                if not r_dead or not r_dead.node_reactions:
                    raise RuntimeError("Failed to compute DEAD reactions on CAE fixture model.")
                w_dead = sum(r.fz for r in r_dead.node_reactions)

                run_analysis(proj, analysis_case_id="SuperDead", load_case_id="SuperDead")
                r_sd = proj.analysis_results.get("SuperDead")
                if not r_sd or not r_sd.node_reactions:
                    raise RuntimeError("Failed to compute SuperDead reactions on CAE fixture model.")
                w_sd = sum(r.fz for r in r_sd.node_reactions)

                w_total_dead = round(w_dead + w_sd, 2)
                w_oracle = w_total_dead

                # 2. Base shear from lateral seismic case EQx
                run_analysis(proj, analysis_case_id="EQx", load_case_id="EQx")
                r_eq = proj.analysis_results.get("EQx")
                if not r_eq or not r_eq.node_reactions:
                    raise RuntimeError("Failed to compute EQx reactions on CAE fixture model.")
                vb_oracle = round(abs(sum(r.fx for r in r_eq.node_reactions)), 2)

                # 3. Modal periods (T1, T2, T3)
                run_analysis(proj, analysis_case_id="MODAL", analysis_type="modal", num_modes=3)
                r_modal = proj.analysis_results.get("MODAL")
                if not r_modal or not r_modal.modal_result or not r_modal.modal_result.modes:
                    raise RuntimeError("Failed to compute MODAL analysis on CAE fixture model.")
                modes = r_modal.modal_result.modes
                t1_oracle = round(float(modes[0].period), 3)
                if len(modes) > 1:
                    t2_oracle = round(float(modes[1].period), 3)
                if len(modes) > 2:
                    t3_oracle = round(float(modes[2].period), 3)

            elif analysis_type == "static":
                r_ana = run_analysis(proj, analysis_case_id="linear_static")
                active_case = proj.analysis_results.get("linear_static")
                if active_case and active_case.node_reactions:
                    # Vertical reactions give total structural weight (sum(fz) or sum(fy))
                    if str(cfg.get("dimension")).lower() == "3d":
                        w_oracle = round(sum(r.fz for r in active_case.node_reactions), 2)
                        if is_lateral:
                            vb_oracle = round(
                                math.sqrt(
                                    sum(r.fx for r in active_case.node_reactions) ** 2
                                    + sum(r.fy for r in active_case.node_reactions) ** 2
                                ),
                                2,
                            )
                    else:
                        w_oracle = round(sum(r.fy for r in active_case.node_reactions), 2)
                        if is_lateral:
                            vb_oracle = round(abs(sum(r.fx for r in active_case.node_reactions)), 2)

            elif analysis_type == "rsa_asce7":
                r_dyn = run_response_spectrum(
                    proj,
                    analysis_case_id="rsa_asce7",
                    sds=cfg.get("sds", 1.0),
                    sd1=cfg.get("sd1", 0.6),
                    scale_factor=cfg.get("scale_factor"),
                    direction="x",
                )
                vb_oracle = round(float(r_dyn.data.get("combined_base_shear", 0.0)), 2)
                t1_oracle = round(float(r_dyn.data.get("fundamental_period", 0.0)), 3)
                # Compute static weight
                run_analysis(proj, analysis_case_id="gravity_static")
                g_case = proj.analysis_results.get("gravity_static")
                if g_case and g_case.node_reactions:
                    is_3d = str(cfg.get("dimension")).lower() == "3d"
                    w_oracle = round(
                        sum((r.fz if is_3d else r.fy) for r in g_case.node_reactions), 2
                    )

            elif analysis_type == "rsa_gm":
                r_dyn = run_response_spectrum(
                    proj,
                    analysis_case_id="rsa_gm",
                    ground_motion=cfg.get("ground_motion", "elcentro"),
                    scale_factor=cfg.get("scale_factor"),
                    direction="x",
                )
                vb_oracle = round(float(r_dyn.data.get("combined_base_shear", 0.0)), 2)
                t1_oracle = round(float(r_dyn.data.get("fundamental_period", 0.0)), 3)
                run_analysis(proj, analysis_case_id="gravity_static")
                g_case = proj.analysis_results.get("gravity_static")
                if g_case and g_case.node_reactions:
                    is_3d = str(cfg.get("dimension")).lower() == "3d"
                    w_oracle = round(
                        sum((r.fz if is_3d else r.fy) for r in g_case.node_reactions), 2
                    )

            elif analysis_type == "time_history":
                r_th = run_time_history(
                    proj,
                    analysis_case_id="time_hist",
                    ground_motion=cfg.get("ground_motion", "elcentro"),
                    direction="x",
                )
                vb_oracle = round(float(r_th.data.get("max_shear_envelope", 0.0)), 2)
                t1_oracle = round(float(r_th.data.get("fundamental_period", 0.0)), 3)
                peak_disp_oracle = round(float(r_th.data.get("peak_lateral_displacement", 0.0)), 4)
                run_analysis(proj, analysis_case_id="gravity_static")
                g_case = proj.analysis_results.get("gravity_static")
                if g_case and g_case.node_reactions:
                    is_3d = str(cfg.get("dimension")).lower() == "3d"
                    w_oracle = round(
                        sum((r.fz if is_3d else r.fy) for r in g_case.node_reactions), 2
                    )

            elif analysis_type == "modal":
                # Pure modal dynamics (A05, B04)
                # Mass source from dead load only (self-weight + SDL per prompt & ASCE 7-22 Section 12.7.2)
                define_mass_source(proj, factors={"DEAD": 1.0})
                res_modal = run_analysis(proj, analysis_case_id="MODAL", analysis_type="modal", num_modes=3)
                r_modal = proj.analysis_results.get("MODAL")
                if r_modal and r_modal.modal_result and r_modal.modal_result.modes:
                    modes = r_modal.modal_result.modes
                    t1_oracle = round(float(modes[0].period), 3)
                    if len(modes) > 1:
                        t2_oracle = round(float(modes[1].period), 3)
                    if len(modes) > 2:
                        t3_oracle = round(float(modes[2].period), 3)
                    modal_mass_ratio_oracle = round(
                        float(getattr(modes[0], "mass_participation_x", 0.0) or getattr(modes[0], "mass_participation_y", 0.0) or 0.0), 4
                    )
                else:
                    r_dyn = run_response_spectrum(
                        proj,
                        analysis_case_id="modal_only",
                        sds=1.0,
                        sd1=0.5,
                        direction="x",
                    )
                    t1_oracle = round(float(r_dyn.data.get("fundamental_period", 0.0)), 3)

                run_analysis(proj, analysis_case_id="gravity_static")
                g_case = proj.analysis_results.get("gravity_static")
                if g_case and g_case.node_reactions:
                    is_3d = str(cfg.get("dimension")).lower() == "3d"
                    w_oracle = round(
                        sum((r.fz if is_3d else r.fy) for r in g_case.node_reactions), 2
                    )

            # Code checks for design cases
            if requires_design:
                res_des = run_design(proj, design_case_id="aci318")
                if res_des.ok and res_des.data:
                    dcr_oracle = round(float(res_des.data.get("governing_dcr", 0.0)), 3)
                    design_res = proj.design_results.get("aci318")
                    if design_res and getattr(design_res, "element_results", None):
                        elems = design_res.element_results
                        if elems:
                            gov_eid, gov_elem = max(
                                elems.items(),
                                key=lambda item: float(getattr(item[1], "governing_dcr", 0.0) or 0.0),
                            )
                            gov_member_id = str(gov_eid)
                            m_type = str(getattr(gov_elem, "member_type", "unknown"))
                            gov_member_type = m_type
                            g_dcr = float(getattr(gov_elem, "governing_dcr", 0.0) or 0.0)
                            flx = getattr(gov_elem, "flexure", None)
                            shr = getattr(gov_elem, "shear", None)
                            flx_dcr = float(getattr(flx, "dcr", 0.0) or 0.0) if flx else 0.0
                            shr_dcr = float(getattr(shr, "dcr", 0.0) or 0.0) if shr else 0.0
                            if m_type == "column":
                                if abs(flx_dcr - g_dcr) < 1e-3:
                                    gov_limit_state = "Column P-M Interaction (ACI 318 §10.5)"
                                elif abs(shr_dcr - g_dcr) < 1e-3:
                                    gov_limit_state = "Column Shear (ACI 318 §22.5)"
                                else:
                                    gov_limit_state = "Column P-M Interaction (ACI 318 §10.5)"
                            else:
                                if abs(flx_dcr - g_dcr) < 1e-3:
                                    gov_limit_state = "Beam Flexure / As,min (ACI 318 §9.6.1)"
                                elif abs(shr_dcr - g_dcr) < 1e-3:
                                    gov_limit_state = "Beam Shear (ACI 318 §22.5)"
                                else:
                                    gov_limit_state = "Beam Flexure (ACI 318 Ch 9)"

        except Exception as exc:
            return OracleResult(
                case_id=case_id,
                valid_sections=True,
                sanitized_sections=sanitized_dims,
                error_message=f"Solver execution exception: {exc}",
                code_compliant=False if requires_design else None,
                calculation_hallucination_rate_pct=100.0,
            )

        try:
            concrete_vol = calculate_concrete_volume(proj, strict=True)
        except ValueError as exc:
            return OracleResult(
                case_id=case_id,
                valid_sections=False,
                sanitized_sections=sanitized_dims,
                error_message=f"Strict concrete volume calculation failed: {exc}",
                code_compliant=False if requires_design else None,
                calculation_hallucination_rate_pct=100.0,
            )
        code_compliant = (dcr_oracle <= 1.00) if (requires_design and dcr_oracle is not None) else None
        economy_ratio = round(concrete_vol / base_vol, 3) if (code_compliant and base_vol is not None and base_vol > 0) else None

        # -------------------------------------------------------------------
        # 4. Regime-Specific Discrepancy & Hallucination Scoring
        # -------------------------------------------------------------------
        # 5. Hallucination Scrutiny (Active Regime Metrics Only)
        # -------------------------------------------------------------------
        active_metrics: List[str] = []
        claims_made: List[str] = []
        hallucinated_metrics: List[str] = []
        omitted_metrics: List[str] = []
        metric_errors: Dict[str, float] = {}

        # Metric 1: Total Weight (active for all cases)
        if w_oracle is not None:
            active_metrics.append("total_weight_kN")
            claimed_w = (
                claims.get("claimed_total_weight_kN")
                or claims.get("total_weight_kN")
                or claims.get("weight_kN")
                or claims.get("weight")
            )
            if claimed_w is None:
                omitted_metrics.append("total_weight_kN")
            else:
                claims_made.append("total_weight_kN")
                try:
                    w_err = abs(float(claimed_w) - w_oracle) / max(w_oracle, 1e-4)
                    metric_errors["total_weight_kN"] = round(w_err, 4)
                    if w_err > self.CHR_TOLERANCE:
                        hallucinated_metrics.append("total_weight_kN")
                except (TypeError, ValueError):
                    hallucinated_metrics.append("total_weight_kN")
                    metric_errors["total_weight_kN"] = 1.0

        # Metric 2: Base Shear (active ONLY if lateral load is present)
        if is_lateral and vb_oracle is not None and vb_oracle > 1e-2:
            active_metrics.append("base_shear_kN")
            claimed_vb = (
                claims.get("claimed_base_shear_kN")
                or claims.get("base_shear_kN")
                or claims.get("base_shear")
                or claims.get("vb")
            )
            if claimed_vb is None:
                omitted_metrics.append("base_shear_kN")
            else:
                claims_made.append("base_shear_kN")
                try:
                    vb_err = abs(float(claimed_vb) - vb_oracle) / max(vb_oracle, 1e-4)
                    metric_errors["base_shear_kN"] = round(vb_err, 4)
                    if vb_err > self.CHR_TOLERANCE:
                        hallucinated_metrics.append("base_shear_kN")
                except (TypeError, ValueError):
                    hallucinated_metrics.append("base_shear_kN")
                    metric_errors["base_shear_kN"] = 1.0

        # Metric 3: Fundamental Period (active ONLY if dynamic/modal analysis)
        if is_dynamic and t1_oracle is not None and t1_oracle > 1e-3:
            active_metrics.append("fundamental_period_s")
            claimed_t1 = (
                claims.get("claimed_fundamental_period_s")
                or claims.get("fundamental_period_s")
                or claims.get("period_s")
                or claims.get("period")
                or claims.get("t1")
            )
            if claimed_t1 is None:
                omitted_metrics.append("fundamental_period_s")
            else:
                claims_made.append("fundamental_period_s")
                try:
                    t1_err = abs(float(claimed_t1) - t1_oracle) / max(t1_oracle, 1e-4)
                    metric_errors["fundamental_period_s"] = round(t1_err, 4)
                    if t1_err > self.CHR_TOLERANCE:
                        hallucinated_metrics.append("fundamental_period_s")
                except (TypeError, ValueError):
                    hallucinated_metrics.append("fundamental_period_s")
                    metric_errors["fundamental_period_s"] = 1.0

        # Metric 4: Governing DCR (active ONLY for design cases)
        if requires_design and dcr_oracle is not None:
            active_metrics.append("governing_dcr")
            claimed_dcr = (
                claims.get("claimed_governing_dcr")
                or claims.get("governing_dcr")
                or claims.get("dcr")
            )
            if claimed_dcr is None:
                omitted_metrics.append("governing_dcr")
            else:
                claims_made.append("governing_dcr")
                try:
                    dcr_err = abs(float(claimed_dcr) - dcr_oracle) / max(dcr_oracle, 1e-4)
                    metric_errors["governing_dcr"] = round(dcr_err, 4)
                    if dcr_err > self.CHR_TOLERANCE:
                        hallucinated_metrics.append("governing_dcr")
                except (TypeError, ValueError):
                    hallucinated_metrics.append("governing_dcr")
                    metric_errors["governing_dcr"] = 1.0

        # Metric 5: Higher Modal Periods (T2, T3) and Modal Mass Ratio (active if claimed)
        if t2_oracle is not None:
            claimed_t2 = claims.get("claimed_period_t2_s") or claims.get("period_t2_s") or claims.get("t2")
            if claimed_t2 is not None:
                active_metrics.append("period_t2_s")
                claims_made.append("period_t2_s")
                try:
                    t2_err = abs(float(claimed_t2) - t2_oracle) / max(t2_oracle, 1e-4)
                    metric_errors["period_t2_s"] = round(t2_err, 4)
                    if t2_err > self.CHR_TOLERANCE:
                        hallucinated_metrics.append("period_t2_s")
                except (TypeError, ValueError):
                    hallucinated_metrics.append("period_t2_s")
                    metric_errors["period_t2_s"] = 1.0

        if t3_oracle is not None:
            claimed_t3 = claims.get("claimed_period_t3_s") or claims.get("period_t3_s") or claims.get("t3")
            if claimed_t3 is not None:
                active_metrics.append("period_t3_s")
                claims_made.append("period_t3_s")
                try:
                    t3_err = abs(float(claimed_t3) - t3_oracle) / max(t3_oracle, 1e-4)
                    metric_errors["period_t3_s"] = round(t3_err, 4)
                    if t3_err > self.CHR_TOLERANCE:
                        hallucinated_metrics.append("period_t3_s")
                except (TypeError, ValueError):
                    hallucinated_metrics.append("period_t3_s")
                    metric_errors["period_t3_s"] = 1.0

        if modal_mass_ratio_oracle is not None:
            claimed_mmr = claims.get("claimed_modal_mass_ratio") or claims.get("modal_mass_ratio") or claims.get("mass_participation")
            if claimed_mmr is not None:
                active_metrics.append("modal_mass_ratio")
                claims_made.append("modal_mass_ratio")
                try:
                    mmr_val = float(claimed_mmr)
                    if mmr_val > 1.0:
                        mmr_val /= 100.0
                    mmr_err = abs(mmr_val - modal_mass_ratio_oracle) / max(modal_mass_ratio_oracle, 1e-4)
                    metric_errors["modal_mass_ratio"] = round(mmr_err, 4)
                    if mmr_err > self.CHR_TOLERANCE:
                        hallucinated_metrics.append("modal_mass_ratio")
                except (TypeError, ValueError):
                    hallucinated_metrics.append("modal_mass_ratio")
                    metric_errors["modal_mass_ratio"] = 1.0

        # Metric 6: Peak Roof Displacement (for dynamic time-history cases C01/C02, active if claimed)
        if peak_disp_oracle is not None:
            claimed_disp = (
                claims.get("claimed_peak_displacement_m")
                or claims.get("peak_displacement_m")
                or claims.get("roof_displacement")
                or claims.get("peak_displacement")
            )
            if claimed_disp is not None:
                active_metrics.append("peak_displacement_m")
                claims_made.append("peak_displacement_m")
                try:
                    d_val = float(claimed_disp)
                    if d_val > 1.0:  # likely in mm
                        d_val /= 1000.0
                    disp_err = abs(d_val - peak_disp_oracle) / max(peak_disp_oracle, 1e-4)
                    metric_errors["peak_displacement_m"] = round(disp_err, 4)
                    if disp_err > self.CHR_TOLERANCE:
                        hallucinated_metrics.append("peak_displacement_m")
                except (TypeError, ValueError):
                    hallucinated_metrics.append("peak_displacement_m")
                    metric_errors["peak_displacement_m"] = 1.0

        cfg_required = cfg.get("required_metrics", [])
        expected_metrics = sorted(list(set(active_metrics) | set(cfg_required)))
        for rm in expected_metrics:
            if rm not in claims_made and rm not in omitted_metrics:
                omitted_metrics.append(rm)
        omitted_metrics.sort()

        n_claims = len(claims_made)
        chr_pct = round((len(hallucinated_metrics) / n_claims) * 100.0, 1) if n_claims > 0 else 0.0

        return OracleResult(
            case_id=case_id,
            valid_sections=True,
            sanitized_sections=sanitized_dims,
            total_weight_kN=w_oracle,
            base_shear_kN=vb_oracle,
            fundamental_period_s=t1_oracle,
            period_t2_s=t2_oracle,
            period_t3_s=t3_oracle,
            modal_mass_ratio=modal_mass_ratio_oracle,
            peak_displacement_m=peak_disp_oracle,
            governing_dcr=dcr_oracle,
            governing_member_id=gov_member_id,
            governing_member_type=gov_member_type,
            governing_limit_state=gov_limit_state,
            concrete_volume_m3=concrete_vol,
            material_economy_ratio=economy_ratio,
            code_compliant=code_compliant,
            active_metrics=active_metrics,
            expected_metrics=expected_metrics,
            claims_made=claims_made,
            hallucinated_metrics=hallucinated_metrics,
            omitted_metrics=omitted_metrics,
            metric_errors=metric_errors,
            calculation_hallucination_rate_pct=chr_pct,
        )

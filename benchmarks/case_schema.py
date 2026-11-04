"""
Typed schema for the benchmark suite (``benchmark_cases.json``).

The JSON file is the single source of truth: prompts, the structural problem specification
(``spec``), deliverables, evaluation rules, frozen reference solutions, and the minimum-volume
baseline designs. The oracle, the baseline generator, the harness, and the consistency tests all
read cases through :func:`load_cases`.

Units
-----
Geometry, loads, forces, section dimensions and the allowable soil bearing pressure are expressed in ``spec.units``
(e.g. "kN, m" or "kip, ft"). In the spec, material strengths are stated in SI (MPa, kg/m^3) and converted to
the case's ``spec.units`` when building the model. Periods are in seconds.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Literal, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, model_validator

BENCHMARKS_DIR = Path(__file__).resolve().parent
CASES_JSON = BENCHMARKS_DIR / "benchmark_cases.json"
REPO_ROOT = BENCHMARKS_DIR.parents[1]

# Canonical metric keys; values are in spec.units (force, length) or seconds.
METRICS = (
    "total_weight",            # unfactored dead load W = member self-weight + superimposed dead
    "base_shear",              # X-direction base shear (ELF design, RSA CQC, THA peak, or fixture case)
    "fundamental_period",      # T1
    "period_t2",               # T2
    "period_t3",               # T3
    "modal_mass_ratio",        # cumulative X-direction effective mass ratio of the first three modes
    "peak_roof_displacement",  # peak X roof displacement relative to the base
    "max_base_reaction",       # largest vertical support reaction under 1.2D + 1.6L
    "governing_dcr",           # governing ACI 318 demand-capacity ratio over beams and columns
)
Metric = Literal[METRICS]  # type: ignore[valid-type]

# Largest departure (spec length units) of a delivered dimension from the design grid and its bounds: a
# grid value rounded to two or more decimals (e.g. 16 in = 1.33 ft, 10 in = 0.8333 ft) still lies on the grid.
GRID_ROUNDING = 0.005

DesignTask = Literal["none", "design", "check"]
Behavior = Literal["report_infeasible", "declare_assumption", "flag_contradiction"]


class DesignGrid(BaseModel):
    """Design space stated in every design prompt (spec length units)."""

    step: float
    column_min: float
    column_max: float
    beam_width_min: float
    beam_width_max: float
    beam_depth_max: float


# Square columns, beams with b <= h, minimum column 12 in and beam width 10 in (ACI 318-25 §18.7.2.1, §18.6.2.1)
DESIGN_GRIDS: Dict[str, DesignGrid] = {
    "m": DesignGrid(step=0.05, column_min=0.30, column_max=1.20, beam_width_min=0.25, beam_width_max=0.60,
                    beam_depth_max=1.20),
    "ft": DesignGrid(step=2.0 / 12.0, column_min=1.0, column_max=4.0, beam_width_min=10.0 / 12.0,
                     beam_width_max=2.0, beam_depth_max=4.0),
}


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SectionPair(_Strict):
    column: Tuple[float, float] = Field(description="Column (b, h) in spec length units")
    beam: Tuple[float, float] = Field(description="Beam (b, h) in spec length units")


class SectionLimits(_Strict):
    max_width: float
    max_depth: float


class Geometry(_Strict):
    dimension: Literal["2d", "3d"]
    bay_widths_x: List[float]
    bay_widths_y: Optional[List[float]] = None
    story_heights: List[float]
    support: Literal["fixed", "pinned"] = "fixed"
    grid_labels_x: Optional[List[str]] = None
    grid_labels_y: Optional[List[str]] = None
    omitted_columns: List[Tuple[str, str]] = Field(
        default_factory=list, description="Grid intersections (x_label, y_label) without a column"
    )

    @model_validator(mode="after")
    def _check(self) -> "Geometry":
        if (self.dimension == "3d") != (self.bay_widths_y is not None):
            raise ValueError("bay_widths_y is required for 3d geometry and forbidden for 2d geometry")
        if self.grid_labels_x is not None and len(self.grid_labels_x) != len(self.bay_widths_x) + 1:
            raise ValueError("grid_labels_x must have one more entry than bay_widths_x")
        if self.grid_labels_y is not None and len(self.grid_labels_y) != len(self.bay_widths_y or []) + 1:
            raise ValueError("grid_labels_y must have one more entry than bay_widths_y")
        if self.omitted_columns and (self.grid_labels_x is None or self.grid_labels_y is None):
            raise ValueError("omitted_columns requires grid labels")
        return self


class Materials(_Strict):
    fc_mpa: float = 27.6
    fy_mpa: float = 414.0
    density_kg_m3: float = 2400.0


class Foundation(_Strict):
    allowable_bearing_pressure: float = Field(
        gt=0.0, description="Net allowable soil bearing pressure under service loads, spec pressure units (kPa, ksf)"
    )


class Loads(_Strict):
    occupancy: str
    superimposed_dead: float = Field(description="Superimposed dead pressure in spec pressure units")
    live: float = Field(description="Live pressure in spec pressure units")
    live_basis: str
    partition_weight: Optional[float] = Field(
        default=None,
        description="Partition weight in the effective seismic weight (ASCE 7-22 §12.7.2 item 2), spec pressure units",
    )
    tributary_width: Optional[float] = Field(default=None, description="2D frames only (spec length units)")


class GroundMotion(_Strict):
    file: str = Field(description="Repository-relative record path (.AT2 or .csv)")
    event: str
    station: str
    component: str
    rsn: Optional[int] = None
    pga_g: float


class Seismic(_Strict):
    procedure: Literal["elf", "rsa_code", "rsa_record", "tha"]
    sds: Optional[float] = None
    sd1: Optional[float] = None
    s1: Optional[float] = Field(default=None, description="Mapped MCE_R S1 (g), for the Cs bound of Eq. 12.8-7")
    r_factor: Optional[float] = None
    importance_factor: float = 1.0
    system: Optional[Literal["rc_smf", "rc_imf"]] = None
    risk_category: str = "II"
    site_class: str = "D"
    directions: List[Literal["x", "y"]] = Field(default_factory=lambda: ["x"])
    orthogonal_combination: bool = False
    vertical_effect: bool = Field(default=False, description="Ev = 0.2 SDS D in the seismic combinations")
    damping_ratio: float = 0.05
    modal_combination: Optional[Literal["CQC", "SRSS"]] = None
    ground_motion: Optional[GroundMotion] = None

    @model_validator(mode="after")
    def _check(self) -> "Seismic":
        needs_code = self.procedure in ("elf", "rsa_code")
        if needs_code and (self.sds is None or self.sd1 is None):
            raise ValueError(f"{self.procedure} requires sds and sd1")
        if self.procedure in ("rsa_record", "tha") and self.ground_motion is None:
            raise ValueError(f"{self.procedure} requires a ground_motion record")
        if self.vertical_effect and self.sds is None:
            raise ValueError("vertical_effect requires sds")
        if self.procedure != "tha" and self.r_factor is None:
            raise ValueError("design-level seismic procedures require r_factor")
        return self


class CaeSource(_Strict):
    file: str
    format: Literal["sap2000", "etabs"]
    column_section_id: str
    beam_section_id: str


class Spec(_Strict):
    units: str = "kN, m"
    analysis: Literal["static", "modal", "rsa", "tha", "cae"]
    geometry: Optional[Geometry] = None
    cae: Optional[CaeSource] = None
    plan_image: Optional[str] = None
    materials: Materials = Field(default_factory=Materials)
    sections: Optional[SectionPair] = Field(default=None, description="Prescribed sections (analysis-only cases)")
    initial_sections: Optional[SectionPair] = Field(default=None, description="Undersized trial sections (reflection)")
    section_limits: Optional[SectionLimits] = None
    loads: Optional[Loads] = None
    seismic: Optional[Seismic] = None
    foundation: Optional[Foundation] = Field(
        default=None, description="Footing inputs of a design or check case (footings are not scored)"
    )

    @model_validator(mode="after")
    def _check(self) -> "Spec":
        if (self.geometry is None) == (self.cae is None):
            raise ValueError("exactly one of geometry or cae must be given")
        if self.analysis == "cae" and self.cae is None:
            raise ValueError("cae analysis requires a cae source")
        if self.analysis in ("rsa", "tha") and (self.seismic is None or self.seismic.procedure[:3] != self.analysis):
            raise ValueError(f"{self.analysis} analysis requires a matching seismic procedure")
        if self.geometry is not None and self.loads is None:
            raise ValueError("generated geometry requires loads")
        return self


class FileDeliverable(_Strict):
    path: str
    kind: Literal["dxf", "s2k", "e2k"]


class Deliverables(_Strict):
    design: DesignTask
    max_dcr: float = 1.0
    files: List[FileDeliverable] = Field(default_factory=list)


class Evaluation(_Strict):
    expected_tools: List[str]
    required_metrics: List[Metric]  # type: ignore[valid-type]
    expected_behavior: Optional[Behavior] = None
    withheld: List[Literal["story_heights", "bay_widths_x"]] = Field(
        default_factory=list,
        description="Geometry fields the prompt deliberately leaves undetermined (excluded from PSFR)",
    )
    claim_tolerance: float = 0.10
    geometry_tolerance: float = Field(default=0.05, description="Absolute tolerance in spec length units")


class Taxonomy(_Strict):
    dimension: Literal["2d", "3d"]
    regime: Literal["gravity", "modal", "elf", "rsa", "tha", "fixture"]
    modality: Literal["text", "image", "cae"]
    task: Literal["analyze", "design", "check", "reflection"]
    probe: Optional[Literal["units", "infeasible", "underspecified", "contradictory"]] = None


class Difficulty(_Strict):
    label: Literal["Easy", "Medium", "Hard"]
    score: int


class DesignSummary(_Strict):
    governing_dcr: float
    governing_member_id: Optional[str] = Field(default=None, description="None when a frame-level check (joint, story) governs")
    governing_member_type: str = Field(description="'beam', 'column', or 'frame'")
    governing_limit_state: str


class ReferenceSolution(_Strict):
    source: str = Field(description="How the values were produced (oracle commit or commercial software)")
    sections: Optional[SectionPair] = None
    metrics: Dict[str, float] = Field(default_factory=dict)
    design: Optional[DesignSummary] = None
    initial_dcr: Optional[float] = None
    concrete_volume: Optional[float] = None


class BaselineDesign(_Strict):
    method: Literal["min_volume_grid_search"] = "min_volume_grid_search"
    feasible: bool
    sections: Optional[SectionPair] = None
    concrete_volume: Optional[float] = None
    design: Optional[DesignSummary] = None
    evaluations: int
    candidates: int


class BenchmarkCase(_Strict):
    id: str
    name: str
    group: Literal["A_2D", "B_3D", "C_Multimodal", "D_Robustness"]
    archetype: str
    taxonomy: Taxonomy
    difficulty: Difficulty
    prompt: str
    spec: Spec
    deliverables: Deliverables
    evaluation: Evaluation
    reference_solution: Optional[ReferenceSolution] = None
    baseline_design: Optional[BaselineDesign] = None

    @model_validator(mode="after")
    def _check_foundation(self) -> "BenchmarkCase":
        if (self.deliverables.design != "none") != (self.spec.foundation is not None):
            raise ValueError(f"{self.id}: a design or check case states its allowable bearing pressure (spec.foundation), "
                             f"and only such a case")
        return self

    @property
    def design_required(self) -> bool:
        return self.deliverables.design == "design"

    @property
    def design_grid(self) -> DesignGrid:
        return DESIGN_GRIDS[self.spec.units.split(",")[1].strip()]

    @property
    def min_beam_depth(self) -> float:
        """ACI 318-25 Table 9.3.1.1 minimum depth l/18.5 for the longest span (deflection not computed)."""
        geo = self.spec.geometry
        if geo is None:
            return 0.0
        return max(geo.bay_widths_x + (geo.bay_widths_y or [])) / 18.5

    def design_space_violations(self, sections: SectionPair) -> List[str]:
        """Departures of proposed sections from the design space stated in the prompt."""
        g = self.design_grid
        (cb, ch), (bb, bh) = sections.column, sections.beam
        tol = GRID_ROUNDING  # a dimension given to two decimals (10 in = 0.83 ft) meets a bound it rounds to
        out = []
        if abs(cb - ch) > tol:
            out.append("column section is not square")
        if bb > bh + tol:
            out.append("beam width exceeds beam depth")
        if cb < g.column_min - tol:
            out.append(f"column smaller than the {g.column_min:g} minimum")
        if bb < g.beam_width_min - tol:
            out.append(f"beam narrower than the {g.beam_width_min:g} minimum")
        if bh < self.min_beam_depth - tol:
            out.append(f"beam shallower than l/18.5 = {self.min_beam_depth:.3f} (ACI 318-25 Table 9.3.1.1)")
        if any(abs(d - round(d / g.step) * g.step) > tol for d in (cb, ch, bb, bh)):
            out.append(f"dimensions are not multiples of {g.step:g}")
        lim = self.spec.section_limits
        if lim is not None and (max(cb, bb) > lim.max_width + tol or max(ch, bh) > lim.max_depth + tol):
            out.append("section exceeds the stated architectural limits")
        return out


def difficulty_score(case: BenchmarkCase) -> int:
    """Rubric: dimension + regime + modality + task (+1 drawings) + robustness probe."""
    t = case.taxonomy
    score = {"2d": 1, "3d": 2}[t.dimension]
    score += {"gravity": 0, "modal": 1, "elf": 1, "fixture": 1, "rsa": 2, "tha": 2}[t.regime]
    score += {"text": 0, "cae": 1, "image": 2}[t.modality]
    score += {"analyze": 0, "check": 1, "design": 1, "reflection": 2}[t.task]
    score += 1 if any(f.kind == "dxf" for f in case.deliverables.files) else 0
    score += 2 if t.probe else 0
    return score


def difficulty_label(score: int) -> str:
    return "Easy" if score <= 3 else ("Medium" if score == 4 else "Hard")


def load_cases(path: Optional[Path] = None) -> List[BenchmarkCase]:
    with open(path or CASES_JSON, "r", encoding="utf-8") as f:
        return [BenchmarkCase.model_validate(c) for c in json.load(f)]


def cases_by_id(path: Optional[Path] = None) -> Dict[str, BenchmarkCase]:
    return {c.id: c for c in load_cases(path)}


def save_cases(cases: List[BenchmarkCase], path: Optional[Path] = None) -> None:
    payload = [c.model_dump(mode="json", exclude_none=True) for c in cases]
    with open(path or CASES_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write("\n")

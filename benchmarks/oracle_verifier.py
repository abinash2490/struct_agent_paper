"""
Deterministic Oracle Verifier for the structural benchmark suite
================================================================

Builds the canonical structural model of a benchmark case from its ``spec`` (see
``case_schema.py``), assigns candidate member sections, runs the deterministic engines
(fem2d / fem3d / structdyn / struct_load / aci318 through the struct_agent tools), and returns
ground-truth metrics. It serves three roles:

1. Ground truth for frozen ``reference_solution`` values and the minimum-volume baseline search.
2. Code-compliance verification of any configuration's final sections (agent, LLM, heuristic):
   compliance is judged on the case's canonical model, never on a model the configuration built.
3. Calculation-hallucination scoring: each claimed metric in ``evaluation.required_metrics`` is
   compared with the oracle value; a relative error above ``evaluation.claim_tolerance`` is a
   hallucination. CHR is precision over claims made; omissions are tracked separately.

The design space shared by every configuration is one rectangular column section and one
rectangular beam section for the whole frame.
"""

from __future__ import annotations

import io
import math
from contextlib import redirect_stdout
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from .benchmark_utils import calculate_concrete_volume
    from .case_schema import REPO_ROOT, BenchmarkCase, SectionPair, cases_by_id
except ImportError:
    from research_paper.benchmarks.benchmark_utils import calculate_concrete_volume
    from research_paper.benchmarks.case_schema import REPO_ROOT, BenchmarkCase, SectionPair, cases_by_id

from struct_core import conversion_factor
from struct_agent.tools.analysis import run_analysis
from struct_agent.tools.design import run_design
from struct_agent.tools.dynamics import run_response_spectrum, run_time_history
from struct_agent.tools.link import import_from_etabs, import_from_sap2000
from struct_agent.tools.loads import apply_gravity_loads, apply_lateral_loads, generate_load_combinations
from struct_agent.tools.model import create_frame_model
from struct_agent.validation.model import validate_model
from struct_agent.vision.compiler import build_project_from_draft
from struct_agent.vision.schemas import BeamDraft, ColumnDraft, FloorPlanDraft, GridLineDraft, StoryDraft
from struct_core import parse_units


@dataclass
class OracleSolution:
    """Ground-truth outcome of one case evaluated with one pair of sections."""

    case_id: str
    sections: Optional[SectionPair]
    metrics: Dict[str, float] = field(default_factory=dict)
    design: Optional[Dict[str, Any]] = None
    concrete_volume: Optional[float] = None
    error: Optional[str] = None

    @property
    def governing_dcr(self) -> Optional[float]:
        return None if self.design is None else self.design.get("governing_dcr")


@dataclass
class OracleResult:
    """Oracle solution plus claim scoring for one configuration's output."""

    solution: OracleSolution
    code_compliant: Optional[bool]
    material_economy_ratio: Optional[float]
    design_space_violations: List[str] = field(default_factory=list)
    claims_made: List[str] = field(default_factory=list)
    hallucinated_metrics: List[str] = field(default_factory=list)
    omitted_metrics: List[str] = field(default_factory=list)
    metric_errors: Dict[str, float] = field(default_factory=dict)

    @property
    def calculation_hallucination_rate_pct(self) -> float:
        n = len(self.claims_made)
        return round(100.0 * len(self.hallucinated_metrics) / n, 1) if n else 0.0

    @property
    def claim_completeness_pct(self) -> float:
        n = len(self.claims_made) + len(self.omitted_metrics)
        return round(100.0 * len(self.claims_made) / n, 1) if n else 100.0


def _quiet(fn, *args, **kwargs):
    with redirect_stdout(io.StringIO()):
        return fn(*args, **kwargs)


def _require(result: Any, what: str) -> Any:
    if not result.ok:
        raise RuntimeError(f"{what} failed: {result.error.message if result.error else result}")
    return result


class OracleVerifier:
    """Deterministic ground truth for benchmark cases (see module docstring)."""

    def __init__(self, cases: Optional[Dict[str, BenchmarkCase]] = None, repo_root: Optional[Path] = None):
        self.cases = cases if cases is not None else cases_by_id()
        self.repo_root = Path(repo_root) if repo_root is not None else REPO_ROOT
        self._cache: Dict[Tuple[str, Optional[Tuple[float, ...]]], OracleSolution] = {}

    # ------------------------------------------------------------------
    # Section handling
    # ------------------------------------------------------------------
    def sections_for(self, case: BenchmarkCase, candidate: Optional[SectionPair]) -> Optional[SectionPair]:
        """Sections used for the oracle model: the candidate, else prescribed, else fixture-defined (None)."""
        if candidate is not None:
            return candidate
        return case.spec.sections

    def check_sections(self, case: BenchmarkCase, sections: Optional[SectionPair]) -> Optional[str]:
        """Return a reason when sections are outside physical bounds or the case's section limits."""
        if sections is None:
            return None if case.spec.cae is not None else "Missing column/beam sections."
        to_m = parse_units(case.spec.units).length
        scale = {"m": 1.0, "mm": 1e-3, "cm": 1e-2, "ft": 0.3048, "in": 0.0254}[to_m]
        for name, dims in (("column", sections.column), ("beam", sections.beam)):
            for d in dims:
                if not (math.isfinite(d) and 0.15 <= d * scale <= 1.50):
                    return (f"{name} dimension {d:g} {to_m} ({d * scale:.3f} m) outside realistic bounds "
                            f"[0.15 m, 1.50 m].")
        return None

    # ------------------------------------------------------------------
    # Model construction
    # ------------------------------------------------------------------
    def build_project(self, case: BenchmarkCase, sections: Optional[SectionPair]) -> Any:
        spec = case.spec
        if spec.cae is not None:
            path = self.repo_root / spec.cae.file
            # The file's materials; the reinforcement it lacks is the case's (stated in the prompt)
            fy_model = spec.materials.fy_mpa * conversion_factor("N, mm", spec.units, "stress")
            rebar = dict(fy=fy_model) if case.deliverables.design != "none" else {}
            if spec.cae.format == "sap2000":
                proj = _require(import_from_sap2000(s2k_path=path, **rebar), "SAP2000 import").data["project"]
            else:
                proj = _require(import_from_etabs(e2k_path=path, **rebar), "ETABS import").data["project"]
            if sections is not None:
                self._resize_fixture_sections(proj, spec.cae.column_section_id, spec.cae.beam_section_id, sections)
            if case.deliverables.design != "none":
                _require(generate_load_combinations(proj), "generate_load_combinations")
            return proj

        geo = spec.geometry
        (col_b, col_h), (beam_b, beam_h) = sections.column, sections.beam
        if geo.omitted_columns:
            proj = self._build_from_grid(case, sections)
        else:
            fc_model = spec.materials.fc_mpa * conversion_factor("N, mm", spec.units, "stress")
            fy_model = spec.materials.fy_mpa * conversion_factor("N, mm", spec.units, "stress")
            unit_weight_model = (
                spec.materials.density_kg_m3 * 9.80665 * conversion_factor("N, m", spec.units, "weight_density")
            )
            proj = _require(
                create_frame_model(
                    dimension=geo.dimension,
                    bay_widths_x=geo.bay_widths_x,
                    bay_widths_y=geo.bay_widths_y,
                    story_heights=geo.story_heights,
                    support_type=geo.support,
                    units=spec.units,
                    col_b=col_b, col_h=col_h, beam_b=beam_b, beam_h=beam_h,
                    fc=fc_model,
                    fy=fy_model,
                    unit_weight=unit_weight_model,
                ),
                "create_frame_model",
            ).data["project"]

        loads = spec.loads
        allow_partial = bool(geo and geo.omitted_columns)
        _require(
            apply_gravity_loads(
                proj,
                occupancy=loads.occupancy,
                tributary_width=loads.tributary_width,
                superimposed_dead=loads.superimposed_dead,
                custom_live_load=loads.live,
                partition_weight=loads.partition_weight,
                allow_partial_floor=allow_partial,
            ),
            "apply_gravity_loads",
        )
        seis = spec.seismic
        if seis is not None and seis.procedure == "elf":
            _require(
                apply_lateral_loads(
                    proj,
                    sds=seis.sds,
                    sd1=seis.sd1,
                    s1=seis.s1,
                    r_factor=seis.r_factor,
                    importance_factor=seis.importance_factor,
                    system_type=seis.system,
                    risk_category=seis.risk_category,
                    site_class=seis.site_class,
                    direction="both" if len(seis.directions) > 1 else seis.directions[0],
                    distribution="uniform",
                ),
                "apply_lateral_loads",
            )
        _require(
            generate_load_combinations(
                proj,
                sds=seis.sds if (seis is not None and seis.vertical_effect) else None,
                orthogonal_seismic=bool(seis is not None and seis.orthogonal_combination),
            ),
            "generate_load_combinations",
        )
        return proj

    def _build_from_grid(self, case: BenchmarkCase, sections: SectionPair) -> Any:
        """Partial grids (plan fixtures with omitted columns) are compiled through FloorPlanDraft."""
        geo = case.spec.geometry
        omitted = {tuple(c) for c in geo.omitted_columns}
        gx = [GridLineDraft(label=lab, direction="X", spacing_to_next=(geo.bay_widths_x[i] if i < len(geo.bay_widths_x) else 0.0))
              for i, lab in enumerate(geo.grid_labels_x)]
        gy = [GridLineDraft(label=lab, direction="Y", spacing_to_next=(geo.bay_widths_y[i] if i < len(geo.bay_widths_y) else 0.0))
              for i, lab in enumerate(geo.grid_labels_y)]
        present = [(x, y) for y in geo.grid_labels_y for x in geo.grid_labels_x if (x, y) not in omitted]
        (col_b, col_h), (beam_b, beam_h) = sections.column, sections.beam
        beams: List[BeamDraft] = []
        for y in geo.grid_labels_y:
            for x1, x2 in zip(geo.grid_labels_x, geo.grid_labels_x[1:]):
                if (x1, y) in present and (x2, y) in present:
                    beams.append(BeamDraft(from_grid=(x1, y), to_grid=(x2, y), section="BEAM", b=beam_b, h=beam_h))
        for x in geo.grid_labels_x:
            for y1, y2 in zip(geo.grid_labels_y, geo.grid_labels_y[1:]):
                if (x, y1) in present and (x, y2) in present:
                    beams.append(BeamDraft(from_grid=(x, y1), to_grid=(x, y2), section="BEAM", b=beam_b, h=beam_h))
        draft = FloorPlanDraft(
            title=case.name,
            units=case.spec.units,
            grids_x=gx,
            grids_y=gy,
            stories=[StoryDraft(name=f"Story {i + 1}", height=h) for i, h in enumerate(geo.story_heights)],
            columns=[ColumnDraft(grid=(x, y), section="COL", b=col_b, h=col_h) for x, y in present],
            beams=beams,
            support_type="Pinned" if geo.support == "pinned" else "Fixed",
            fc=case.spec.materials.fc_mpa * conversion_factor("N, mm", case.spec.units, "stress"),
            fy=case.spec.materials.fy_mpa * conversion_factor("N, mm", case.spec.units, "stress"),
            unit_weight=case.spec.materials.density_kg_m3 * 9.80665 * conversion_factor("N, m", case.spec.units, "weight_density"),
            dead_load=0.0,
            live_load=0.0,
        )
        return build_project_from_draft(draft)

    @staticmethod
    def _resize_fixture_sections(proj: Any, col_id: str, beam_id: str, sections: SectionPair) -> None:
        size = {col_id: sections.column, beam_id: sections.beam}  # resized; materials and cover kept
        proj.model.sections = [s.model_copy(update={"b": size[s.id][0], "h": size[s.id][1]}) if s.id in size else s
                               for s in proj.model.sections]

    # ------------------------------------------------------------------
    # Solution
    # ------------------------------------------------------------------
    def solve(self, case_id: str, sections: Optional[SectionPair] = None) -> OracleSolution:
        case = self.cases[case_id]
        used = self.sections_for(case, sections)
        key = (case_id, None if used is None else (*used.column, *used.beam))
        if key not in self._cache:
            self._cache[key] = self._solve(case, used)
        return self._cache[key]

    def _solve(self, case: BenchmarkCase, sections: Optional[SectionPair]) -> OracleSolution:
        sol = OracleSolution(case_id=case.id, sections=sections)
        reason = self.check_sections(case, sections)
        if reason:
            sol.error = reason
            return sol
        try:
            proj = _quiet(self.build_project, case, sections)
            validate_model(proj)
            vertical = "fz" if case.spec.cae is not None or case.spec.geometry.dimension == "3d" else "fy"
            _quiet(self._analyze, case, proj, sol, vertical)
            if case.deliverables.design != "none" or case.spec.initial_sections is not None:
                res = _require(_quiet(
                    run_design, proj, design_case_id="oracle",
                    allowable_bearing_pressure=case.spec.foundation.allowable_bearing_pressure
                    if case.spec.foundation is not None else None), "run_design")
                sol.design = {k: res.data[k] for k in (
                    "governing_dcr", "governing_member_id", "governing_member_type", "governing_limit_state",
                    "dcr_flexure", "dcr_shear",
                )}
                sol.metrics["governing_dcr"] = res.data["governing_dcr"]
            sol.concrete_volume = calculate_concrete_volume(proj, strict=True)
        except Exception as exc:  # recorded, never silently replaced
            sol.error = f"{type(exc).__name__}: {exc}"
        return sol

    def _analyze(self, case: BenchmarkCase, proj: Any, sol: OracleSolution, vertical: str) -> None:
        spec = case.spec
        m = sol.metrics

        def _case_reaction_sum(case_id: str, component: str) -> float:
            _require(run_analysis(proj, analysis_case_id=f"oracle_{case_id}", load_case_id=case_id), f"case {case_id}")
            return sum(getattr(r, component) for r in proj.analysis_results[f"oracle_{case_id}"].node_reactions)

        dead_ids = [lc.id for lc in proj.model.load_cases if any(t in lc.id.lower() for t in ("dead", "sdl"))]
        m["total_weight"] = sum(_case_reaction_sum(cid, vertical) for cid in dead_ids)
        # Design analyses: ACI 318-25 Table 6.6.3.1.1 stiffness with slenderness (§6.6.4); the drift and
        # stability checks follow from the seismic basis recorded by the load tools. Analysis-only
        # cases use gross sections.
        design_basis = dict(cracked_sections=True, second_order=True) if self._designs(case) else {}

        if spec.analysis == "cae":
            m["base_shear"] = abs(_case_reaction_sum("EQx", "fx"))
            self._modal(proj, m)
            if case.deliverables.design != "none":
                _require(run_analysis(proj, analysis_case_id="oracle_envelope", **design_basis), "static envelope")
            return

        if spec.analysis == "static":
            _require(run_analysis(proj, analysis_case_id="oracle_envelope", **design_basis), "static envelope")
            gravity = proj.analysis_results.get("COMB_1.2D+1.6L")
            if gravity is not None:
                m["max_base_reaction"] = max(abs(getattr(r, vertical)) for r in gravity.node_reactions)
            eq_x = next((lc.id for lc in proj.model.load_cases if lc.id.upper() in ("EQ_X", "EQX")), None)
            if eq_x is not None:
                m["base_shear"] = abs(sum(
                    r.fx for r in proj.analysis_results[eq_x].node_reactions
                ))
            proj.active_analysis_case = "oracle_envelope"
            return

        if spec.analysis == "modal":
            self._modal(proj, m)
            return

        seis = spec.seismic
        record = None if seis.ground_motion is None else str(self.repo_root / seis.ground_motion.file)
        if spec.analysis == "rsa":
            res = _require(
                run_response_spectrum(
                    proj,
                    analysis_case_id="oracle_rsa",
                    sds=seis.sds if seis.procedure == "rsa_code" else None,
                    sd1=seis.sd1 if seis.procedure == "rsa_code" else None,
                    s1=seis.s1,
                    ground_motion=record,
                    r_factor=seis.r_factor,
                    importance_factor=seis.importance_factor,
                    system_type=seis.system,
                    risk_category=seis.risk_category,
                    direction="both" if len(seis.directions) > 1 else seis.directions[0],
                    combination=seis.modal_combination or "CQC",
                    damping_ratio=seis.damping_ratio,
                    **design_basis,
                ),
                "run_response_spectrum",
            )
            m["base_shear"] = res.data["base_shear_by_direction"]["x"]
            m["fundamental_period"] = res.data["fundamental_period"]
            return

        res = _require(
            run_time_history(
                proj,
                analysis_case_id="oracle_tha",
                ground_motion=record,
                direction=seis.directions[0],
                damping_ratio=seis.damping_ratio,
            ),
            "run_time_history",
        )
        m["base_shear"] = res.data["peak_base_shear"]
        m["fundamental_period"] = res.data["fundamental_period"]
        m["peak_roof_displacement"] = res.data["peak_lateral_displacement"]

    @staticmethod
    def _designs(case: BenchmarkCase) -> bool:
        """Cases whose deliverable includes a code design or check (or a reflection trial design)."""
        return case.deliverables.design != "none" or case.spec.initial_sections is not None

    @staticmethod
    def _modal(proj: Any, m: Dict[str, float]) -> None:
        _require(run_analysis(proj, analysis_case_id="oracle_modal", analysis_type="modal", num_modes=12), "modal")
        modes = proj.analysis_results["oracle_modal"].modal_result.modes
        m["fundamental_period"] = modes[0].period
        m["period_t2"] = modes[1].period
        m["period_t3"] = modes[2].period
        m["modal_mass_ratio"] = sum(mode.mass_participation_x for mode in modes[:3])

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------
    def evaluate(
        self,
        case_id: str,
        sections: Optional[SectionPair] = None,
        claims: Optional[Dict[str, Any]] = None,
    ) -> OracleResult:
        """Verify a configuration's final sections and score its numerical claims.

        ``claims`` maps metric keys (``case_schema.METRICS``) to claimed values in spec units.
        """
        case = self.cases[case_id]
        claims = claims or {}
        if sections is None and case.spec.cae is None and case.spec.sections is None:
            sol = OracleSolution(case_id=case_id, sections=None, error="Missing column/beam sections.")
        else:
            sol = self.solve(case_id, sections)

        compliant: Optional[bool] = None
        violations: List[str] = []
        if case.deliverables.design == "design" and sections is not None:
            violations = case.design_space_violations(sections)
        if case.deliverables.design != "none":
            dcr = sol.governing_dcr
            compliant = bool(dcr is not None and dcr <= case.deliverables.max_dcr and sol.error is None and not violations)

        baseline = case.baseline_design
        economy = None
        if compliant and baseline is not None and baseline.feasible and sol.concrete_volume:
            economy = round(sol.concrete_volume / baseline.concrete_volume, 3)

        result = OracleResult(
            solution=sol, code_compliant=compliant, material_economy_ratio=economy, design_space_violations=violations
        )
        for metric in case.evaluation.required_metrics:
            truth = sol.metrics.get(metric)
            if truth is None:
                continue  # no reference (e.g. a withheld input leaves the structure undetermined): not scored
            claimed = claims.get(metric)
            if claimed is None:
                result.omitted_metrics.append(metric)
                continue
            result.claims_made.append(metric)
            try:
                err = abs(float(claimed) - truth) / max(abs(truth), 1e-4)
            except (TypeError, ValueError):
                err = math.inf
            result.metric_errors[metric] = round(err, 4) if math.isfinite(err) else 1.0
            if not err <= case.evaluation.claim_tolerance:
                result.hallucinated_metrics.append(metric)
        return result

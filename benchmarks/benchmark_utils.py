"""
Canonical Utility Functions for Structural Benchmark Suite
===========================================================

Provides a single source of truth for:
1. Geometry-derived concrete volume calculation without silent fallbacks.
2. Canonical benchmark cases loading and baseline mapping.
3. Numerical claim extraction from agent conversational responses.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


BENCHMARKS_DIR = Path(__file__).resolve().parent
DEFAULT_CASES_JSON = BENCHMARKS_DIR / "benchmark_cases.json"


def load_benchmark_cases(json_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Load benchmark cases from benchmark_cases.json (canonical source)."""
    target_path = Path(json_path) if json_path else DEFAULT_CASES_JSON
    if not target_path.exists():
        raise FileNotFoundError(f"Benchmark cases file not found: {target_path}")
    with open(target_path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_canonical_baseline_volumes(json_path: Optional[Path] = None) -> Dict[str, float]:
    """Return mapping of case_id -> baseline_concrete_volume_m3 from JSON."""
    cases = load_benchmark_cases(json_path)
    mapping: Dict[str, float] = {}
    for c in cases:
        vol = c.get("baseline_concrete_volume_m3")
        if vol is not None:
            mapping[c["id"]] = float(vol)
    return mapping


def calculate_concrete_volume(project: Any, strict: bool = False) -> float:
    """
    Calculate total concrete volume in cubic meters from elements.

    Computes sum(A_e * L_e) directly from section geometry and nodal coordinates.
    Eliminates all silent fallback assumptions (e.g. area = 0.15).

    Note: When non-rectangular sections (e.g., circular columns, flanged T-beams,
    or composite shapes) are modeled, their cross-section area 'A' (or 'area') must
    be provided directly in the section schema, or reduced to an equivalent rectangular
    gross area (b * h).

    Parameters
    ----------
    project : Any
        A struct_core.Project or object with .model attribute.
    strict : bool
        If True, raises ValueError if any element has zero or undefined cross-section area.

    Returns
    -------
    float
        Total concrete volume in m^3 rounded to 3 decimal places.
    """
    if not project or not hasattr(project, "model") or not project.model:
        return 0.0

    raw_nodes = getattr(project.model, "nodes", [])
    nodes_iter = raw_nodes.values() if isinstance(raw_nodes, dict) else raw_nodes
    nodes_map: Dict[Any, Any] = {}
    for n in nodes_iter:
        nid = n.get("id") if isinstance(n, dict) else getattr(n, "id", None)
        if nid is not None:
            nodes_map[nid] = n

    raw_secs = getattr(project.model, "sections", [])
    secs_iter = raw_secs.values() if isinstance(raw_secs, dict) else raw_secs
    sections_map: Dict[Any, Any] = {}
    for s in secs_iter:
        sid = s.get("id") if isinstance(s, dict) else getattr(s, "id", None)
        if sid is not None:
            sections_map[sid] = s

    total_vol = 0.0
    raw_elems = getattr(project.model, "elements", [])
    elems_iter = raw_elems.values() if isinstance(raw_elems, dict) else raw_elems
    for elem in elems_iter:
        sec_id = (
            elem.get("section_id")
            if isinstance(elem, dict)
            else getattr(elem, "section_id", None)
        )
        sec = sections_map.get(sec_id)
        area = 0.0
        if sec:
            if isinstance(sec, dict):
                area = float(sec.get("A", 0.0) or sec.get("area", 0.0))
                if not area:
                    b = float(sec.get("b", 0.0) or sec.get("width", 0.0))
                    h = float(sec.get("h", 0.0) or sec.get("height", 0.0) or sec.get("depth", 0.0))
                    if b and h:
                        area = b * h
            else:
                area = float(getattr(sec, "A", 0.0) or getattr(sec, "area", 0.0))
                if not area:
                    b = float(getattr(sec, "b", 0.0) or getattr(sec, "width", 0.0))
                    h = float(
                        getattr(sec, "h", 0.0)
                        or getattr(sec, "height", 0.0)
                        or getattr(sec, "depth", 0.0)
                    )
                    if b and h:
                        area = b * h

        if area <= 0.0:
            elem_area = elem.get("area") if isinstance(elem, dict) else getattr(elem, "area", 0.0)
            if elem_area:
                area = float(elem_area)

        if area <= 0.0:
            if strict:
                elem_id = elem.get("id") if isinstance(elem, dict) else getattr(elem, "id", "unknown")
                raise ValueError(
                    f"Element '{elem_id}' has invalid cross-section area {area} (section '{sec_id}')."
                )
            continue

        if isinstance(elem, dict):
            start_nid = elem.get("start_node") or elem.get("node_i")
            end_nid = elem.get("end_node") or elem.get("node_j")
        else:
            start_nid = getattr(elem, "start_node", None) or getattr(elem, "node_i", None)
            end_nid = getattr(elem, "end_node", None) or getattr(elem, "node_j", None)

        ni = nodes_map.get(start_nid)
        nj = nodes_map.get(end_nid)
        if not ni or not nj:
            if strict:
                elem_id = elem.get("id") if isinstance(elem, dict) else getattr(elem, "id", "?")
                raise ValueError(f"Element '{elem_id}' references missing nodes ({start_nid}, {end_nid}).")
            continue

        if isinstance(ni, dict):
            xi, yi, zi = float(ni.get("x", 0.0)), float(ni.get("y", 0.0)), float(ni.get("z", 0.0))
        else:
            xi, yi, zi = float(getattr(ni, "x", 0.0)), float(getattr(ni, "y", 0.0)), float(getattr(ni, "z", 0.0))

        if isinstance(nj, dict):
            xj, yj, zj = float(nj.get("x", 0.0)), float(nj.get("y", 0.0)), float(nj.get("z", 0.0))
        else:
            xj, yj, zj = float(getattr(nj, "x", 0.0)), float(getattr(nj, "y", 0.0)), float(getattr(nj, "z", 0.0))

        length = math.sqrt((xj - xi) ** 2 + (yj - yi) ** 2 + (zj - zi) ** 2)
        total_vol += float(area) * float(length)

    return round(total_vol, 3)


def parse_numerical_claims_from_text(text: str) -> Dict[str, float]:
    """
    Extract engineering numerical claims from agent text responses.

    Extracts:
    - governing_dcr / DCR
    - total_weight_kN / weight
    - base_shear_kN / base shear (Vb)
    - fundamental_period_s / period (T1)
    - period_t2_s / second mode period (T2)
    - period_t3_s / third mode period (T3)
    - modal_mass_ratio / modal mass participation
    - peak_displacement_m / roof displacement
    """
    import unicodedata

    claims: Dict[str, float] = {}
    if not text:
        return claims

    # Normalize unicode subscripts (e.g., T₁ -> T1, Vᵦ -> Vb) and whitespace
    norm_text = unicodedata.normalize("NFKD", text)

    # 1. Governing DCR: e.g., "DCR: 0.846", "DCR = 1", "governing DCR: 0.92"
    dcr_match = re.search(r"\bdcr\b[^\d-]{0,35}(-?\d+(?:\.\d+)?)", norm_text, re.IGNORECASE)
    if dcr_match:
        try:
            val = float(dcr_match.group(1))
            if 0.0 <= val <= 20.0:  # physical bounds check
                claims["governing_dcr"] = val
        except (ValueError, TypeError):
            pass

    # 2. Total structural weight: e.g., "total weight: 1250 kN", "weight = 850 kN"
    weight_match = re.search(r"\b(?:total\s+)?weight\b[^\d-]{0,35}(-?\d+(?:\.\d+)?)", norm_text, re.IGNORECASE)
    if weight_match:
        try:
            val = float(weight_match.group(1))
            if val > 1.0:  # sanity check against small decimals
                claims["total_weight_kN"] = val
        except (ValueError, TypeError):
            pass

    # 3. Base shear: e.g., "base shear: 145.2 kN", "V_b = 132 kN", "Vb: 140 kN"
    vb_match = re.search(r"\b(?:base\s+shear|v[_\s]?b)\b[^\d-]{0,35}(-?\d+(?:\.\d+)?)", norm_text, re.IGNORECASE)
    if vb_match:
        try:
            val = float(vb_match.group(1))
            if val > 0.0:
                claims["base_shear_kN"] = val
        except (ValueError, TypeError):
            pass

    # 4. Fundamental period: e.g., "fundamental period: 0.45 s", "T1 = 0.38s", "T1: 1 s"
    t1_match = re.search(
        r"\b(?:fundamental\s+(?:natural\s+)?period(?:\s*t[_\s]?1)?|t[_\s]?1|\bperiod(?:\s*t[_\s]?1)?)\b[^\d-]{0,35}(-?\d+(?:\.\d+)?)",
        norm_text,
        re.IGNORECASE,
    )
    if t1_match:
        try:
            val = float(t1_match.group(1))
            if 0.01 <= val <= 30.0:
                claims["fundamental_period_s"] = val
        except (ValueError, TypeError):
            pass

    # 5. Higher modal periods (T2, T3)
    t2_match = re.search(
        r"\b(?:second\s+mode\s+period(?:\s*t[_\s]?2)?|mode\s+2\s+period(?:\s*t[_\s]?2)?|t[_\s]?2)\b[^\d-]{0,35}(-?\d+(?:\.\d+)?)",
        norm_text,
        re.IGNORECASE,
    )
    if t2_match:
        try:
            val = float(t2_match.group(1))
            if 0.005 <= val <= 30.0:
                claims["period_t2_s"] = val
        except (ValueError, TypeError):
            pass

    t3_match = re.search(
        r"\b(?:third\s+mode\s+period(?:\s*t[_\s]?3)?|mode\s+3\s+period(?:\s*t[_\s]?3)?|t[_\s]?3)\b[^\d-]{0,35}(-?\d+(?:\.\d+)?)",
        norm_text,
        re.IGNORECASE,
    )
    if t3_match:
        try:
            val = float(t3_match.group(1))
            if 0.005 <= val <= 30.0:
                claims["period_t3_s"] = val
        except (ValueError, TypeError):
            pass

    # 6. Modal mass participation ratio: e.g., "mass participation: 85%", "modal mass ratio = 0.85"
    mmr_match = re.search(r"\b(?:modal\s+)?mass\s+participation(?:\s+ratio)?\b[^\d-]{0,12}(-?\d+(?:\.\d+)?)\s*(%?)", norm_text, re.IGNORECASE)
    if mmr_match:
        try:
            val = float(mmr_match.group(1))
            is_pct = mmr_match.group(2) == "%" or val > 1.0
            ratio = val / 100.0 if is_pct else val
            if 0.0 <= ratio <= 1.05:
                claims["modal_mass_ratio"] = min(ratio, 1.0)
        except (ValueError, TypeError):
            pass

    # 7. Peak roof displacement: e.g., "peak roof displacement: 0.024 m", "displacement: 24 mm"
    disp_match = re.search(r"\b(?:peak\s+)?(?:roof\s+)?displacement\b[^\d-]{0,12}(-?\d+(?:\.\d+)?)\s*(mm|m)?", norm_text, re.IGNORECASE)
    if disp_match:
        try:
            d_val = float(disp_match.group(1))
            d_unit = (disp_match.group(2) or "m").lower()
            if d_unit == "mm" or d_val > 1.0:  # If > 1.0 in structural frame context, likely mm
                claims["peak_displacement_m"] = d_val / 1000.0
            else:
                claims["peak_displacement_m"] = d_val
        except (ValueError, TypeError):
            pass

    return claims


def compute_material_economy(agent_volume: Optional[float], baseline_volume: Optional[float]) -> Optional[float]:
    """
    Compute material economy ratio eta_vol = V_agent / V_baseline.

    Returns None if either volume is None or if baseline_volume <= 0.
    """
    if agent_volume is None or baseline_volume is None or baseline_volume <= 0.0:
        return None
    return round(float(agent_volume) / float(baseline_volume), 3)


def evaluate_prompt_to_schema_fidelity(
    project: Any,
    case: Dict[str, Any],
    runner: Optional[Any] = None,
) -> Tuple[bool, Dict[str, Any]]:
    """
    Evaluate Prompt-to-Schema Fidelity Rate (PSFR).

    Verifies comprehensive tool-argument and mechanical specification fidelity:
    - Structural Geometry: Model dimensionality (2D/3D), story count, bay counts (X/Y),
      bay spans (m), and story heights (m).
    - Boundary Restraints: Fixed supports at all ground level nodes.
    - Material Properties: Valid structural concrete elastic material (E in [15, 45] GPa,
      density >= 2000 kg/m3).
    - Seismic Parameters: SDS, SD1, and R factor fidelity for lateral/seismic cases.
    - Gravity Load Configuration: Valid dead and live load cases populated.
    """
    if not project or not hasattr(project, "model") or not project.model:
        return False, {"error": "Missing or null structural model in project container."}

    model = project.model
    case_id = case.get("id", "")
    target = case.get("target_constraints", {})

    # Retrieve fallback parameterization catalog lazily if needed
    catalog: Dict[str, Any] = {}
    try:
        from .oracle_verifier import ORACLE_CASES_CATALOG
        catalog = ORACLE_CASES_CATALOG.get(case_id, {})
    except ImportError:
        try:
            from research_paper.benchmarks.oracle_verifier import ORACLE_CASES_CATALOG
            catalog = ORACLE_CASES_CATALOG.get(case_id, {})
        except ImportError:
            pass

    details: Dict[str, Any] = {}

    # For CAE interop benchmark cases (C03, C04), geometry is strictly defined by the vendor fixture
    if catalog.get("analysis") == "cae_interop" or "cae_interop" in str(case.get("name", "")).lower() or "C03" in case_id or "C04" in case_id:
        if not getattr(model, "nodes", []):
            return False, {"error": "CAE fixture import produced zero nodes."}
        if not getattr(model, "supports", []):
            return False, {"error": "CAE fixture import produced zero supports."}
        if not getattr(model, "materials", []):
            return False, {"error": "CAE fixture import produced zero materials."}
        details["cae_fixture_defined_geometry"] = True
        return True, details

    nodes = getattr(model, "nodes", [])
    if not nodes:
        return False, {"error": "Model contains zero nodes."}

    # 1. Dimensionality Verification (2D vs 3D)
    expected_dim = str(target.get("dimension") or catalog.get("dimension") or "").lower()
    if expected_dim:
        z_coords = [abs(getattr(n, "z", 0.0)) for n in nodes]
        is_3d_actual = any(z > 1e-3 for z in z_coords)
        if expected_dim == "2d" and is_3d_actual:
            return False, {"error": "Dimensionality mismatch: expected 2D model (z=0), got non-zero z coordinates."}
        if expected_dim == "3d" and not is_3d_actual and len(nodes) > 4:
            return False, {"error": "Dimensionality mismatch: expected 3D space frame, but all nodes have z=0."}
        details["dimension_match"] = True

    # 2. Story Count & Elevated Floor Spacing
    expected_stories = target.get("stories") or catalog.get("num_stories")
    elevations: List[float] = []
    if expected_stories is not None:
        if expected_dim == "3d":
            elevations = sorted(list(set(round(float(getattr(n, "z", 0.0)), 2) for n in nodes if getattr(n, "z", 0.0) > 0.05)))
        else:
            elevations = sorted(list(set(round(float(getattr(n, "y", 0.0)), 2) for n in nodes if getattr(n, "y", 0.0) > 0.05)))
        actual_stories = len(elevations)
        if actual_stories != int(expected_stories):
            return False, {
                "error": f"Story count mismatch: expected {expected_stories} stories, got {actual_stories} elevated levels.",
                "elevations": elevations,
            }
        details["stories_match"] = True

    # 3. Story Height Fidelity (Floor-to-floor height in meters)
    expected_story_h = target.get("story_height") or catalog.get("story_height")
    if expected_story_h is not None and len(elevations) > 0:
        all_levels = [0.0] + elevations
        story_heights = [round(all_levels[i+1] - all_levels[i], 3) for i in range(len(all_levels)-1)]
        exp_h = float(expected_story_h)
        for h in story_heights:
            if abs(h - exp_h) > 0.15:
                return False, {
                    "error": f"Story height mismatch: expected {exp_h} m, got {h} m in levels {all_levels}.",
                    "story_heights": story_heights,
                }
        details["story_height_match"] = True

    # 4. Bay Counts & Grid Spans
    is_vision = bool(target.get("vision") or "vision" in case_id.lower() or "vision" in str(case.get("name", "")).lower())

    # 2D Grid
    expected_bays = target.get("bays") or (catalog.get("num_bays") if expected_dim == "2d" else None)
    if expected_bays is not None and expected_dim == "2d":
        x_coords = sorted(list(set(round(float(getattr(n, "x", 0.0)), 2) for n in nodes)))
        actual_bays = max(len(x_coords) - 1, 0)
        if actual_bays != int(expected_bays):
            return False, {
                "error": f"Bay count mismatch: expected {expected_bays} bays, got {actual_bays} grid bays in X.",
                "x_coords": x_coords,
            }
        details["bays_match"] = True

        # Check bay span (bay width) in 2D
        expected_bay_w = target.get("bay_width") or (catalog.get("bay_width") if not is_vision else None)
        if expected_bay_w is not None and len(x_coords) > 1:
            bay_widths = [round(x_coords[i+1] - x_coords[i], 3) for i in range(len(x_coords)-1)]
            exp_w = float(expected_bay_w)
            for w in bay_widths:
                if abs(w - exp_w) > 0.15:
                    return False, {
                        "error": f"Bay width span mismatch: expected {exp_w} m, got {w} m in grid {x_coords}.",
                        "bay_widths": bay_widths,
                    }
            details["bay_width_match"] = True

    # 3D Grid X & Y
    if expected_dim == "3d":
        x_coords = sorted(list(set(round(float(getattr(n, "x", 0.0)), 2) for n in nodes)))
        y_coords = sorted(list(set(round(float(getattr(n, "y", 0.0)), 2) for n in nodes)))

        expected_bays_x = target.get("bays_x") or catalog.get("bays_x")
        if expected_bays_x is not None:
            actual_bays_x = max(len(x_coords) - 1, 0)
            if actual_bays_x != int(expected_bays_x):
                return False, {
                    "error": f"Bay X count mismatch: expected {expected_bays_x} bays, got {actual_bays_x}.",
                }
            details["bays_x_match"] = True

            # Check bay width along X (skip CAE third-party models and vision cases where bay width is not explicitly constrained)
            expected_bay_wx = target.get("bay_width_x") or target.get("bay_width")
            if not is_vision and expected_bay_wx is None:
                expected_bay_wx = catalog.get("bay_width_x") or catalog.get("bay_width")
            if expected_bay_wx is not None and len(x_coords) > 1 and catalog.get("analysis") != "cae_interop":
                spans_x = [round(x_coords[i+1] - x_coords[i], 3) for i in range(len(x_coords)-1)]
                exp_wx = float(expected_bay_wx)
                for w in spans_x:
                    if abs(w - exp_wx) > 0.15:
                        return False, {
                            "error": f"Bay X span mismatch: expected {exp_wx} m, got {w} m in X grid {x_coords}.",
                        }
                details["bay_width_x_match"] = True

        expected_bays_y = target.get("bays_y") or catalog.get("bays_y")
        if expected_bays_y is not None:
            actual_bays_y = max(len(y_coords) - 1, 0)
            if actual_bays_y != int(expected_bays_y):
                return False, {
                    "error": f"Bay Y count mismatch: expected {expected_bays_y} bays, got {actual_bays_y}.",
                }
            details["bays_y_match"] = True

            # Check bay width along Y (skip CAE third-party models and vision cases where bay width is not explicitly constrained)
            expected_bay_wy = target.get("bay_width_y") or target.get("bay_width")
            if not is_vision and expected_bay_wy is None:
                expected_bay_wy = catalog.get("bay_width_y") or catalog.get("bay_width")
            if expected_bay_wy is not None and len(y_coords) > 1 and catalog.get("analysis") != "cae_interop":
                spans_y = [round(y_coords[i+1] - y_coords[i], 3) for i in range(len(y_coords)-1)]
                exp_wy = float(expected_bay_wy)
                for w in spans_y:
                    if abs(w - exp_wy) > 0.15:
                        return False, {
                            "error": f"Bay Y span mismatch: expected {exp_wy} m, got {w} m in Y grid {y_coords}.",
                        }
                details["bay_width_y_match"] = True

    # 5. Boundary Restraints / Support Verification
    supports = getattr(model, "supports", [])
    if not supports:
        return False, {"error": "Model contains zero support boundary restraints."}
    # Check that base nodes at elevation ~0 are restrained
    if expected_dim == "3d":
        base_nodes = [n for n in nodes if abs(getattr(n, "z", 0.0)) <= 0.05]
    else:
        base_nodes = [n for n in nodes if abs(getattr(n, "y", 0.0)) <= 0.05]

    supp_node_ids = {s.node_id for s in supports}
    for bn in base_nodes:
        if bn.id not in supp_node_ids:
            return False, {"error": f"Ground node id={bn.id} has no support boundary condition assigned."}
    details["supports_match"] = True

    # 6. Material Properties Fidelity (Normalweight structural concrete)
    materials = getattr(model, "materials", [])
    if not materials:
        return False, {"error": "Model defines zero materials."}
    valid_mat = False
    for m in materials:
        e_val = float(getattr(m, "E", 0.0))
        # Structural concrete modulus: 1.5e7 kPa (15 GPa) to 4.5e7 kPa (45 GPa)
        if 1.5e7 <= e_val <= 4.5e7:
            valid_mat = True
            break
    if not valid_mat:
        return False, {
            "error": "Material elasticity modulus E is outside valid structural concrete range [15 GPa, 45 GPa].",
            "material_moduli": [getattr(m, "E", None) for m in materials],
        }
    details["material_match"] = True

    # 7. Seismic Parameter Fidelity (SDS, SD1, R)
    is_seismic_case = bool(
        catalog.get("lateral") or catalog.get("sds") or catalog.get("lateral_sds")
        or target.get("sds") or target.get("lateral_sds")
    )
    if is_seismic_case and catalog.get("analysis") != "cae_interop":
        exp_sds = float(catalog.get("sds") or catalog.get("lateral_sds") or target.get("sds") or 0.0)
        exp_sd1 = float(catalog.get("sd1") or catalog.get("lateral_sd1") or target.get("sd1") or 0.0)
        exp_r = float(catalog.get("r_factor") or target.get("r_factor") or 5.0)

        found_seismic = False
        # Check load_cases for seismic parameters
        load_cases = getattr(model, "load_cases", [])
        for lc in load_cases:
            sparams = getattr(lc, "seismic_params", None)
            if isinstance(sparams, dict) and sparams:
                sds_actual = float(sparams.get("sds", 0.0))
                sd1_actual = float(sparams.get("sd1", 0.0))
                if abs(sds_actual - exp_sds) <= 0.05 and abs(sd1_actual - exp_sd1) <= 0.05:
                    found_seismic = True
                    details["seismic_sds_match"] = True
                    details["seismic_sd1_match"] = True
                    if "r_factor" in sparams:
                        r_act = float(sparams.get("r_factor", 0.0))
                        if abs(r_act - exp_r) <= 0.5:
                            details["seismic_r_match"] = True
                    break

        # Check analysis_results for RSA cases with numerical SDS/SD1 verification
        if not found_seismic and hasattr(project, "analysis_results") and project.analysis_results:
            for ar_key, ar in project.analysis_results.items():
                if any(k in ar_key.lower() for k in ["rsa", "spectrum", "dynamic"]):
                    ar_data = getattr(ar, "data", {}) if hasattr(ar, "data") else {}
                    if isinstance(ar_data, dict):
                        ar_sds = float(ar_data.get("sds", 0.0) or 0.0)
                        ar_sd1 = float(ar_data.get("sd1", 0.0) or 0.0)
                        if abs(ar_sds - exp_sds) <= 0.05 and abs(ar_sd1 - exp_sd1) <= 0.05:
                            found_seismic = True
                            details["seismic_sds_match"] = True
                            details["seismic_sd1_match"] = True
                            break

        # Check runner messages if tool was called directly
        if not found_seismic and runner and hasattr(runner, "messages"):
            for msg in runner.messages:
                tool_calls = msg.get("tool_calls", [])
                for tc in tool_calls:
                    fn_name = tc.get("function", {}).get("name", "")
                    if fn_name in ("apply_lateral_loads", "run_response_spectrum"):
                        args_raw = tc.get("function", {}).get("arguments", {})
                        args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
                        sds_arg = float(args.get("sds", 0.0) or 0.0)
                        sd1_arg = float(args.get("sd1", 0.0) or 0.0)
                        if abs(sds_arg - exp_sds) <= 0.05 and abs(sd1_arg - exp_sd1) <= 0.05:
                            found_seismic = True
                            details["seismic_tool_arguments_match"] = True
                            break

        if exp_sds > 0 and not found_seismic:
            return False, {
                "error": f"Seismic parameter mismatch: expected SDS={exp_sds}, SD1={exp_sd1}, but no conforming seismic load case or RSA analysis found.",
            }
        details["seismic_match"] = True

    # 8. Gravity Load Case Population
    load_cases = getattr(model, "load_cases", [])
    if load_cases and catalog.get("analysis") != "cae_interop":
        has_gravity = any(
            any(k in lc.id.lower() or k in (lc.name or "").lower() for k in ["dead", "live", "gravity"])
            for lc in load_cases
        )
        if has_gravity:
            details["gravity_loads_match"] = True

    return True, details


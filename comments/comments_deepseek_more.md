## Critical (must fix before submission)

1. **B08 is misnamed/mismodeled.** The "Asymmetric / Torsional" case uses symmetric 2×2 bays @ 6.0 m — zero torsional eccentricity. Rename to `B08_3D_BiDirectional_Seismic` and drop all "asymmetric/torsional" language from prompt, description, experiment plan, etc.

2. **C05/C06 vision targets are unverified against the PNG fixtures.** `target_constraints` bay counts/spacings (C05: 3×3 @ 6.0 m; C06: 4×3 @ 3.735/3.66 m) may not match the actual drawings.

[My comment: Let me know if you want me to give you the dimensions from the plan drawings.]

3. **CAE PSFR skips bay *width* but not bay *count* or *story count*.** Add an early return in `evaluate_prompt_to_schema_fidelity` when `catalog["analysis"] == "cae_interop"`, skipping all geometry checks (fixture defines geometry).

4. **A08's initial DCR = 10.519 is implausible and looks adversarial.** Either reduce initial sections to DCR ≈ 3–4 (e.g., columns 0.30×0.30, beams 0.30×0.45), or justify A08 as a deliberate lower-bound stress test. Also confirm `modify_project` uses DCR-scaled resizing (h_new ∝ √DCR) — a fixed-increment heuristic cannot close a 10× gap within 20 turns.

5. **CHR penalizes omission, which is unfair and invites a "rigged metric" critique.** Redefine CHR as **precision over claimed metrics**: `CHR = |wrong claims| / |claims made|`. Missing claims are absent, not hallucinated. Alternatively, derive `active_metrics` from the prompt text (A05 asks for T₁/T₂/T₃, not total weight).

6. **CAE round-trip verified only by file existence, not numerical fidelity.** After export, re-import the `.s2k`/`.e2k`, then compare against the original: node count, element count, total mass (<1% rel. error), T₁ (<1% rel. error), boundary-condition count. Add `roundtrip_fidelity` per case to results.

## High priority

7. **Single-seed runs weaken statistical claims.** Change reproducibility protocol to `--seeds 5` for `full_agent`/`ablated`, `--seeds 1` for `direct_llm`/`code_gen`. Update `analyze_results.py` to plot mean ± std and run paired Wilcoxon signed-rank or bootstrap tests between `full_agent` and `ablated`.

8. **Ablation post-hoc violation check is dead code or conflates outcomes.** If `allow_model_recreation=False` already blocks recreation, delete the check. Otherwise, remove `create_frame_model` from `runner.tools` *before* the run (as you already do for `modify_project`), so ablated failures mean "could not converge without reflection," not "violated protocol."

9. **No deterministic heuristic baseline.** Add `--config heuristic`: `col = (0.05·H, 0.05·H)`, `beam = (L/14, L/12)`, then `while DCR > 1.0: scale by √DCR`. Establishes the non-LLM floor; essential to justify the neuro-symbolic layer.

10. **No failure-mode taxonomy.** Add a `failure_mode` field to each case result (`"model_construction"`, `"missing_tool"`, `"dcr_non_convergence"`, `"artifact_missing"`, `"schema_fidelity"`), tabulate per configuration in `analyze_results.py`. Feeds Section 5 diagnostics.

11. **Material economy only shows matching, not outperformance.** Add `min_feasible_volume_m3` per design case (grid search subject to DCR ≤ 1.0) and report `design_efficiency = V_baseline / V_agent`. If the agent beats η = 1.0, report it as a win.

## Medium priority

12. **A06 and A07 both hit DCR = 0.880 by As,min — looks like padding.** Elevate the `experiment_plan.md` §3.2 note to a dedicated "Design-case diversity" paragraph in Section 4, and add `governing_limit_state` column to the per-case results table (already computed in `generate_human_baselines.py`).

13. **B03's 0.80×0.80 columns at DCR = 0.983 look oversized for a 3-story building.** Either re-size to a realistic conventional section (0.55–0.65 m; resulting DCR will be 1.2–1.5, making B03 a reflection case) or rename to `B03_3D_Seismic_ELF_NearLimit` and state the baseline intentionally sits at the limit.

14. **`evaluate_prompt_to_schema_fidelity` seismic check is too loose.** Condition 2 (`any RSA analysis result exists`) passes regardless of SDS/SD1. Remove it. Read SDS/SD1 numerically from `analysis_results["rsa_*"].data` (or `load_cases[*].seismic_params` for ELF); keep the message-history fallback only when the project object does not expose parameters, and document it.

15. **`calculate_concrete_volume` only handles rectangular sections.** Add a docstring note ("non-rectangular sections must be reduced to equivalent area") or extend the schema with a `section_shape` discriminator.

16. **Vision cases lack human ground-truth validation.** Have 2–3 structural engineers independently annotate the two floor plans; report Cohen's κ or % agreement against `target_constraints`.

17. **Seeds, temperature, and model version pinning are undocumented.** Add a "Reproducibility" subsection to `04_experimental_setup.md`: seeds per config, `temperature=0.0`, canonical model IDs (`gemini-2.5-flash`, not the alias `gemini-3.8-flash`), API access date.

## Low priority / polish

18. Add PSFR bar chart to `analyze_results.py`.
19. State in `oracle_verifier.py` docstring that T₁ is required but T₂/T₃ are optional-if-claimed.
20. Ship raw CSI output files in `benchmarks/fixtures/csi_reference/` to substantiate the hardcoded reference values in `verify_cae_parity.py`.
21. Remove "mode shapes" from A05/B04 prompts if not a deliverable, or add an artifact check for mode-shape output.
22. Consider one non-rectangular or non-moment-frame case (shear wall, braced frame) to broaden generalizability.

## Highest-leverage fixes (do these first)

- **#5** (CHR → precision-over-claims) — removes the most likely "rigged metric" critique, ~1 hour of code.
- **#7** (multi-seed + significance tests) — converts single-sample anecdotes into publishable statistics.
- **#1** (B08 asymmetry) — reviewers will catch this immediately.
- **#6** (CAE round-trip fidelity) — substantiates the "lossless round-trip" claim.

## What is already strong (do not break)

- All 16 baseline concrete volumes are arithmetically correct.
- Oracle-verifier design (equifinality elimination, regime-specific metrics) is a genuine differentiator.
- `calculate_concrete_volume(strict=True)` failing loudly is good engineering.
- Timestamped non-clobbering outputs across harness and analysis scripts.
- `verify_cae_parity.py` validates against commercial software — most structural-AI papers never do this.
- Two-paper strategy (methodology + software) is well-scoped.
## P0 — Must fix before regenerating any Section 5 figures

### P0-1. Sync `experiment_plan.md` A08 to the actual sections

`experiment_plan.md` §2 still says A08 initializes at `0.25×0.25 / 0.25×0.30` with `DCR₀ = 10.519`. `benchmark_cases.json` now has `0.30×0.30 / 0.30×0.45`.

**Do:**
- Run `python research_paper/benchmarks/generate_human_baselines.py` (dry run) and note the new A08 initial DCR (it will print).
- Update `experiment_plan.md` §2 A08 line to the actual initial sections and actual DCR₀.
- Also update `benchmark_cases.json` `A08` prompt to match if it still says 0.25×0.25 (it currently says 0.30×0.30, so just verify).

**Acceptance:** A08 sections and DCR₀ match between `experiment_plan.md`, `benchmark_cases.json`, and `HUMAN_BASELINES_CATALOG` in `generate_human_baselines.py`.

### P0-2. Surface `CCR_claims` in analysis outputs

`claim_completeness_pct` is now computed per case but never displayed. RQ1 is undefendable without it.

**Do:**
1. `analyze_results.py::print_and_save_markdown_table`: add columns `CHR %` and `Claim Completeness %` (rename current CHR column from `Hallucination (CHR)`).
2. Add an aggregate `avg_claim_completeness_pct` to each summary row (mean of `claim_completeness_pct` across cases).
3. `analyze_results.py::generate_plots`: add a paired-bar figure `fig_chr_vs_completeness_<ts>.png` — two bars per model/config, one for CHR, one for CCR_claims, with `axhline(100, ...)` for completeness reference. This is the "honest" analogue of the current hallucination plot.
4. In `run_benchmarks.py::main`, ensure `avg_claim_completeness` (already computed) is stored in `summary`.

**Acceptance:** Summary table contains both metrics; new figure is produced; `summary["claim_completeness_rate_pct"]` is non-null.

### P0-3. Fix Wilcoxon pairing (currently pairs last-seed-only)

`analyze_results.py::compute_statistical_significance` builds `fa_cases = {c["case_id"]: c for c in ...}` which silently keeps only the **last seed per case**. With `--seeds 5` this destroys 80% of the data and biases the p-value.

**Do:** Replace the pairing with **per-case means over seeds**:

```python
def _per_case_means(cases, metric_fn):
    by_cid = defaultdict(list)
    for c in cases:
        by_cid[c["case_id"]].append(metric_fn(c))
    return {cid: float(np.mean(vals)) for cid, vals in by_cid.items() if vals}
```

Then run Wilcoxon on `list(mean_by_cid.values())` aligned by `common_ids`. Also report both:
- `p_wilcox_per_case` (paired on 24 case means) — the paper's primary test
- `n_seeds` used in the aggregation

**Acceptance:** `statistical_significance_report_*.md` shows `N Pairs = 24` (or 16 for CCR), not `N Pairs = 5`.

---

## P1 — Must fix before running the full campaign

### P1-1. Read `case_results_mean_std` in `analyze_results.py`

`run_benchmarks.py` writes `case_results_mean_std` when `seeds > 1`, but nothing consumes it. Currently the convergence plot in `analyze_results.py` §2 plots all 5×N seed traces with identical labels — unreadable.

**Do:**
1. In `load_all_results`, if `"case_results_mean_std"` exists, propagate it.
2. In `generate_plots` §2 (convergence), aggregate `dcr_history` per case across seeds, plot **mean ± std shaded band**, one line per case (not per seed).
3. In `print_and_save_markdown_table`, display `mean ± std` for TCR/CCR/CHR/η where `mean_std` exists.

**Acceptance:** With 5 seeds and 3 reflection cases, the convergence plot shows 3 shaded-band curves, not 15 raw traces.

### P1-2. Fix failure-mode table for seeds

`print_and_save_failure_mode_table` counts per **run** not per **case**. With 5 seeds, a case failing 2/5 shows "2" and inflates totals.

**Do:** Report two columns per mode:
- `cases_failing_at_least_once`
- `cases_failing_all_seeds`

Use `defaultdict(list)` grouped by `case_id`.

**Acceptance:** Failure-mode table sums to ≤ 24 per column.

### P1-3. Report `unique_cases` alongside `total_runs`

`summary["total_cases"]` is currently `n_total` (runs, e.g. 120). Rename/split:

```python
"total_runs": n_total,
"unique_cases": len({r["case_id"] for r in results}),
"design_runs": n_design_cases,
"unique_design_cases": len({r["case_id"] for r in results if r.get("design_required")}),
"case_wise_success_rate_pct": <fraction of unique cases where all seeds succeeded>
```

Update `analyze_results.py` summary table headers to say `Runs (TCR)` / `Cases`.

### P1-4. B03 vs B08 are now near-duplicates

Both are 2×2 bays @ 6.0 m, 3 stories @ 3.5 m, symmetric, ELF+ASCE 7 combos, RC moment frame. Only SDS/SD1 and baseline column size differ. A reviewer will ask why both exist.

**Do one:**
- **(Preferred)** Rewrite B08 so it is genuinely bidirectional: require the agent to run **two separate analyses** (X-primary: 1.0EX + 0.3EY; Y-primary: 0.3EX + 1.0EY) and envelope both, then design. Update `expected_tools` to include `run_analysis` twice (or a distinct `run_bidirectional_seismic` if it exists). Update `experiment_plan.md` §2 B08.
- **(Fallback)** Remove B08, add a genuinely different case (asymmetric plan with an offset bay, or a setback). Requires `create_frame_model` extension — likely out of scope for this cycle.
- **(Minimum)** Rename B08 to reflect what it is (e.g., `B08_3D_Seismic_ELF_LowerIntensity`) and add one sentence in `experiment_plan.md` §2 explaining that B03 and B08 bracket the seismic intensity range (SDS 1.2 vs 1.0) for the same geometry, to test design robustness under different demand levels. Update `paper_idea.md` §3 and §5 accordingly.

**Acceptance:** Either a genuinely different B08, or an explicit justification visible in `experiment_plan.md`.

### P1-5. CAE PSFR early-return must still validate the model

`evaluate_prompt_to_schema_fidelity` currently returns `True` unconditionally for CAE cases — even if the agent produced an empty model.

**Do:** In the CAE early-return block, add:

```python
if not nodes:
    return False, {"error": "CAE fixture import produced zero nodes."}
if not supports:
    return False, {"error": "CAE fixture import produced zero supports."}
if not materials:
    return False, {"error": "CAE fixture import produced zero materials."}
```

**Acceptance:** Manually instantiate a `Project()` with empty model and call `evaluate_prompt_to_schema_fidelity` for C03; must return `False`.

### P1-6. Heuristic baseline must respect prompt-specified sections for non-design cases

`run_heuristic_baseline` uses `0.05·H` / `L/12` sizing for **all** cases, ignoring the prompt-specified sections in A05, B01, B04, C01, C02. This makes the heuristic fail PSFR-style on those cases while the LLM agent (which reads the prompt) passes — an unfair comparison.

**Do:**
```python
if not requires_design or catalog.get("analysis") == "cae_interop":
    col_b, col_h = catalog.get("default_col", (0.40, 0.40))
    beam_b, beam_h = catalog.get("default_beam", (0.30, 0.50))
else:
    col_dim = max(0.30, ...)  # existing heuristic
    ...
```

Also for CAE cases: set `success = None`, `failure_mode = "not_applicable"`, and `prompt_to_schema_fidelity_passed = None` (currently leaks `True`).

**Acceptance:** Re-run heuristic on A05; `concrete_volume_m3` must match the prompt-specified 0.40×0.40 / 0.30×0.50 geometry.

---

## P2 — Fix before the final campaign run

### P2-1. Failure-mode classifier missing model-creation tools

`run_single_case` checks `"create_frame_model" in expected_tools` but C05/C06 use `create_model_from_plan_draft`, and C03/C04 use `import_from_sap2000`/`import_from_etabs`.

**Do:** Use the actual set:
```python
MODEL_CREATION_TOOLS = {"create_frame_model", "create_model_from_plan_draft",
                         "import_from_sap2000", "import_from_etabs"}
expected_creation = [t for t in expected_tools if t in MODEL_CREATION_TOOLS]
if nodes_count == 0 or elems_count == 0 or (expected_creation and not any(t in successful_tools for t in expected_creation)):
    failure_mode = "model_construction"
```

### P2-2. PSFR seismic check uses `or` instead of `and`

In `benchmark_utils.py`:
```python
if abs(ar_sds - exp_sds) <= 0.05 or abs(ar_sd1 - exp_sd1) <= 0.05:
```
→ `and`. An RSA result with wrong SDS but accidentally-right SD1 currently passes.

### P2-3. Force required metrics in CCR_claims for modal/time-history cases

A05/B04 prompts explicitly require T1, T2, T3, MMR. C01/C02 require peak displacement and base shear. `active_metrics` for these cases only includes `[total_weight, fundamental_period]`, so an agent that reports weight + T1 gets CCR_claims = 100%.

**Do:**
1. Add `required_metrics` to `ORACLE_CASES_CATALOG`:
   - A05: `["fundamental_period_s", "period_t2_s", "period_t3_s", "modal_mass_ratio"]`
   - B04: same
   - C01: `["fundamental_period_s", "base_shear_kN", "peak_displacement_m"]`
   - C02: same
2. In `oracle_verifier.py::evaluate` (return block): `expected_metrics = set(active_metrics) | set(cfg.get("required_metrics", []))` and expose as `OracleResult.expected_metrics`.
3. In `run_benchmarks.py`, compute `claim_completeness_pct = |claims_made ∩ expected_metrics| / |expected_metrics| * 100`.

### P2-4. Add T₁ comparison to CAE roundtrip fidelity

Current fidelity check compares nodes, elements, volume, BCs — but not modal behavior. Add:
```python
run_analysis(runner.project, analysis_case_id="RT_orig", analysis_type="modal", num_modes=1)
run_analysis(p_check,        analysis_case_id="RT_reimp", analysis_type="modal", num_modes=1)
t1_orig  = runner.project.analysis_results["RT_orig"].modal_result.modes[0].period
t1_reimp = p_check.analysis_results["RT_reimp"].modal_result.modes[0].period
t1_err   = abs(t1_orig - t1_reimp) / max(t1_orig, 1e-4)
fidelity_passed = ... and t1_err < 0.01
```
Store `t1_original`, `t1_reimported`, `t1_rel_error` in the `roundtrip_fidelity` dict.

### P2-5. Re-add the As,min note to `experiment_plan.md` §3.2

The paragraph explaining why A06/A07/B06/C06 share DCR = 0.880 (governed by ACI 318 §9.6.1.2 minimum flexural steel) was removed. Restore it under a small "Design-case diversity" callout, or the duplicated values look like padding.

---

## P3 — Cleanup

- **P3-1.** `run_heuristic_baseline`: `prompt_to_schema_fidelity_passed = True` → `None`; and for CAE set `success = None`.
- **P3-2.** `run_benchmarks.py::main` argparse default `--model` → frontier model actually used (matching README §4).
- **P3-3.** In `summary`, add `avg_material_economy_ratio_per_case` and `avg_convergence_iterations_per_case` (mean of per-case seed-averaged values, alongside the existing pooled-run mean).
- **P3-4.** `paper_idea.md` §3 architecture diagram still has `Gemini 3.8 Flash | Qwen3.5:9B | Gemma4:31B | Nemotron-Ultra` — refresh alongside §0 above.

---

## Definition of Done

Before re-running the campaign, all of the following must hold:

1. `grep -rn "gemini-3.8\|qwen3.5\|gemma4\|nemotron-3" research_paper/` → **zero matches**
2. `grep -rn "10.519" research_paper/` → **zero matches** (or matches only the historical log files under `results/`, never in `.md` or `.json` cases)
3. `python research_paper/benchmarks/analyze_results.py --help` runs clean
4. Given a synthetic results JSON with 5 seeds × 24 cases, `analyze_results.py`:
   - produces `summary_table_*.md` with **both** CHR and Claim Completeness columns
   - produces `fig_chr_vs_completeness_*.png`
   - produces `statistical_significance_report_*.md` with `N Pairs = 24` (or `16` for CCR)
   - produces `fig_dcr_convergence_*.png` with mean ± shaded std bands (3 curves for 3 reflection cases), not 15 raw traces
   - produces `failure_mode_taxonomy_table_*.md` summing to ≤ 24 per column
5. `python research_paper/benchmarks/generate_human_baselines.py` (dry run) passes all asserts and prints the new A08 DCR₀
6. `experiment_plan.md` §2 A08 line, `benchmark_cases.json` A08, and `HUMAN_BASELINES_CATALOG["A08"]` are mutually consistent
7. `experiment_plan.md` §3.2 contains the restored As,min note
8. `README.md` §4 commands, `experiment_plan.md` §5 commands, and `run_benchmarks.py` docstring commands all reference the same model strings

Once these hold, run the full campaign with `--seeds 5` on `full_agent` and `ablated` for the frontier model, and `--seeds 1` on `heuristic` / `direct_llm` / `code_gen`. Regenerate all figures. Section 5 is ready to write.
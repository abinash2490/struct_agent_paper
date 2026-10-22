# Actionable Fix List for Coding Agent

## P0 — Blocking (fix before any submission)

### 1. `oracle_verifier.py` — remove hardcoded `baseline_vol` values
- **Problem**: `ORACLE_CASES_CATALOG` hardcodes `baseline_vol` values that are numerically wrong (e.g., A03 `5.760` vs correct `5.772`; B03 `89.910` vs correct `143.100`; A05 `9.720` vs correct `10.440`; B01 `24.300` vs correct `31.680`; C05 `43.740` vs correct `98.820`).
- **Fix**: Delete every `"baseline_vol": <number>` entry from `ORACLE_CASES_CATALOG`. Load volumes exclusively via `get_canonical_baseline_volumes()` (already imported). For non-design cases, leave `baseline_vol = None`. Update downstream reads of `cfg.get("baseline_vol", 1.0)` to handle `None` cleanly (skip `η_vol` when `None`).

### 2. `run_benchmarks.py::run_single_case` — unify CHR computation with `direct_llm`
- **Problem**: `full_agent` CHR is computed via ad-hoc `final_message` parsing (only checks `governing_dcr` and `total_weight_kN`, ignores missing claims). `direct_llm`/`code_gen` use `OracleVerifier.evaluate(...)` with a proper active-metric denominator. This makes the H1 claim (CHR = 0% for agent) a tautology.
- **Fix**: In `run_single_case`, after the run completes:
  1. Extract agent sections from `runner.project` (col_b, col_h, beam_b, beam_h).
  2. Build `parsed_claims = {"claimed_total_weight_kN": ..., "claimed_base_shear_kN": ..., "claimed_fundamental_period_s": ..., "claimed_governing_dcr": ..., ...}` from `parse_numerical_claims_from_text(final_message)`.
  3. Call `OracleVerifier.evaluate(case_id, col_b, col_h, beam_b, beam_h, claims=parsed_claims)`.
  4. Set `active_claims = oracle_res.active_metrics`, `hallucinated_claims = oracle_res.hallucinated_metrics`, `claim_errors = oracle_res.metric_errors`, `measured_chr_pct = oracle_res.calculation_hallucination_rate_pct`.
- **Note**: If you want to keep the "agent reports tool outputs, not computed values" narrative, then add a requirement that the agent emit a structured JSON summary at end of run and pass *those* claims to the verifier. Either way, denominator must be `active_metrics`, not "claims the agent chose to make."

### 3. `run_benchmarks.py::run_single_case` — rename `claim_errors` → `oracle_metric_errors`
- **Problem**: `analyze_results.py::generate_plots` (Figure 5) reads `case.get("oracle_metric_errors", {})`, but `run_single_case` writes `claim_errors`. Figure 5 silently omits agents.
- **Fix**: Rename the key in `run_single_case` output dict from `"claim_errors"` to `"oracle_metric_errors"`. Update `analyze_results.py` accordingly if any other key name is used.

### 4. `run_benchmarks.py::run_single_case` — verify file artifacts for DXF and CAE export cases
- **Problem**: A01, A08, C08 (DXF), C03, C04 (SAP2000/ETABS export) pass TCR if `generate_drawings` / `export_to_*` returns `ok=True`, without checking the file exists. A tool can succeed without writing.
- **Fix**: After the run, for each case with `target_constraints.drawings_generated == true`:
  - Assert the DXF path exists and `os.path.getsize(path) > 500`.
  - Optionally, try loading with `ezdxf.readfile` and confirm ≥1 entity.
  - For C03/C04, assert the exported `.s2k`/`.e2k` exists and re-imports via `import_from_sap2000`/`import_from_etabs` with matching node/element counts.
- **Action**: If any check fails, set `task_completed = False` and append the reason to `error_messages`.

### 5. `benchmark_cases.json` — re-verify A06, A07, B06 baselines
- **Problem**: All three have `DCR = 0.88`, despite different geometry and load cases. Suspicious.
- **Action**: Run `generate_human_baselines.py --write` on these three cases and log the governing element ID and limit state (e.g., `"Column P-M Interaction (ACI 318 §10.5)"` or `"Beam Flexure / As,min (ACI 318 §9.6.1)"`). Add the governing limit state to `baseline_design` in `benchmark_cases.json` for every design case (new key `governing_limit_state`). If they are all `As,min`-governed, document in `experiment_plan.md`; if not, fix the baseline generator.

---

## P1 — High priority (reviewers will ask)

### 6. `experiment_plan.md`, `README.md`, `run_benchmarks.py` docstrings — replace fictitious model names
- **Problem**: `gemini-3.8-flash`, `qwen3.5:9b`, `gemma4:31b-cloud`, `nemotron-3-ultra:cloud` are not real model identifiers.
- **Fix**: Substitute real versioned IDs (e.g., `gemini-2.5-flash`, `qwen2.5:9b`, `gemma3:27b`, `nemotron-4-15b`). If aliased for double-blind review, add a footnote in the paper AND a note in `experiment_plan.md §4.2`. Update every occurrence in docstrings and README.

### 7. `run_benchmarks.py::run_direct_llm_baseline` and `run_code_gen_baseline` — fix TCR semantics
- **Problem**: Both hardcode `"success": False`, so TCR for these baselines is trivially 0%.
- **Fix**: Either (a) redefine `success = bool(oracle_res.code_compliant)` for design cases and `= bool(oracle_res.valid_sections)` for non-design, or (b) in the paper explicitly state TCR applies only to agent configurations; rename the direct_llm/code_gen metric to "Physically Valid Output Rate" and report separately in `analyze_results.py`.

### 8. `benchmark_utils.py::parse_numerical_claims_from_text` — fix regex robustness
- **Problem**: Regexes require decimal point (misses "DCR = 1"), lack `\b` word boundaries ("lightweight" matches "weight"), and don't handle Unicode subscripts (T₁).
- **Fix**:
  ```python
  import unicodedata
  text = unicodedata.normalize("NFKD", text)
  dcr_match = re.search(r"\bdcr\b[^\d-]{0,12}(-?\d+(?:\.\d+)?)", text, re.I)
  weight_match = re.search(r"\b(?:total\s+)?weight\b[^\d-]{0,12}(-?\d+(?:\.\d+)?)", text, re.I)
  vb_match = re.search(r"\b(?:base\s+shear|v[_\s]?b)\b[^\d-]{0,12}(-?\d+(?:\.\d+)?)", text, re.I)
  t1_match = re.search(r"\b(?:fundamental\s+period|period|t[_\s]?1)\b[^\d-]{0,12}(-?\d+(?:\.\d+)?)", text, re.I)
  ```
  Apply same pattern to T2, T3, mass participation, displacement.

### 9. `oracle_verifier.py` — use `strict=True` for concrete volume
- **Problem**: `calculate_concrete_volume(proj)` in `OracleVerifier.evaluate` uses default `strict=False`, silently under-counting volume for zero-area sections and inflating η_vol for undersized designs.
- **Fix**: Change to `calculate_concrete_volume(proj, strict=True)`. On `ValueError`, return `OracleResult(valid_sections=False, error_message=str(exc), ...)`.

### 10. `verify_cae_parity.py` — document source of hardcoded CSI references
- **Problem**: Reference values (e.g., `140.000 kN`, `0.0931 s`) are presented as "CSI SAP2000" outputs with no citation.
- **Fix**: Add a module-level docstring listing CSI SAP2000 version (e.g., v24.0.0), ETABS version (v21.0.0), build numbers, and the exact output table used (e.g., "Joint Reactions table, load case DEAD"). Add a `source` field to each row in `calculate_parity_metrics`. If possible, also write the SAP2000 `.out` log next to the `.s2k` fixture.

### 11. `benchmark_cases.json` — standardize decimal precision
- **Problem**: Mixed precision (`143.1`, `82.508`, `3.82`, `5.772`).
- **Fix**: Round every `baseline_concrete_volume_m3` to 3 decimals. Round every `baseline_design.governing_dcr` to 3 decimals. Round every `bay_width`, `story_height`, `sds`, `sd1` to 3 decimals.

### 12. `README.md` — fix fixture references
- **Problem**: `fixtures/hostel_block_plan_2 story.PNG` (a) has a space in the filename, (b) is not referenced by any case.
- **Fix**: Rename to `hostel_block_plan_2story.PNG`. Either wire it into B01 as a vision case (add `"image_path"` and change `expected_tools` to include `create_model_from_plan_draft`) or delete from README and disk.

### 13. `README.md` — clarify conditional figures
- **Problem**: README lists `fig_dcr_convergence_<timestamp>.png` as always generated; `generate_plots` only writes it if `has_curves` is True.
- **Fix**: Add "(only when ≥1 run has a multi-iteration DCR history)" after each conditional figure line.

---

## P2 — Medium priority

### 14. `run_benchmarks.py::run_single_case` — ablated config is a soft ablation
- **Problem**: The ablated run only removes `modify_project`; the agent can bypass by re-calling `create_frame_model` with larger sections.
- **Fix**: In `run_single_case`, for `config == "ablated"`, detect if `create_frame_model` (or `create_model_from_plan_draft`) is called more than once. If so, set `task_completed = False` and log `ablation_violation` in `error_messages`. Document this in `experiment_plan.md §4.1`.

### 15. `run_benchmarks.py::run_single_case` — record governing limit state and DCR components
- **Problem**: The result JSON only contains `final_dcr`, not `governing_member_id`, `governing_limit_state`, or `(P_u, M_u, V_u)`.
- **Fix**: After `run_design`, extract from `proj.design_results["oracle_independent_eval"]` the governing element's `member_type`, `limit_state`, and `flexure.dcr`/`shear.dcr`. Add to output: `governing_member_id`, `governing_limit_state`, `dcr_flexure`, `dcr_shear`, `dcr_pm`. Emit these for both agent and human baselines so `analyze_results.py` can build a per-case comparison table.

### 16. `generate_human_baselines.py` — print governing limit state
- **Problem**: Only DCR is printed per case; the governing element and limit state are hidden.
- **Fix**: Extend the print loop:
  ```python
  gov = res_design.data.get("governing_member_id")
  ls  = res_design.data.get("governing_limit_state")
  print(f"{cid:44s} | DCR={dcr:.3f} | {gov} | {ls} | {vol:.3f} m3 | {status}")
  ```
  Add `governing_member_id` and `governing_limit_state` to the written JSON under `baseline_design`.

### 17. `run_benchmarks.py` — add `--seeds` and report mean ± std
- **Problem**: Single-run LLM evaluation is not reproducible.
- **Fix**: Add `--seeds N` (default 1). Loop `run_single_case` N times per case; aggregate with mean and std for TCR, CCR, CHR, η, N_iter. Store both `case_results` (all seeds) and `case_results_mean_std` (aggregated) in the JSON. Update `analyze_results.py` to prefer aggregated keys when present.

### 18. `run_benchmarks.py::main` — equalise turn budget between configs
- **Problem**: `full_agent` gets `--max-turns 20`; `direct_llm` gets 1 call. The comparison confounds grounding with iteration budget.
- **Fix**: Add `direct_llm` a chain-of-thought self-correction loop: after the first JSON output, feed back `{"col_b_m": ..., "claimed_governing_dcr": ...}` to the LLM with "verify your numbers, revise if needed", for `max_turns` iterations. This makes the direct_llm baseline a *fair* iteration-matched comparison. Alternatively, document the confound explicitly in `experiment_plan.md §4`.

### 19. `analyze_results.py` — add per-case comparison table (agent vs human baseline)
- **Problem**: No table in the paper shows per-case DCR, governing limit state, and η_vol for the agent vs the verified human baseline.
- **Fix**: Add `print_and_save_detailed_table(summaries, results_dir)` that emits a Markdown table with columns: `case_id | group | baseline_DCR | agent_DCR | baseline_limit_state | agent_limit_state | baseline_V | agent_V | η_vol | compliant`. Wire into `main()`.

### 20. `analyze_results.py` — add CCR margin metric
- **Problem**: B03 (0.983), B07 (0.970), B08 (0.940) sit near 1.0. An agent at DCR = 1.001 is physically within rounding but fails CCR.
- **Fix**: In the summary JSON, report both `code_compliance_rate_pct` (strict, ≤ 1.0) and `code_compliance_rate_margin_pct` (≤ 1.02). Add both columns to the Markdown table.

---

## P3 — Cosmetic / cleanup

### 21. `analyze_results.py::generate_plots` — drop `_latest.json` fallback
`run_benchmarks.py` never writes `_latest.json`. Delete lines 55–67 in `load_all_results` or mark as legacy with a comment.

### 22. `analyze_results.py::generate_plots` — stabilize matplotlib style
Replace `plt.style.use("seaborn-v0_8-whitegrid" if ... else "default")` with `plt.style.use("default")`. `seaborn-v0_8-*` names vary across matplotlib versions.

### 23. `analyze_results.py::generate_plots` — trim model labels
`models = [f"{s['model']}\n({s.get('configuration', 'full')})" ...]` produces `"gemini (full)"`. Use the full config string (`full_agent`, `ablated`, `direct_llm`, `code_gen`) since `(full)` is ambiguous.

### 24. `benchmark_utils.py::calculate_concrete_volume` — add schema fallback
Support both `elem.start_node`/`elem.end_node` and `elem.node_i`/`elem.node_j`, and `sec.A` vs `sec.area`. Add a unit test that imports a `.s2k` fixture and verifies volume > 0.

### 25. `verify_cae_parity.py` — remove hardcoded source paths
Replace `repo_root / "struct_link" / "tests" / "fixtures" / "sample_frame.s2k"` with paths resolved relative to `benchmarks_dir / "fixtures"`. Copy the fixtures into `benchmarks/fixtures/` if they don't already exist there.

### 26. `benchmark_cases.json` — add `governing_limit_state` per design case
Add `"baseline_design.governing_limit_state"` for all 16 design cases (values from §5). Enables reviewers to audit the baseline.

### 27. `experiment_plan.md §3.3` — clarify CHR denominator
Currently: "CHR = N_hallucinated / N_total_numerical_claims". Add: "N_total is defined as the number of *active oracle metrics* for the case (weight, base shear if lateral, period if dynamic, DCR if design), regardless of whether the configuration reported them. Missing claims count as hallucinations."

### 28. `README.md` — add "Limitations" section
Add a short note that the 24 cases are all RC moment frames, that the benchmark does not include steel/shear-wall/PT typologies, and that CAE round-trip is tested on 2 fixtures only. Reviewers prefer explicit scope statements over buried caveats.

---

## Verification checklist before re-submission

After the coding agent finishes, run this sequence and confirm all pass:

1. `python generate_human_baselines.py` (dry run) — all 16 baselines report `VERIFIED [OK]` with governing limit state printed. A06, A07, B06 DCR values are either identical *and* the limit state is documented, or updated.
2. `python generate_human_baselines.py --write` — `benchmark_cases.json` updated with corrected volumes and `governing_limit_state` for all 16 design cases. Volumes in the JSON now match `experiment_plan.md` exactly.
3. `python run_benchmarks.py --model <real-id> --config direct_llm --cases A06_2D_Response_Spectrum_ASCE7` — output JSON contains `oracle_metric_errors` with base shear and period checked.
4. `python run_benchmarks.py --model <real-id> --config full_agent --cases A01_Portal_Frame_Office` — output JSON contains `oracle_metric_errors` with the *same* active metric set as step 3, and `drawings_generated` is verified on disk.
5. `python analyze_results.py` — Figure 5 shows bars for all four configurations (not just direct_llm/code_gen). Markdown table contains the new `baseline_DCR / agent_DCR / η_vol` columns.
6. `python verify_cae_parity.py` — maximum discrepancy < 0.5%, and the output includes version strings for SAP2000 and ETABS.
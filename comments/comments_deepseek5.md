## P0 — Methodological, must fix before the campaign

### 1. `--seeds N` does not actually vary anything

**Files:** `run_benchmarks.py`, `commands_to_run.md`, `experiment_plan.md` §5

`AgentRunner` is constructed with `temperature=0.0` and no `seed` parameter, and `main()` loops `for s_idx in range(seeds_count)` without passing any seed downstream. With `temperature=0.0` and no seed, most providers (Gemini, Ollama) will return **byte-identical outputs across the 5 runs**, giving `std ≈ 0` and `Wilcoxon p ≈ 1.0` or `NaN`. The entire multi-seed statistical apparatus produces no signal.

`experiment_plan.md` §5 even claims *"repeating across random seeds 42, 43, 44, 45, 46"*, but the code never sets 42–46 anywhere.

**Fix one of:**
- **(Preferred)** Add a `--temperature` CLI flag (default `0.0` for reproducibility checks, `0.1`–`0.3` for multi-seed). Then `--seeds 5 --temperature 0.2` gives genuinely different runs. Update `experiment_plan.md` §5 to include `--temperature 0.2` on the multi-seed commands.
- **(Alternative)** Add a `seed` parameter to `AgentRunner.__init__` that gets forwarded to the provider API (Gemini supports `seed`, Ollama inherits whatever the model supports). Pass `seed=s_idx + 42` from `main()`.
- **(Last resort)** Rename the flags and doc: `--repeats 5` instead of `--seeds 5`, and state in `experiment_plan.md` §5 that repeats are a *determinism consistency check*, not a statistical bootstrap. Then drop the Wilcoxon report for `full_agent vs ablated` (or replace it with a sign test on which of the 24 cases differ, not a paired test on 5 identical repeats).

Without this, the paper's "statistical significance" section is unsupportable.

### 2. Baseline prompts do not ask for T2/T3/MMR/peak-disp, making CCR_claims unfair

**Files:** `run_benchmarks.py::run_direct_llm_baseline`, `run_benchmarks.py::run_code_gen_baseline` — both `system_msg` definitions

Both baseline prompts request only `claimed_total_weight_kN`, `claimed_base_shear_kN`, `claimed_fundamental_period_s`, `claimed_governing_dcr`. But the agent's case prompts (A05, B04, C01, C02) explicitly ask for T1, T2, T3, modal mass participation, and peak roof displacement. The agent gets these via `required_metrics` in `ORACLE_CASES_CATALOG`; the baselines get nothing because their system prompt never asked.

Result: `claim_completeness_pct` for `direct_llm` and `code_gen` on A05 will max out at ~40% (weight + T1 out of 5 expected), not because the models are bad but because they were never asked. This asymmetry undermines the paper's claim that "CCR_claims exposes gaming via omission" — it exposes a prompt-design asymmetry between the agent and the baselines.

**Fix:** extend both `system_msg` JSON schemas:
```python
'  "claimed_period_t2_s": <float, second mode period T2 in seconds (0.0 if not modal)>,\n'
'  "claimed_period_t3_s": <float, third mode period T3 in seconds (0.0 if not modal)>,\n'
'  "claimed_modal_mass_ratio": <float, modal mass participation ratio (0.0 if not modal)>,\n'
'  "claimed_peak_displacement_m": <float, peak roof lateral displacement in meters (0.0 if not time-history)>\n'
```
This is the only way the baseline CHR/CCR_claims comparison is defensible.

---

## P1 — Documentation and correctness

### 3. `experiment_plan.md` §3.3 formula says `active_metrics`, code uses `expected_metrics`

Current formula in §3.3:
$$\text{CCR}_{\text{claims}} = \frac{N_{\text{claims\_made}}}{N_{\text{active\_metrics}}} \times 100\%$$

The code (`oracle_verifier.py` + all three baselines + `run_single_case`) uses `expected_metrics = active_metrics ∪ required_metrics`. Update:

$$\text{CCR}_{\text{claims}} = \frac{|\,N_{\text{claims\_made}} \cap N_{\text{expected\_metrics}}\,|}{N_{\text{expected\_metrics}}} \times 100\%$$

where $N_{\text{expected\_metrics}} = N_{\text{active\_metrics}} \cup N_{\text{required\_metrics}}$, and `required_metrics` is populated for A05, B04, C01, C02 (T2, T3, MMR, peak disp) plus any future case where the prompt names specific quantities.

Also update the paragraph below the formula — it currently says "total dead weight W, lateral base shear Vb, fundamental period T1, and governing DCR" without mentioning the per-case `required_metrics`. Add one sentence.

### 4. Add `required_metrics` to C03 and C04

**File:** `oracle_verifier.py::ORACLE_CASES_CATALOG`, entries `C03_CAE_SAP2000_RoundTrip` and `C04_CAE_ETABS_RoundTrip`

The C03/C04 prompts explicitly ask for total weight, base shear, T1, T2, T3. But their catalog entries have no `required_metrics`, so `expected_metrics` only contains `[total_weight_kN, base_shear_kN, fundamental_period_s]`. An agent that reports only W + Vb + T1 gets 100% CCR_claims, even though it ignored the T2/T3 requirement in the prompt.

**Fix:** add to both:
```python
"required_metrics": ["fundamental_period_s", "period_t2_s", "period_t3_s", "base_shear_kN"],
```

### 5. `benchmarks/README.md` has a broken nested code fence

Top of the file:
```markdown
```
```
research_paper/benchmarks/
├── ...
```
```
There are two consecutive ` ``` ` opens (the outer fence and a second one at the top of the tree content). The Markdown renderer will show the tree as plain prose, not as a code block. Users reading the benchmarks README on GitHub will see a broken layout.

**Fix:** remove one of the leading ` ``` ` lines. The correct structure is:
```markdown
```
research_paper/benchmarks/
├── ...
```
```

### 6. `commands_to_run.md` single-case example points to a file that does not exist

At the bottom:
```powershell
--update-file results/results_gemini-3.8-flash_full_agent_latest.json
```
The harness only writes `results_<model>_<config>_<timestamp>.json`. `analyze_results.py` explicitly **skips** `_latest.json` files:
```python
if f.name.endswith("_latest.json"):
    continue
```
So a user following this command will get `Error: Update file does not exist`.

**Fix:** change to a placeholder the user must substitute, and add a note:
```powershell
# First list existing results and pick the timestamped file to update:
ls research_paper/benchmarks/results/

# Then update it with the re-run case:
python "research_paper/benchmarks/run_benchmarks.py" --model "..." --config "..." --cases "C03" `
  --update-file "research_paper/benchmarks/results/results_<model>_<config>_<timestamp>.json"
```

---

## P2 — Aggregation and reporting

### 7. `avg_claim_completeness` and per-config aggregate include heuristic — drags down the pooled value

**File:** `run_benchmarks.py::main`, the block computing `total_expected_metrics` and `total_matched_claims`

The heuristic baseline emits no text, so `claims_made=[]`. It contributes 0 to `total_matched_claims` but full count to `total_expected_metrics`. A `--config heuristic` run therefore reports pooled `claim_completeness_rate_pct = 0.0%` — technically "correct" but confusing next to the summary table, which now displays `N/A` for heuristic. Same problem in `analyze_results.py::load_all_results`, where `cc_vals` includes heuristic's `0.0` values.

**Fix in `run_benchmarks.py::main`:**
```python
non_heuristic = [r for r in results if r.get("configuration") != "heuristic"]
total_expected_metrics = sum(len(r.get("expected_oracle_metrics", ...)) for r in non_heuristic)
total_matched_claims = sum(
    len(set(r.get("claims_made", [])) & set(r.get("expected_oracle_metrics", ...)))
    for r in non_heuristic
    if not (r.get("configuration") == "code_gen" and not r.get("success") and r.get("claim_completeness_pct", 0.0) == 0.0)
)
avg_claim_completeness = (
    round((total_matched_claims / max(total_expected_metrics, 1)) * 100.0, 1)
    if total_expected_metrics > 0 else None
)
```

**Fix in `analyze_results.py::load_all_results`:**
```python
if "claim_completeness_rate_pct" not in r or r["claim_completeness_rate_pct"] is None:
    if r.get("configuration") == "heuristic":
        r["claim_completeness_rate_pct"] = None
    else:
        cc_vals = [c["claim_completeness_pct"] for c in cases_list if c.get("claim_completeness_pct") is not None]
        r["claim_completeness_rate_pct"] = round(sum(cc_vals) / len(cc_vals), 1) if cc_vals else None
```

### 8. `generate_human_baselines.py` usage docstring is missing `--write`

**File:** `generate_human_baselines.py`, module docstring

Currently:
```
Usage:
    python "research_paper/benchmarks/generate_human_baselines.py"
```
The script defaults to dry-run (no JSON write). Users running this without `--write` and expecting `benchmark_cases.json` to be updated will be surprised.

**Fix:**
```
Usage:
    python "research_paper/benchmarks/generate_human_baselines.py"           # dry run, verify only
    python "research_paper/benchmarks/generate_human_baselines.py" --write   # update benchmark_cases.json
    python "research_paper/benchmarks/generate_human_baselines.py" --write --output PATH
```

### 9. `generate_human_baselines.py` crashes on first baseline failure

Inside the per-case loop:
```python
assert is_pass, f"Baseline for {cid} failed compliance check: DCR={dcr}"
```
If the first case fails, the whole script aborts and the user cannot see the other 15 baselines. For a verification harness, this is the wrong failure mode.

**Fix:** collect failures and continue, then raise/print at the end:
```python
failures = []
...
if not is_pass:
    failures.append({"case_id": cid, "dcr": dcr, "limit_state": gov_limit_state})
    continue  # don't write to verified_baselines

...
if failures:
    print("=" * 95)
    print(f"FAILED BASELINES ({len(failures)}):")
    for f in failures:
        print(f"  {f['case_id']}: DCR={f['dcr']}, state={f['limit_state']}")
    if write_json:
        raise RuntimeError(f"{len(failures)} baselines failed; refusing to overwrite {cases_json_path.name}.")
```

This gives users the full diagnostic list and blocks the `--write` from silently persisting bad baselines.

---

## P3 — Polish

### 10. `paper_idea.md` H1 should pair `CHR = 0.0%` with high `CCR_claims`

**File:** `paper_idea.md` §2, hypothesis H1

Current: *"the proposed neuro-symbolic architecture guarantees CHR = 0.0% across all completed workflows"*

With the new CHR = precision-over-claims definition, a model could trivially hit CHR=0 by making zero claims. The headline must be the pair. Change to:

> *"...guarantees CHR = 0.0% **with CCR_claims = 100%** (all prompt-required quantities reported) across all completed workflows..."*

Same update in §5.2 bullet.

### 11. Verify A08 `initial DCR_0 = 3.952`

**File:** `experiment_plan.md` §2, A08 entry

The prompt and `benchmark_cases.json` now both say A08 initializes at `0.30×0.30 / 0.30×0.45`. The stated `DCR_0 = 3.952` was not re-derived in any file I can see. Confirm by running:

```python
from research_paper.benchmarks.oracle_verifier import OracleVerifier
r = OracleVerifier().evaluate(
    "A08_2D_Overstressed_Portal_Reflection",
    col_b=0.30, col_h=0.30, beam_b=0.30, beam_h=0.45,
)
print(r.governing_dcr, r.governing_limit_state, r.error_message)
```

If it prints a value different from 3.952, update `experiment_plan.md` §2. If it prints `None` with an error message, investigate before the campaign — A08's whole premise (self-healing from a large DCR) depends on this.

### 12. `benchmarks/README.md` lists a fixture no case uses

The directory tree lists `hostel_block_plan_2story.PNG` in `fixtures/`, but no benchmark case (`A01`–`C08`) references it. Either delete the fixture or add a note that it is reserved for a future case. A reviewer scanning the fixtures vs. cases will spot the mismatch.

### 13. `verify_cae_parity.py` still hardcodes CSI reference values

Not a Paper 1 blocker — this is supplementary parity evidence. But for the JOSS/SoftwareX submission (Paper 2), the reviewer will want to trace the hardcoded `140.000`, `12.928`, `12.826`, `0.0931`, etc. back to actual CSI output reports. Add a `benchmarks/fixtures/csi_reference/` directory containing:
- Exported `Joint Reactions` table (DEAD / LIVE) from SAP2000 for `sample_frame.s2k` and `frame.s2k`
- Exported `Modal Frequencies` table
- Exported `Joint Displacements` table

Ship as CSV or screenshots — the point is reproducibility.

---

## What to leave alone (verified correct)

I traced all of these against the source and they are right as-is:

- **`oracle_verifier.py`** — `expected_metrics`, `claims_made`, `omitted_metrics`, `CHR = |wrong ∩ claims_made| / |claims_made|` all correct. `required_metrics` for A05/B04/C01/C02 correctly increases the CCR_claims denominator without inflating CHR.
- **`run_benchmarks.py::run_direct_llm_baseline`, `run_code_gen_baseline`, `run_heuristic_baseline`** — all three use `expected_metrics` for `claim_completeness_pct`. Failed code-gen runs correctly set `claims_made = list(expected_metrics)` and `hallucinated = num_claims`, keeping CHR = 100% for those runs. Heuristic correctly sets `prompt_to_schema_fidelity_passed = None`, `success = None` for CAE, and respects prompt-specified sections for non-design cases.
- **`analyze_results.py`** — `_compute_run_level_seed_stats` correct; convergence plot mean ± shaded band correct; failure-mode table case-grouped correct; Wilcoxon uses per-case seed-averaged means correct; heuristic CHR/CCR_claims override in the summary table correct.
- **`benchmark_utils.py::evaluate_prompt_to_schema_fidelity`** — CAE early-return now checks nodes/supports/materials; `and` used for seismic parameter matching; no over-permissive path remains.
- **`benchmark_cases.json`** — B08 renamed, A08 sections aligned with prompt and `HUMAN_BASELINES_CATALOG`, all 16 design baselines intact.
- **`paper_idea.md` §4.2** — "5 configurations" fixed.

Fix P0-1 and P0-2 before the campaign. P1 items are documentation but will be caught by any careful reader of the repository (especially §3.3 and the README tree). P2/P3 are polish but cheap to do in one pass.
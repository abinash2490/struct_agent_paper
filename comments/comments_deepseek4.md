# Coding Agent Task Brief — Benchmark Suite Final Fixes

Below are the remaining issues. Everything else in the updated files is correct and should not be touched.

---

## 1. `claim_completeness_pct` uses the wrong denominator in all three baselines

**Files:** `run_benchmarks.py` — `run_direct_llm_baseline`, `run_code_gen_baseline`, `run_heuristic_baseline`

**Current (wrong):**
```python
"claim_completeness_pct": round(
    (len(oracle_res.claims_made) / max(len(oracle_res.active_metrics), 1)) * 100.0, 1
),
```

**Why it's wrong:** `active_metrics` only reflects metrics the oracle computes an error for. `expected_metrics` is `active_metrics ∪ required_metrics` (from the catalog). For A05, `expected_metrics` has 5 items (weight, T1, T2, T3, MMR) but `active_metrics` has 2. A direct-LLM response that reports weight + T1 scores `2/2 = 100%` instead of the correct `2/5 = 40%`.

**Fix in all three baselines:**
```python
expected_metrics = oracle_res.expected_metrics or oracle_res.active_metrics
"expected_oracle_metrics": expected_metrics,
"claim_completeness_pct": round(
    len(set(oracle_res.claims_made) & set(expected_metrics))
    / max(len(expected_metrics), 1) * 100.0,
    1,
),
```

The `run_single_case` (agent config) already does this correctly — do not modify it.

---

## 2. `code_gen` failed-run CHR aggregation is internally inconsistent

**File:** `run_benchmarks.py::run_code_gen_baseline`, the `if not code_execution_ok:` branch

**Current:**
```python
chr_pct = 100.0
hallucinated_claims = num_claims        # > 0
```
But the returned dict has `claims_made = []` → `claims_made_count = 0`.

**Effect:** In `run_benchmarks.py::main`, the aggregate is `sum(hallucinated) / sum(claims_made)`. Mixed runs (some success, some failure) produce an aggregate CHR > 100%, because failed runs contribute hallucinations to the numerator with zero claims in the denominator.

**Fix — pick the second option (defensible convention):** a script that fails to execute is a wrong answer, not an omission, so treat it as an attempted-but-incorrect claim:
```python
if not code_execution_ok:
    chr_pct = 100.0
    code_compliant = False if requires_design else None
    concrete_vol = 0.0
    econ_ratio = None
    gov_dcr = None
    num_claims = max(len(oracle_res.expected_metrics or oracle_res.active_metrics), 1)
    hallucinated_claims = num_claims
    claims_made_list = list(oracle_res.expected_metrics or oracle_res.active_metrics)
else:
    chr_pct = oracle_res.calculation_hallucination_rate_pct
    ...
    claims_made_list = oracle_res.claims_made
```
Then in the return dict use `"claims_made": claims_made_list` and `"claims_made_count": len(claims_made_list)` instead of `oracle_res.claims_made`. Keep `hallucinated_claims_count = hallucinated_claims`.

After this change, verify: for a run that fails on 3 cases and succeeds on 21, the pooled CHR stays in `[0, 100]`.

---

## 3. `run_heuristic_baseline` missing `expected_oracle_metrics`

**File:** `run_benchmarks.py::run_heuristic_baseline`, return dict

Add the field alongside `active_oracle_metrics`:
```python
"expected_oracle_metrics": oracle_res.expected_metrics or oracle_res.active_metrics,
```
Without it, `analyze_results.py::load_all_results` falls back to `active_oracle_metrics` when computing CCR_claims for the heuristic row.

---

## 4. `oracle_verifier.py` module docstring is stale

**File:** `oracle_verifier.py`, lines describing metric 4

**Current text (outdated):**
> "...T_2, T_3, modal mass ratio, and peak roof displacement are optional-if-claimed and scored only when explicitly asserted"

**Fix:**
> "T_1 is mandatory for dynamic/modal regimes; higher modes (T_2, T_3), modal mass ratio, and peak roof displacement are **mandatory** for A05, B04, C01, C02 (per their `required_metrics`) and optional-if-claimed for other cases."

No code change — docstring only.

---

## 5. `paper_idea.md` §4.2 says "4 configurations" — now 5

**File:** `paper_idea.md` §4.2 defense matrix, first row

**Current:** *"execute a rigorous 24-case empirical benchmark across 4 configurations and 4 LLM backbones"*

**Fix:** change "4 configurations" → "5 configurations" (`heuristic`, `direct_llm`, `code_gen`, `ablated`, `full_agent`). Leave "4 LLM backbones" alone.

---

## 6. Print statements in two baselines use mismatched denominators

**Files:** `run_benchmarks.py::run_direct_llm_baseline` and `run_code_gen_baseline`

**Current:**
```python
num_claims = max(len(oracle_res.active_metrics), 1)
print(f"... Hallucinations: {hallucinated_claims}/{num_claims} (CHR: {chr_pct}%) ...")
```
`chr_pct` uses `claims_made` as denominator, but the printed `X/Y` uses `active_metrics`. For A05 this prints e.g. "0/2 (CHR: 0%)" while the true denominator is 2 of 5.

**Fix:** change `num_claims = max(len(oracle_res.claims_made), 1)` in both print lines. Cosmetic only.

---

## 7. Heuristic contributes 0/0 to the aggregate CHR / CCR_claims

**File:** `analyze_results.py::print_and_save_markdown_table` (or wherever the summary table is built)

The heuristic row shows `CHR = 0.0%` and `CCR_claims = 0.0%` because it makes no text claims. Mathematically defensible, but a reviewer will ask why a "perfect" system shows 0% completeness.

**Fix (lightweight):** in the summary table rendering, when `s.get("configuration") == "heuristic"`, print `N/A` for both CHR and Claim Completeness columns, with a trailing footnote line after the table:

```
Note: CHR and CCR_claims are not applicable to the deterministic heuristic
baseline (no textual claims are emitted).
```

Do not change any aggregation logic — just the display.

---

## 8. Verify A08 initial DCR matches the claimed value

**File:** `experiment_plan.md` §2, A08 entry claims `initial DCR_0 = 3.952 > 1.0`

Run:
```python
from research_paper.benchmarks.oracle_verifier import OracleVerifier
r = OracleVerifier().evaluate(
    "A08_2D_Overstressed_Portal_Reflection",
    col_b=0.30, col_h=0.30, beam_b=0.30, beam_h=0.45,
)
print(r.governing_dcr, r.error_message)
```

If the printed value is not `≈3.952`, update `experiment_plan.md` §2 A08 to the actual value. If `r.error_message` is non-null, investigate before proceeding.

---

## Definition of Done

1. `python research_paper/benchmarks/analyze_results.py --help` runs clean
2. Given a mixed-seed results JSON (some successful, some failed `code_gen` runs), the pooled `calculation_hallucination_rate_pct` in `summary` is within `[0.0, 100.0]`
3. Summary table shows `N/A` for `heuristic` CHR and CCR_claims columns; footnote present
4. `print_and_save_markdown_table` for A05 under `direct_llm` shows `CCR_claims < 100%` (2/5 = 40%, not 100%)
5. A08's `initial DCR_0` in `experiment_plan.md` matches the value printed by direct evaluation
6. `grep "optional-if-claimed" oracle_verifier.py` shows the updated wording
7. `grep "4 configurations" paper_idea.md` returns zero hits (it should read "5 configurations")

Once these hold, the benchmark suite is ready for the full 5-seed campaign.
Only the items below remain. Everything else in the current files is correct and should not be touched.

### 1. Confirm `AgentRunner.__init__` accepts `seed`

`run_benchmarks.py::run_single_case` now calls:
```python
runner = AgentRunner(..., temperature=temperature, seed=seed, ...)
```

If `AgentRunner` does not accept `seed`, this raises `TypeError` on the first agent run and aborts the campaign.

**Verify:**
```bash
python -c "from struct_agent import AgentRunner; import inspect; print(inspect.signature(AgentRunner.__init__))"
```

**If `seed` is missing:** either add it to `AgentRunner.__init__` (forward to provider API or store as `self._seed`), or drop the `seed=seed` kwarg — `temperature=0.2` alone is enough to break determinism for the multi-seed protocol. Do not proceed to the campaign until this is resolved.

---

## P1 — Methodological correctness

### 2. C03/C04 cannot exceed 60% CCR_claims — Oracle never extracts T₂ or T₃

**File:** `oracle_verifier.py`, `if is_cae_fixture:` solver branch

Catalog entries for C03/C04 list `required_metrics: ["fundamental_period_s", "period_t2_s", "period_t3_s", "base_shear_kN"]`, but the CAE branch only sets `t1_oracle`. `t2_oracle` and `t3_oracle` remain `None`, so the metric-scoring block never populates `claims_made` for T₂ or T₃, and both land in `omitted_metrics`. Denominator is 5, maximum attainable numerator is 3 → 60% hard ceiling for every C03/C04 run regardless of agent quality.

**Fix — add to the CAE branch (replacing the single-line `t1_oracle` assignment):**
```python
modes = r_modal.modal_result.modes
t1_oracle = round(float(modes[0].period), 3)
if len(modes) > 1:
    t2_oracle = round(float(modes[1].period), 3)
if len(modes) > 2:
    t3_oracle = round(float(modes[2].period), 3)
```

**Alternative:** if the SAP2000/ETABS modal output genuinely yields only one mode, reduce C03/C04 `required_metrics` to `["fundamental_period_s", "base_shear_kN"]` and remove T₂/T₃ from the C03/C04 prompts so the prompt and the metric definition stay consistent.

### 3. Heuristic is still plotted in two CHR figures

**File:** `analyze_results.py::generate_plots`, sections labeled `# 4.` and `# 4b.`

The summary table correctly renders heuristic CHR and Claim Completeness as `N/A`, but both figures still add heuristic as a data point — it renders green as `0.0% (Verified)` in section 4, and as `CHR=0, CCR_claims=0` in section 4b. A reviewer reading the figure will interpret "heuristic achieves zero hallucinations with zero completeness" as a bug.

**Fix in both sections:** add at the top of the per-summary loop:
```python
if s.get("configuration") == "heuristic":
    continue
```

---

## P2 — Documentation consistency

### 4. `experiment_plan.md` §5 says `--temperature 0.2` but commands omit it

Prose states the multi-seed runs are executed *"with `--temperature 0.2`"*, but no `--seeds 5` command block contains the flag. The code relies on the argparse default (`0.2` when `seeds_count > 1`), so it works — but a reader grepping the commands for `--temperature 0.2` will conclude the plan and the commands disagree.

**Fix — pick one:**
- Add `--temperature 0.2` to every `--seeds 5` command in §5, or
- Change the prose to *"via the harness default of 0.2 when `--seeds > 1`"*.

### 5. `oracle_verifier.py` module docstring omits C03/C04 from the mandatory-metrics list

Current docstring:
> "...mandatory for A05, B04, C01, C02 (per their required_metrics) and optional-if-claimed for other cases."

**Fix:** change `A05, B04, C01, C02` → `A05, B04, C01, C02, C03, C04`.

---

## P3 — Polish

### 6. Force `seeds_count = 1` for heuristic

**File:** `run_benchmarks.py::main`

`--config heuristic --seeds 5` runs each case 5× identically (temperature and seed are ignored by `run_heuristic_baseline`). No information gained, 5× the wasted time.

**Fix:**
```python
if args.config == "heuristic":
    seeds_count = 1
elif args.seeds is None:
    seeds_count = 5 if args.config in ("full_agent", "ablated") else 1
else:
    seeds_count = max(args.seeds, 1)
```

### 7. Verify A08 `DCR_0 = 3.952`

**File:** `experiment_plan.md` §2 claims A08 initializes at `DCR_0 = 3.952` with sections `0.30×0.30 / 0.30×0.45`. This value is not asserted anywhere in code. Run:

```python
from research_paper.benchmarks.oracle_verifier import OracleVerifier
r = OracleVerifier().evaluate(
    "A08_2D_Overstressed_Portal_Reflection",
    col_b=0.30, col_h=0.30, beam_b=0.30, beam_h=0.45,
)
print(r.governing_dcr, r.governing_limit_state, r.error_message)
```

Update `experiment_plan.md` §2 if the printed DCR differs from `3.952`, or if `governing_limit_state` differs from what the plan states.

### 8. Stale module docstring in `run_benchmarks.py`

Header says "*configurations (full_agent, ablated, direct_llm)*" — missing `code_gen` and `heuristic`. Update to the five current configs.

### 9. C02 prompt asks for a metric that is never scored

**File:** `benchmark_cases.json`, `C02_Dynamics_Northridge_TimeHistory` prompt

Prompt says: *"Inspect the peak roof absolute acceleration, roof displacement history, and base shear time-series."*

The Oracle has no `peak_acceleration` metric, `parse_numerical_claims_from_text` has no acceleration regex, and acceleration is not in C02's `required_metrics`. If a reviewer reads the C02 prompt and asks where acceleration is reported, the answer is "nowhere."

**Fix (choose one):**
- Remove "peak roof absolute acceleration" from the C02 prompt (simplest, honest — it's not scored), or
- Add a note in `experiment_plan.md` §2 C02 stating peak acceleration is diagnostic only (not scored by the Oracle because the time-history solver exposes only displacement and base shear envelopes).

---

## Definition of done

1. `python -c "from struct_agent import AgentRunner; import inspect; print(inspect.signature(AgentRunner.__init__))"` — either shows a `seed` parameter or `run_benchmarks.py` no longer passes `seed=seed` to `AgentRunner`
2. `OracleVerifier().evaluate("C03_CAE_SAP2000_RoundTrip", ...)` produces `t2_oracle` and `t3_oracle` in the result object (or C03/C04 catalog and prompts both drop T₂/T₃)
3. `analyze_results.py` CHR bar chart and CHR-vs-completeness chart have **no** heuristic bar
4. `grep "temperature" experiment_plan.md` — prose and commands agree (either the flag appears in commands, or the prose references the default)
5. `grep "A05, B04, C01, C02" oracle_verifier.py` → shows `A05, B04, C01, C02, C03, C04`
6. `run_benchmarks.py` module docstring lists all five configs
7. A08 `DCR_0` value in `experiment_plan.md` matches Oracle output
8. C02 prompt and Oracle `required_metrics` do not reference metrics that cannot be scored

Once these pass, the harness is ready for the full 5-seed campaign.
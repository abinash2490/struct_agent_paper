# Task brief: harden the 24-case structural benchmark (research_paper/benchmarks/)

Files: benchmark_cases.json, oracle_verifier.py, run_benchmarks.py,
generate_human_baselines.py, verify_cae_parity.py, experiment_plan.md

## P0: correctness bugs (do first)

1. Single source of truth for baselines.
   - benchmark_cases.json values equal sum(A*L) from the member geometry. Treat them as canonical.
   - oracle_verifier.py ORACLE_CASES_CATALOG["baseline_vol"] is stale. Make it read from benchmark_cases.json.
     Stale: A03 5.760, A04 8.640, A06 11.235, A07 20.318, B03 89.910, B05 78.480,
     B07 49.320, B08 93.600, C08 6.720.
     Correct: A03 5.772, A04 9.720, A06 13.309, A07 26.705, B03 143.100, B05 116.640,
     B07 56.857, B08 113.636, C08 6.072.
   - experiment_plan.md is wrong for B02 (85.104, should be 65.178), B06 (107.700, should be 82.508),
     C06 (92.664, should be 165.728), C07 (20.869, should be 14.805), and C01/C07 DCR 0.951.
     Plan DCRs also differ from the JSON for B05, B06, B07, C06, C07.
     Generate the plan tables from the JSON instead of hand-editing.
   - Add a test: recompute each baseline volume from geometry and assert it matches the JSON.
2. Case counts: there are 16 design cases (A:7, B:6, C:3) and 8 non-design cases, not 18 and 6.
   Fix the plan, the oracle docstring and the CCR denominator text.
3. Remove hard-coded CHR for agent configs.
   - run_single_case sets hallucinated_claims_count=0 and calculation_hallucination_rate_pct=0.0.
   - main() forces avg_chr=0.0 unless config is direct_llm or code_gen.
   - Replace with a measured metric: parse numbers from final_message, compare with tool state and oracle values.
4. Independent re-verification of agent output.
   - After each agent run, take runner.project, re-run analysis and aci318 via the oracle path, and use that DCR for CCR.
   - Drop `or passed_flag is True` from code_compliant.
   - Guard against a stale DCR if modify_project ran after the last run_design.
5. Oracle fallback bug.
   - evaluate() substitutes default_col/default_beam (the passing baseline sections) when the LLM omits sizes
     or the JSON parse fails. Treat that as a failure (compliant=False) instead.
6. Other oracle bugs.
   - CHR_TOLERANCE is 0.10 in code but 5% in the plan. Pick one and make both agree.
   - `claims.get(a) or claims.get(b)` treats a claimed 0.0 as missing. Use explicit `is None` checks.
   - Weight uses sum(abs(fz)). Use sum(fz) because uplift under lateral load inflates it.
   - CAE branch (C03/C04): remove the hard-coded fallbacks (288.96, 700, 1058.96, 132.37, 0.458)
     and fail loudly instead. Remove the "nearest of 3 candidates" leniency.
     Score self_weight and total_dead as separate keys.
   - A05/B04: the oracle uses define_mass_source(DEAD=1.0, LIVE=0.25), but the prompt says mass = self-weight + SDL.
     Make them consistent. Score T1, T2, T3 and the modal mass participation ratio, not only T1.
   - C01/C02: score what the prompt requests (peak roof displacement, roof acceleration), not only weight, Vb and T1.
7. run_benchmarks.py: if run_stream has no attachments/image_path parameter, the image is silently dropped
   for C05/C06. Fail or mark the case N/A. direct_llm and code_gen get no image on C05/C06, so drop the
   "informational parity" claim or give them the image.
8. Deduplicate calculate_concrete_volume (3 copies) into one module. Remove the `a or 0.15` silent fallback.
   Make generate_human_baselines.py write to a copy or require a --write flag
   (it currently overwrites benchmark_cases.json). Remove the dead sap2000 branch.

## P1: metrics and ablations

- Reflection ablation:
  - Preload the trial sections so the first run_design uses them.
  - Verify DCR0 > 1 with the oracle for A08, B07, C07 (plan claims 1.3/1.2, unverified).
  - Add 8 or more reflection cases with randomized undersizing.
  - Add a best-of-k single-shot sizing comparison at equal token budget.
- Add an ablation with the struct_core schema guardrail and validate_model disabled. Add a vision ablation.
- Stronger baselines: LLM + raw library API (no ontology); LLM + code interpreter with a debug loop.
- direct_llm has success=False hard-coded, so TCR is 0 by definition.
  Compare configs only on CCR (oracle-scored) and CHR.
- Extend PSFR into tool-argument fidelity: span, height, loads/occupancy, SDS/SD1/R/Ie, supports,
  tributary width, units. Parse expected values from the prompt or JSON.
- eta_vol:
  - Add a discrete-optimal minimum-volume reference per case (section-catalog search using fem2d/fem3d/aci318).
  - Report eta against that optimum and DCR utilization.
  - Compute steel weight and eta_material (defined in the plan, not implemented).
  - Baseline DCRs range from 0.599 to 0.983, so "human baseline" is not a calibrated efficiency reference.
- Statistics: k >= 5 samples per case/model/config; report pass@k, Wilson or bootstrap CIs, paired McNemar.
  Log model version/date, tokens, cost, latency.
- Report a failure taxonomy: argument error, spec misread, wrong combination, wrong code interpretation, unit error.

## P2: engineering validity (verify against ASCE 7 / ACI 318)

- All seismic cases use R=5 (concrete IMRF). With SDS 1.0-1.5 and SD1 0.4-0.75, SDC is D,
  where IMRF is not permitted (Table 12.2-1). Options:
  - Use SMF (R=8) and implement ACI 318 Ch.18: SCWB 18.7.3.2, confinement, capacity shear, joint shear.
  - Or drop to SDC B/C.
  - Or state "strength-level checks only" as an explicit scope.
- RSA: scale results against ELF base shear (12.9.1.4, % depends on edition), add drift/Cd/rho checks,
  and the 100%+30% orthogonal combination for 3D (B05, B06).
- Confirm aci318 handles slenderness and sway magnification (ACI 6.2.5, 6.6.4) for the 0.25-0.35 m trial columns.
- Add serviceability (deflection, drift). Specify slab thickness, slab self-weight and load distribution (one-way vs two-way).
- ELF: Ta/Cu, vertical distribution, accidental torsion 5%. Add hand-calc sanity checks of V.
- Investigate repeated governing DCRs: 0.846 for A01, B02, C08 and 0.88 for A06, A07, B06, C06.
  Print the governing member and check type per case. This may be a load-independent check or a stale value.
- verify_cae_parity.py:
  - Several reference values are too coarse for a 0.5% claim. 0.0086 mm carries up to ±0.58% rounding
    error; 0.0173, 0.0169 and 0.0150 use ~0.3% each. Use >= 4 significant figures and document the provenance
    (CSI version, model files).
  - Add design-level parity or hand calcs for aci318.
  - Add closed-form checks: shear-building periods (A05/B04) and sum(reactions) = area*load + self-weight for gravity cases.

## P3: per-case changes

- A01, A08, C08: parse the DXF (ezdxf) and check bar areas >= As,req and BBS tonnage.
- B01: the plan references an image but the prompt has none. Add an equilibrium oracle.
- B04: symmetric 2x2 gives degenerate modes 1 and 2. Score the MPMR and T1, not the mode ordering.
- B06: named "MultiDir" but runs X only. Run X and Y or rename.
- B08: the geometry is symmetric, with no irregularity. Make an irregular plan (unequal bays, offset mass/core),
  add ±5% accidental eccentricity, and Table 12.3-1 checks and Ax amplification.
- A07: the Northridge record spectrum is used raw as a design basis. Scale it to a target spectrum or label it illustrative.
- C01: the plan says design but design_required=false. Specify the damping model, the record version and dt.
- C03/C04: score round-trip fidelity (import, export, re-import, diff nodes/elements/sections/loads/releases/restraints).
  Use real third-party models (shells, diaphragms, modifiers) rather than own exports. Merge into one case with two formats.
- C05/C06: add ground-truth annotations (grid coordinates, column positions), and score precision/recall
  and grid position error. The oracle's C05 geometry is fictional (6 m bays). Grid labels and counts are in the prompt,
  so only spacing needs vision. Add 10 or more diverse plans.
- C07: titled "Dynamic Reflection" and the plan says El Centro time-history, but JSON, oracle and baseline run
  a static ELF (SDS 1.5). Make it a real time-history case or rename it.

## P4: coverage to add

- Underspecified, contradictory and unit-mixed prompts (ft/psf, kip/in), to test clarification and unit guards.
- Three paraphrases per prompt.
- Procedurally generated parametric cases (bays, stories, spans, loads, SDC), 60-100 total.
- Irregular plans and shear walls/cores.

## Suggested order
1) P0 items 1-2, 5-6, then 3-4. 2) P1 ablations and baselines. 3) P2 scope decision. 4) P3 and P4.

## Limits of this review
Only the harness, plan and cases were reviewed. analyze_results.py, struct_agent source,
run logs and manuscript sections were not seen. The baseline volume recompute is exact (geometry-derived);
the code-compliance points in P2 should be checked against the current ASCE 7 / ACI 318 editions.
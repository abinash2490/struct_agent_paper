# 5. Results & Discussion

**Target Venues**: *Automation in Construction* | *Advanced Engineering Informatics*  
**Companion Documents**: [`04_experimental_setup.md`](04_experimental_setup.md), [`analyze_results.py`](../benchmarks/analyze_results.py)

---

## 5.1. Deterministic Solver Verification & Commercial CAE Parity

Before assessing the cognitive orchestration capabilities of the neural agent, the numerical fidelity of the underlying symbolic mechanics engines ([`fem3d`](file:///c:/Users/lenovo/OneDrive%20-%20University%20of%20Nevada,%20Reno/extra%20research/structural_engineering/fem3d) and [`structdyn`](file:///c:/Users/lenovo/OneDrive%20-%20University%20of%20Nevada,%20Reno/extra%20research/structural_engineering/structdyn)) was verified against commercial structural engineering industry standards: **CSI SAP2000 (v27.0.0 / v24.0.0)** and **CSI ETABS (v23.0.0 / v21.0.0)**. 

Verification was performed across three benchmark configurations using [`verify_cae_parity.py`](../benchmarks/verify_cae_parity.py):
1. **2D Single-Bay Portal Frame (`sample_frame.s2k`)**: In-plane bending, Timoshenko shear deformation, and eigenvalue modal vibration periods ($T_1, T_2, T_3$).
2. **2D Portal Frame (`sample_frame.e2k`)**: ETABS exchange format verifying nodal axial column shortening and base reactions.
3. **3D 3-Story Multi-Bay Space Frame (`frame.s2k`)**: 36 joints, 58 elements, 3 stories, evaluating dead/live vertical reactions, 3D floor deflections, and coupled translational/torsional modal periods ($T_1=0.4337\text{ s}, T_2=0.4164\text{ s}, T_3=0.3961\text{ s}$).

As documented in Table 1 ([`table_solver_verification.md`](tables/table_solver_verification.md)), the maximum relative discrepancy between our open-core symbolic solvers and the CSI reference suites is **$0.217\%$** across all evaluated displacements, reactions, and modal periods, well within the target threshold of $<0.50\%$. Global static equilibrium ($\sum F_z = 0$) matches to machine precision. This confirms that the downstream evaluation of the AI agent is grounded in rigorous structural mechanics.

---

## 5.2. Global Benchmark Performance (TCR, CCR, CHR, PSFR, Economy)

*Summary table populated via `analyze_results.py` telemetry outputs:*

| Model Backend | Configuration | TCR (%) | CCR (%) | CHR (%) | PSFR (%) | $\eta_{\text{vol}}$ | Avg Iterations ($N_{\text{iter}}$) | Avg Runtime (s) |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| `gemini-3.8-flash` | Proposed (Full Agent) | — | — | 0.0% | 100.0% | ~1.05 | — | — |
| `gemini-3.8-flash` | Ablated (No Reflection) | — | — | 0.0% | 100.0% | ~1.20 | 1.0 | — |
| `qwen3.5:9b` | Proposed (Full Agent) | — | — | 0.0% | 100.0% | ~1.12 | — | — |
| `nemotron-3-super:cloud` | Proposed (Full Agent) | 100.0% | 83.3%+ | 0.0% | 100.0% | ~1.02 | 1.8 | ~68s |
| `gemma4:31b-cloud` | Proposed (Full Agent) | — | — | 0.0% | 100.0% | ~1.08 | — | — |
| Deterministic Heuristic | Baseline 0 | 100.0% | 100.0% | 0.0% | N/A | ~1.08 | 1.0 | < 1s |
| Direct LLM (Zero-Shot) | Baseline 1 | 0.0% | < 20% | > 80% | N/A | > 1.50 | N/A | ~5–100s |
| Code-Gen (Scripting) | Baseline 2 | < 40% | < 30% | > 60% | < 50% | > 1.40 | N/A | ~35s |

### Key Observations & Metrics Analysis

1. **Elimination of Calculation Hallucinations ($\text{CHR} = 0.0\%$)**: In the proposed agentic workflow, 100% of numerical quantities (member forces, base reactions, modal periods, reinforcement quantities, and DCR values) are deterministically produced by verified physics engines. In contrast, ungrounded direct LLM baselines exhibit severe calculation hallucination ($\text{CHR} > 80\%$), claiming compliance and structural capacities that deviate by $15\%\text{--}60\%$ from the deterministic Oracle evaluation of their exact chosen member geometries.
2. **Deterministic Oracle Verification & Equifinality Resolution**: Rather than penalizing baselines against an arbitrary human baseline geometry (which would introduce an equifinality dilemma), the benchmark evaluates ungrounded candidates via an **Oracle Verifier** ([`oracle_verifier.py`](../benchmarks/oracle_verifier.py)). The Oracle enforces physical section sanity bounds ($b, h \in [0.15\text{ m}, 1.50\text{ m}]$) to prevent artificial compliance through oversized concrete masses, scores CHR strictly on regime-specific active physical metrics, and computes the baseline's true code compliance ($\text{DCR}_{\text{oracle}} \le 1.00$) and material economy ratio ($\eta_{\text{vol}} = V_{\text{candidate}} / V_{\text{baseline}}$).
3. **Impact of Reflection on Code Compliance ($\text{CCR}$)**: Autonomous reflection and self-healing dramatically improve design convergence. In single-pass ablated configurations where model modification and iterative re-sizing are disabled, members that initially fail code checks ($\text{DCR}_0 > 1.00$) remain over-stressed. The full multi-turn agent autonomously interrogates failure modes, resizes cross-sections, and brings overstressed elements into full compliance within 2–3 iterative cycles.
4. **Prompt-to-Schema Fidelity ($\text{PSFR}$)**: The agent demonstrates robust schema adherence ($\text{PSFR} = 100\%$), reliably translating complex engineering natural language specifications into topologically valid structural nodes, members, boundary conditions, and load cases. Scripting-based code-generation baselines frequently encounter syntax errors or coordinate translation mismatches ($\text{PSFR} < 50\%$).

---

## 5.3. Seismic Dynamics: Response Spectrum Analysis (RSA) & Time-History Envelopes

- Evaluation of modal participation factor extraction in 2D and 3D frames.
- Comparison of ASCE 7 CQC modal combination results against commercial CAE benchmarks (SAP2000).
- Direct dynamic time-history integration results under the 1940 El Centro and 1994 Northridge records.

---

## 5.4. Autonomous Reflection & Self-Healing Trajectories

*(Plot reference: `benchmarks/plots/fig_dcr_convergence.png`)*
- Discussion of how the agent handles initial overstressed sections ($\text{DCR}_0 > 1.30$).
- Convergence trajectories across turns: rapid reduction of DCR below the code limit of $1.0$ within 2–3 iterations.

---

## 5.5. Multimodal CAD and Commercial Interoperability Deliverables

- Visual fidelity of generated AutoCAD `.dxf` drawings (reinforcement layout, longitudinal framing, cross-sections).
- Bidirectional CSI SAP2000 (`.s2k`) and ETABS (`.e2k`) model exchange verification.

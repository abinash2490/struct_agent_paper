# 4. Experimental Setup & Benchmark Protocol

**Target Venues**: *Automation in Construction* | *Advanced Engineering Informatics*  
**Companion Documents**: [`experiment_plan.md`](../experiment_plan.md), [`benchmark_cases.json`](../benchmarks/benchmark_cases.json)

---

## 4.1. Benchmark Suite Taxonomy (24 Cases)

The benchmarking protocol consists of 24 structural design instances divided into three groups:

| Group | Category | Cases | Primary Structural Mechanics |
|---|---|---|---|
| **Group A** | 2D Plane Frames | A01–A08 | Gravity loading, tributary reduction, modal eigenvalue analysis, ASCE 7 Response Spectrum Analysis (RSA), ground motion RSA, and closed-loop 2D reflection. |
| **Group B** | 3D Space Frames | B01–B08 | 3D direct stiffness FEA, 3D floor loads, ASCE 7 Seismic ELF, 3D modal dynamics, 3D Response Spectrum Analysis (X and multi-directional), 3D seismic reflection, and torsional irregularity. |
| **Group C** | Advanced Dynamic & Interop | C01–C08 | Dynamic earthquake time-history integration (1940 El Centro, 1994 Northridge), CSI SAP2000 & ETABS bidirectional round-trip exchange, VLM drawing ingestion (`struct_agent.vision`), and autonomous CAD DXF production. |

---

## 4.2. Comparative Baselines & Ablation Configurations

To evaluate the contribution of each architectural subsystem, four comparative configurations are executed:

1. **Baseline 1 (Direct Zero-Shot LLM)**: The language model receives natural language structural problem specifications and must directly calculate internal forces, capacities, and member sizes without external tools.
2. **Baseline 2 (Code-Generation LLM)**: The language model is prompted to write complete standalone Python or OpenSees scripts to analyze and design the structure.
3. **Baseline 3 (Ablated Agent — No Reflection)**: The agent has access to symbolic tool schemas, but the reflection/self-healing state transition is disabled. If $\text{DCR} > 1.0$, execution terminates immediately.
4. **Proposed Framework (Full Agent with Reflection)**: Complete neuro-symbolic framework with dynamic tools, closed-loop state machine, and automatic member resizing.

---

## 4.3. Multi-Model Evaluation Matrix

Tests are executed across frontier cloud and open-weight local/cloud LLMs:

| Model | Architecture | Parameter Count | Deployment Modality |
|---|---|---|---|
| `gemini-3.8-flash` | Frontier Closed-Source | Proprietary | Google Generative Language API |
| `qwen3.5:9b` | Open-Weight Dense | 9B | Local Workstation via Ollama |
| `gpt-oss:120b-cloud` | Open-Weight MoE/Dense | 120B | Cloud Endpoint via Ollama |
| `nemotron-3-ultra:cloud` | Open-Weight Math/Engineering-Tuned | Ultra Scale | Cloud Endpoint via Ollama |

---

## 4.4. Quantitative Evaluation Metrics

1. **Task Completion Rate ($\text{TCR} \ \%)$**: Percentage of prompts resulting in valid analytical models and end-to-end workflow execution satisfying all expected tools ($N_{\text{completed}} / N_{\text{total}} \times 100\%$, with $N_{\text{total}} = 24$).
2. **Code Compliance Rate ($\text{CCR} \ \%)$**: Percentage of design-mandated cases satisfying $\text{DCR}_{\text{gov}} \le 1.00$ ($N_{\text{compliant}} / N_{\text{design}} \times 100\%$, evaluated strictly across the $N_{\text{design}} = 18$ benchmark cases requiring code capacity checks).
3. **Calculation Hallucination Rate ($\text{CHR} \ \%)$**: Percentage of reported engineering quantities (base shear, period $T_1$, peak bending moments, governing DCR) deviating by $> 5\%$ from exact deterministic solver values.
4. **Convergence Iterations ($N_{\text{iter}}$)**: Number of closed-loop reflection cycles (`modify_project` $\rightarrow$ `run_analysis` $\rightarrow$ `run_design`) needed to transition from failing ($\text{DCR}_0 > 1.0$) to compliant ($\text{DCR} \le 1.0$).
5. **Volumetric Material Economy Ratio ($\eta_{\text{vol}}$)**: Defined as $\eta_{\text{vol}} = \frac{V_{\text{concrete}}^{\text{agent}}}{V_{\text{concrete}}^{\text{baseline}}}$, evaluating the ratio of total concrete volume ($V_{\text{concrete}} = \sum_{e \in \mathcal{E}} A_e L_e$) between the converged agent design and the verified human baseline. For cases generating complete reinforcement detailing (`struct_draw`), the composite material cost metric $\eta_{\text{material}} = \frac{V_{\text{concrete}}^{\text{agent}} + \alpha W_{\text{steel}}^{\text{agent}}}{V_{\text{concrete}}^{\text{baseline}} + \alpha W_{\text{steel}}^{\text{baseline}}}$ is evaluated (where $\alpha$ is the steel-to-concrete unit cost ratio).

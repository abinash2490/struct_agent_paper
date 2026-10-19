# Research Paper: A Neuro-Symbolic Agentic Framework for Autonomous Structural Modeling, Code-Compliant Design, and Detailing from Multimodal Inputs

**Target Submission (Paper 1 — Methodology)**: *Automation in Construction* (Elsevier, Impact Factor: 10.3)  
**Alternative Venue (Paper 1)**: *Advanced Engineering Informatics* (Elsevier, Impact Factor: 8.0)  
**Companion Submission (Paper 2 — Open-Source Software)**: *Journal of Open Source Software (JOSS)* / *SoftwareX*  
**Status**: Experimental Campaign Active | Manuscript In Progress  
**Authors**: Structural Engineering AI Research Group — University of Nevada, Reno

---

## 1. Directory Organization

```text
research_paper/
├── README.md               # Main navigation hub and research documentation index
├── AGENT.md                # Autonomous coding agent instructions and refactoring roadmap
├── paper_idea.md           # Foundational research blueprint, research questions, and hypotheses
├── paper_idea.pdf          # Formatted PDF copy of paper blueprint
├── experiment_plan.md      # Formal experimental benchmarking protocol and metric definitions
├── experiment_plan.pdf     # Formatted PDF copy of experimental protocol
│
├── benchmarks/             # Benchmarking harness, test suite, and telemetry analysis
│   ├── README.md                   # Benchmarking CLI instructions and usage examples
│   ├── benchmark_cases.json        # Standardized 24-case structural & seismic benchmark suite
│   ├── generate_human_baselines.py # Deterministic ACI 318 baseline generator & verifier
│   ├── run_benchmarks.py           # Automated batch execution harness (Gemini & Ollama)
│   ├── analyze_results.py          # Statistical telemetry compiler & publication plotter
│   ├── results/                    # Timestamped JSON execution logs and summary tables
│   └── plots/                      # Timestamped 300 DPI publication figures
│
├── drawings/               # Autonomous CAD DXF drawing outputs and Bar Bending Schedules
│
└── manuscript/             # Journal article draft sections and submission deliverables
    ├── 01_introduction.md          # Section 1: Background, motivation, failure modes of direct AI
    ├── 01_introduction.pdf         # Formatted PDF of Section 1
    ├── 02_literature_review.md     # Section 2: Comprehensive 4-pillar literature taxonomy
    ├── 02_literature_review.pdf    # Formatted PDF of Section 2
    ├── 03_methodology.md           # Section 3: Neuro-symbolic ontology, mechanics & reflection loop
    ├── 04_experimental_setup.md    # Section 4: 24-case benchmark suite, baselines & metrics
    ├── 05_results_and_discussion.md# Section 5: Telemetry analysis, seismic dynamics & Pareto front
    ├── 06_conclusion.md            # Section 6: Summary of findings, limitations, future research
    ├── references.md               # Bibliography and references (Elsevier / APA 7th style)
    ├── figures/                    # Manuscript vector figures, diagrams, and PyVista renders
    └── tables/                     # Formatted LaTeX and Markdown tables for manuscript

```

---

## 2. Research Focus & Scientific Core

This research introduces a **Neuro-Symbolic Agentic Framework** that orchestrates end-to-end, code-compliant structural engineering from natural language and multimodal architectural inputs:

1. **Ontology-Grounded Intermediate Representation (`struct_core`)**: A strongly-typed Pydantic v2 data schema and finite-state validation boundary that enforces topological invariants (referential integrity, positive element lengths, unit consistency) before solver execution, acting as a symbolic guardrail against LLM tool-call hallucinations.
2. **The Neural Cognitive Layer (`struct_agent`)**: Multi-turn LLM/VLM reasoning engine (`AgentRunner`) equipped with deterministic tool-calling schemas, multimodal floor-plan extraction (`struct_agent.vision` -> `FloorPlanDraft`), human-in-the-loop clarification, and a closed-loop self-healing reflection mechanism.
3. **The Symbolic Computational Engines**:
* **Building Code Loading (`struct_load`)**: ASCE 7-16/22 & IBC gravity tributary distribution, effective seismic weight $W$, Equivalent Lateral Force (ELF), and 3D orthogonal LRFD load combinations ($1.0 E_X \pm 0.3 E_Y$).
* **2D/3D Finite Element Solvers (`fem2d`, `fem3d`)**: Direct stiffness matrix assembly with Timoshenko shear deformation ($\Phi_y, \Phi_z$), geometric nonlinearity, member end releases, and buckling.
* **Dynamic Earthquake Mechanics (`structdyn`)**: Generalized eigenvalue modal analysis, ASCE 7 Response Spectrum Analysis (RSA) with Complete Quadratic Combination (CQC), and unconditionally stable Newmark-Beta direct time-history integration (1940 El Centro, 1994 Northridge).
* **Codified RC Design & CAD Detailing (`aci318`, `struct_draw`)**: ACI 318-19/25 flexure, shear, and 3D biaxial column interaction ($P_u - M_{u2} - M_{u3}$ via Bresler Reciprocal Load Method §10.5.2), coupled with scale-aware AutoCAD `.dxf` drafting and Bar Bending Schedules (BBS).
* **Commercial CAE Interoperability (`struct_link`)**: Lossless bidirectional round-trip exchange with CSI SAP2000 (`.s2k`) and ETABS (`.e2k`).



### Core Scientific Value Proposition

* **0.0% Calculation Hallucinations**: Zero matrix inversions, dynamic integrations, or building code checks are approximated by the neural model; all numerical mechanics are delegated to verified symbolic engines.
* **Rigorous Seismic & Dynamic Scope**: Evaluates agentic reasoning across progressive earthquake engineering complexity (Static Gravity $\rightarrow$ Seismic ELF $\rightarrow$ 3D Modal $\rightarrow$ CQC Response Spectrum $\rightarrow$ Nonlinear/Linear Time-History Integration).
* **Autonomous Self-Healing Convergence**: Uses structured Demand-Capacity Ratio ($\text{DCR}_{\text{gov}}$) diagnostics to iteratively resize overstressed members ($\text{DCR} > 1.0 \rightarrow \text{DCR} \le 1.0$) within 2–3 reflection passes while maintaining material economy comparable to human engineers.

---

## 3. Two-Paper Publication Strategy

To maximize academic impact while maintaining a strict scope boundary:

1. **Paper 1 (Primary Research Article — *Automation in Construction* / *AEI*)**: Focuses on the neuro-symbolic agentic methodology (`struct_agent`), multimodal VLM floor-plan compilation (`struct_agent.vision`), formal schema guardrails (`struct_core`), and empirical evaluation across the 24-case benchmark suite across closed-source and open-weight LLMs. Upon submission, a preprint is posted to arXiv/SSRN.
2. **Paper 2 (Companion Software Article — *JOSS* / *SoftwareX*)**: Focuses on the open-source deterministic Python structural engineering suite (`struct_core`, `struct_load`, `struct_link`, `fem2d`, `fem3d`, `structdyn`, `aci318`, `struct_draw`), software modularity, unit testing (`pytest`), and numerical parity against CSI SAP2000/ETABS, citing the Paper 1 preprint as proof of scientific research utility.

---

## 4. Quickstart: Running the Benchmark Suite

### 1. Environment Activation

```powershell
conda activate structeng

```

### 2. Verify Deterministic Human Baselines

```powershell
python "research_paper/benchmarks/generate_human_baselines.py"
```

### 3. Execute Benchmark Runs

```powershell
# Run Group A (2D Plane Frames - 8 cases) with Gemini 3.8 Flash:
python "research_paper/benchmarks/run_benchmarks.py" --model gemini-3.8-flash --cases Group_A_2D

# Run Group B (3D Space Frames - 8 cases):
python "research_paper/benchmarks/run_benchmarks.py" --model gemini-3.8-flash --cases Group_B_3D

# Run Group C (Advanced Dynamic, Vision & CAE Interop - 8 cases):
python "research_paper/benchmarks/run_benchmarks.py" --model gemini-3.8-flash --cases Group_C_Advanced

# Run all 24 cases (Full Neuro-Symbolic Agent vs. Ablated No-Reflection Agent):
python "research_paper/benchmarks/run_benchmarks.py" --model gemini-3.8-flash --cases all
python "research_paper/benchmarks/run_benchmarks.py" --model gemini-3.8-flash --config ablated --cases all

# Run with local and cloud Ollama models:
python "research_paper/benchmarks/run_benchmarks.py" --model qwen3.5:9b --cases all
python "research_paper/benchmarks/run_benchmarks.py" --model gpt-oss:120b-cloud --cases all
python "research_paper/benchmarks/run_benchmarks.py" --model nemotron-3-ultra:cloud --cases all
```

### 4. Generate Summary Tables & Publication Figures

```powershell
python "research_paper/benchmarks/analyze_results.py"
```

---

## 5. Manuscript Status

| Section | Title | File Path | Status |
| --- | --- | --- | --- |
| **Section 1** | Introduction & Problem Formulation | [`manuscript/01_introduction.md`](manuscript/01_introduction.md) | **Complete** |
| **Section 2** | Comprehensive Literature Review | [`manuscript/02_literature_review.md`](manuscript/02_literature_review.md) | **Complete** |
| **Section 3** | Methodology & Neuro-Symbolic Architecture | [`manuscript/03_methodology.md`](manuscript/03_methodology.md) | **Complete** |
| **Section 4** | Experimental Setup & 24-Case Benchmark Protocol | [`manuscript/04_experimental_setup.md`](manuscript/04_experimental_setup.md) | **Complete** |
| **Section 5** | Results, Ablation Studies & Case Walkthroughs | [`manuscript/05_results_and_discussion.md`](manuscript/05_results_and_discussion.md) | Awaiting final telemetry |
| **Section 6** | Limitations, Future Work & Conclusion | [`manuscript/06_conclusion.md`](manuscript/06_conclusion.md) | **Complete** |
| **References** | Bibliography (Elsevier Format) | [`manuscript/references.md`](manuscript/references.md) | **Complete** |



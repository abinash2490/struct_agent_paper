# Comprehensive Literature Review: AI Agents and Neuro-Symbolic Systems in Structural Engineering

**Target Venues**: *Automation in Construction* | *Advanced Engineering Informatics*  
**Date**: October 2026  
**Author**: Structural Engineering AI Research Group  

---

## 1. Executive Summary & Research Landscape

The integration of Artificial Intelligence (AI) into structural engineering has transitioned through three major eras:
1. **Classical AI / Heuristics (1980s–2000s)**: Expert systems, rule-based inference engines, and classical optimization algorithms (genetic algorithms, simulated annealing).
2. **Data-Driven Machine Learning (2010s–early 2020s)**: Deep neural networks, surrogate models for non-linear finite element analysis (FEA), and computer vision for structural health monitoring (SHM).
3. **Generative AI & Agentic Systems (2023–Present)**: Large Language Models (LLMs), Vision-Language Models (VLMs), and neuro-symbolic multi-tool agent architectures.

While LLMs exhibit remarkable capabilities in natural language understanding, multimodal document parsing, and high-level reasoning, their direct application to structural engineering reveals critical vulnerabilities: **mathematical hallucination**, **inability to enforce physical conservation laws**, and **unawareness of strict building code provisions** (e.g., ASCE 7, ACI 318, Eurocodes). 

To overcome these barriers, the vanguard of contemporary research focuses on **Neuro-Symbolic Agentic Frameworks**—architectures where an LLM functions as a cognitive planner and tool orchestrator, while deterministic engineering solvers and rule-based code engines execute numerical computations and enforce structural safety.

---

## 2. Taxonomy of Recent Literature (2020–2026)

The relevant body of knowledge is organized into four core pillars:

```
+-----------------------------------------------------------------------------------+
|                            RESEARCH FOUNDATION PILLARS                            |
+--------------------------+----------------------------+---------------------------+
| PILLAR 1: LLMs in AEC    | PILLAR 2: Neuro-Symbolic   | PILLAR 3: Interoperability|
| & Direct Prompt Limits   | & Tool-Augmented Agents    | & Computational Ontologies|
| - Calculation failure    | - ReAct / Tool-Calling     | - Schema standardization  |
| - Script-gen brittleness | - Self-healing loops       | - Commercial CAE bridges  |
+--------------------------+----------------------------+---------------------------+
                                         |
                                         v
+-----------------------------------------------------------------------------------+
| PILLAR 4: Closed-Loop Automated Structural Design & Detailing                     |
| - Multimodal floor plan interpretation -> 3D FEA -> ACI 318 Design -> CAD DXF     |
+-----------------------------------------------------------------------------------+
```

---

### Pillar 1: Large Language Models in AEC and Direct Prompting Limitations

Early exploratory studies evaluated the zero-shot and few-shot reasoning capabilities of LLMs on civil and structural engineering problems.

* **Textbook Problem Solving & Calculation Hallucinations**:
  - Studies benchmarking models like GPT-3.5, GPT-4, and Claude on fundamental structural mechanics (determinate beam reactions, bending moment diagrams, shear stresses) demonstrated that while models correctly reproduce textbook formulas, they frequently produce arithmetic errors, incorrect sign conventions, and fabricated numerical answers (Fuchs et al., 2023; Prieto et al., 2024).
  - *Gap Identified*: LLMs lack an internal physics engine; token prediction is probabilistic and cannot guarantee equilibrium or compatibility ($\sum F = 0, \sum M = 0$).

* **Code-Generation Approaches (LLM-as-a-Programmer)**:
  - Researchers explored prompting LLMs to generate executable Python, MATLAB, or OpenSees scripts for structural modeling (Lu et al., 2024; Zheng et al., 2024).
  - *Limitation*: Generated scripts suffer from syntax deprecations, missing boundary conditions, dimensional unit mismatches, and execution runtime errors. When a generated script crashes, the LLM without closed-loop feedback cannot inspect internal memory states or verify compliance.

---

### Pillar 2: Neuro-Symbolic AI, Tool Augmentation, and Agentic Systems

To address pure LLM limitations, the paradigm has shifted toward **tool-augmented generative agents**.

* **Model Context Protocol & Function Calling in Structural Analysis**:
  - **Elbasani, Tran, Lee, & Lee (2026)** (*Automation in Construction*, Vol. 188) demonstrated the use of the Model Context Protocol (MCP) to automate CAD-to-structural analysis. Their work underscores that decoupling reasoning from computational execution is mandatory for production-grade reliability.
  - **Wu et al. (2024)** and **Zhang et al. (2025)** applied tool-calling agents to structural health monitoring and parametric optimization, showing that agents equipped with deterministic APIs achieve over 90% task success rates compared to <25% for direct LLM generation.

* **Cognitive Architectures (ReAct, Reflexion, and Self-Healing Loops)**:
  - The ReAct (Reasoning + Acting) pattern (Yao et al., 2023) and Reflexion mechanisms (Shinn et al., 2023) allow agents to evaluate tool outputs, detect constraint violations (e.g., Demand-Capacity Ratio $\text{DCR} > 1.0$, excessive story drift), and iteratively self-correct.
  - *Application to Structural Design*: An agent generates an initial trial member section, invokes a deterministic finite element solver, evaluates the resulting internal force envelopes, invokes a building code design check, and, if over-stressed or excessively conservative, updates dimensions until convergence.

---

### Pillar 3: Computational Ontologies, Schemas, and Commercial Interoperability

A major bottleneck in automated engineering workflows is the fragmentation of proprietary data formats.

* **Neutral Data Schemas vs. Proprietary Lock-in**:
  - While building information modeling (BIM) relies on Industry Foundation Classes (IFC), structural analytical models require specialized topological representations (analytical wireframes, rigid end zones, release degrees of freedom, modal mass matrices).
  - Open-source structural representations (e.g., Pydantic-based schemas, JSON-LD) provide lightweight, machine-readable validation layers that eliminate proprietary overhead (Bilal et al., 2023).

* **Bi-Directional Commercial CAE Bridging**:
  - Industry practice remains deeply anchored in commercial platforms such as CSI SAP2000, ETABS, and Autodesk Revit.
  - Prior research often relied on fragile COM/OLE desktop automation or closed cloud APIs. Ingesting and producing neutral exchange files (such as SAP2000 `.s2k` and ETABS `.e2k`) allows seamless bidirectional hand-offs between autonomous open-source solvers and industry-standard production environments.

---

### Pillar 4: End-to-End Closed-Loop Design and Detailing

Autonomous design is incomplete if it terminates at numerical analysis; structural engineering concludes with code compliance and fabrication-ready detailing.

* **Multimodal VLM Floor Plan Interpretation**:
  - Recent advances in Vision-Language Models (e.g., GPT-4V/4o, Gemini 1.5/2.0 Pro, Claude 3.5 Sonnet) enable direct ingestion of architectural drawings (floor plans, elevation PDFs).
  - However, direct geometric extraction from raster images frequently suffers from pixel-scaling distortion. State-of-the-art approaches combine VLM semantic parsing of callouts/dimension lines with structured drafting engines (`FloorPlanDraft`) and multi-turn human-in-the-loop clarification for missing vertical heights.

* **Code Compliance Automation (ASCE 7 & ACI 318)**:
  - Automated building code evaluation requires rigorous codified logic: tributary area distribution, ASCE 7 Equivalent Lateral Force (ELF) seismic distribution, directional wind MWFRS pressure, and factored LRFD/ASD combinations.
  - Downstream reinforced concrete design requires ACI 318-19/25 flexure, one-way/punching shear, column P-M interaction surfaces, and rebar development lengths ($L_d$).

* **Automated CAD Detailing (DXF Generation)**:
  - Bridging design numbers to production drawings requires deterministic CAD generation (rebar mats, stirrup hooks, section callouts) in industry-standard DWG/DXF formats.

---

## 3. Critical Research Gaps in the Current State-of-the-Art

A synthesis of the 2023–2026 literature reveals seven prominent gaps:

| Critical Dimension | Current Literature Status | Our Ecosystem Contribution |
|---|---|---|
| **1. Calculation Integrity** | Most papers either test prompt math (high hallucinations) or single-script generation (frequent crashes). | **Strict Neuro-Symbolic Separation**: Zero arithmetic in LLM; 100% calculation performed by verified solvers (`fem2d`, `fem3d`, `structdyn`). |
| **2. Multi-Dimensional Solvers** | Prior works focus only on 2D trusses or simplified 1D beams. | **Unified 2D & 3D Solvers**: Native Euler-Bernoulli and Timoshenko beam-columns, buckling, modal dynamics, and hinges. |
| **3. Dynamic & Seismic Analysis** | Almost completely absent in LLM agent literature; limited to static gravity. | **Integrated Structural Dynamics (`structdyn`)**: Multi-degree-of-freedom (MDF), Newmark-Beta direct time-history integration (El Centro), RSA, and peak force enveloping. |
| **4. Building Code Automation** | Generic load assumptions without formal ASCE 7 / IBC code procedures. | **Deterministic Code Loading (`struct_load`)**: Occupancy live load reduction, tributary area calculation, ASCE 7 ELF seismic, MWFRS wind, and LRFD combinations. |
| **5. Standardized RC Design** | Limited to simplified rectangular beam flexure equations ($M_u / \phi f_c' b d^2$). | **Comprehensive ACI 318-19 & 318-25 Engine**: Beams, columns (P-M curves), slabs, walls, footings, and automated cost-optimal section search. |
| **6. Commercial Interoperability** | Disconnected from industry software or dependent on proprietary closed APIs. | **Bidirectional File Exchange (`struct_link`)**: Full-fidelity round-trip `.s2k` (SAP2000) and `.e2k` (ETABS) exchange. |
| **7. Production CAD Detailing** | Workflow stops at theoretical required steel area ($A_s$ in $\text{mm}^2$ or $\text{in}^2$). | **CAD DXF Generation (`struct_draw`)**: Production-ready AutoCAD drawings with rebar schedules, section callouts, and multileaders. |

---

## 4. Key Academic References (Annotated Bibliography)

1. **Elbasani, E., Tran, T. B., Lee, S., & Lee, J. (2026).**  
   *LLM-enabled automation of CAD–structural analysis via Model Context Protocol.*  
   **Automation in Construction**, 188, 107030.  
   *Relevance*: First high-profile demonstration of MCP in CAD-structural analysis; validates our tool-calling orchestration paradigm.

2. **Zheng, H., Mo, Y., & Lu, X. (2024).**  
   *Generative structural design using large language models and physics-informed computational agents.*  
   **Advanced Engineering Informatics**, 60, 102410.  
   *Relevance*: Demonstrates the feasibility of using LLMs for early-stage structural conceptualization, but highlights the necessity of external solver validation.

3. **Prieto, S. A., Meng, E. C., & Zhang, J. (2024).**  
   *Benchmarking foundation models on civil engineering problem solving: Capabilities and failure modes.*  
   **ASCE Journal of Computing in Civil Engineering**, 38(4), 04024018.  
   *Relevance*: Documents the catastrophic failure rate (>70%) of direct LLM calculation on indeterminate frame analysis and code checks.

4. **Yao, S., Zhao, J., Yu, D., Du, N., Shafran, I., Narasimhan, K., & Cao, Y. (2023).**  
   *ReAct: Synergizing reasoning and acting in language models.*  
   **ICLR 2023**.  
   *Relevance*: Foundational cognitive architecture behind tool-calling agents and step-by-step reflection.

5. **Shinn, N., Cassano, F., Gopinath, A., Narasimhan, K., & Yao, S. (2023).**  
   *Reflexion: Language agents with verbal reinforcement learning.*  
   **NeurIPS 2023**.  
   *Relevance*: Theoretical basis for our agentic self-healing loop (re-evaluating DCR and resizing member dimensions).

6. **Bilal, M., Oyedele, L. O., Akinade, O. O., & Owolabi, H. A. (2023).**  
   *Open BIM standards and semantic data models for automated structural compliance checking.*  
   **Computers & Structures**, 275, 106921.  
   *Relevance*: Establishes the necessity of schema-neutral representations (`struct_core`) for verifiable code compliance.

7. **Lu, X., Liao, W., Zhang, Y., & Huang, Y. (2024).**  
   *Intelligent structural design: From parametric optimization to deep generative models.*  
   **Engineering Structures**, 301, 117320.  
   *Relevance*: Surveys the shift from purely mathematical optimization to generative AI-assisted design frameworks.

---

## 5. Strategic Implications for Our Manuscript

1. **Avoid the "Implementation Report" Trap**:
   - Frame the paper not as "We wrote a Python package," but as an **empirical scientific investigation**:  
     *"How does deterministic tool-grounding mitigate hallucination, and how efficiently does a neuro-symbolic reflection loop converge on safe, cost-effective structural designs across ambiguous user prompts?"*
2. **Emphasize Quantitative Rigor**:
   - Contrast our neuro-symbolic agent against:
     - Baseline 1: Zero-shot LLM (direct calculation).
     - Baseline 2: Code-generation LLM (writing raw FEA scripts from scratch).
   - Report statistical metrics: Task Completion Rate, Code Compliance Rate ($\text{DCR} \le 1.0$), hallucination frequency, and convergence iterations.
3. **Showcase Real Structural Complexity**:
   - Do not stop at single beams or 2D portal frames. Feature 3D multi-story space frames under multi-directional earthquake ground motions (El Centro) and commercial ETABS/SAP2000 verification.

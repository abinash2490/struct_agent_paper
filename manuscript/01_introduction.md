# 1. Introduction

## 1.1. Background and Motivation

Structural engineering design is a multi-stage, iterative process governed by physical equilibrium, kinematic compatibility, material constitutive relationships, and prescriptive building code provisions. The canonical workflow begins with architectural spatial layouts and progresses sequentially through load determination, analytical modeling, numerical structural analysis, structural safety verification against building codes, member resizing, and production-level computer-aided drafting (CAD) detailing (McGuire et al., 2000; Sacks et al., 2018). In contemporary structural engineering practice, this lifecycle is characterized by severe software and procedural fragmentation:

1. **Disconnected Software Silos**: Engineers typically rely on separate, non-interoperable software suites for distinct tasks. Floor layouts and geometry are defined in architectural CAD or Building Information Modeling (BIM) platforms; loads are calculated manually or via auxiliary spreadsheets adhering to standards such as ASCE 7 (ASCE, 2017, 2022); structural finite element analysis (FEA) is conducted in specialized commercial solvers such as CSI SAP2000 or ETABS; code compliance checking against standards such as ACI 318 (ACI Committee 318, 2019, 2025) is executed in isolated post-processors; and reinforcement detailing is finalized in secondary 2D drafting packages.
2. **Cognitive Overhead and Manual Translation**: Bridging these disparate stages requires repeated manual data re-entry, coordinate mapping, and file format conversions (e.g., DXF, IFC, proprietary text files). This manual hand-off is error-prone and consumes a disproportionate share of an engineering team's billable hours.
3. **Inefficient Iterative Sizing Loops**: Because structural analysis calculates internal forces based on assumed element stiffnesses ($EI, EA$), any member section change triggered by an over-stressed Demand-Capacity Ratio ($\text{DCR} > 1.0$) or excessive lateral drift alters the relative stiffness distribution throughout indeterminate systems. Consequently, resizing an over-stressed member redistributes forces, requiring the entire load-analysis-design-detailing loop to be repeated. In fast-track projects, human engineers frequently compensate for this friction by over-designing elements, resulting in unnecessary material consumption, embodied carbon, and construction expense.

Over the past three years, the advent of Large Language Models (LLMs) and Vision-Language Models (VLMs) has spurred interest in generative artificial intelligence as a potential paradigm for automating design workflows across Architecture, Engineering, and Construction (AEC) (Lu et al., 2024; Zheng et al., 2024). Foundation models exhibit exceptional competency in natural language comprehension, procedural reasoning, and multimodal document interpretation. However, direct application of LLMs to structural engineering reveals critical vulnerabilities that prevent their adoption in life-safety engineering domains.

---

## 1.2. Failure Modes of Direct Generative AI in Structural Mechanics

Empirical evaluations of foundation models on civil and structural engineering tasks have exposed three primary failure modes:

### 1.2.1. Mathematical Hallucination and Absence of Physical Conservation
LLMs are autoregressive token predictors trained to optimize statistical likelihood over natural language corpora; they possess no internal computational mechanics solver and no concept of physical laws. Recent benchmarking studies demonstrate that when prompted to perform structural calculations—such as indeterminate beam reactions, stiffness matrix inversions, moment distribution, or dynamic response integration—frontier models exhibit mathematical error and hallucination rates exceeding 60% (Fuchs et al., 2023; Prieto et al., 2024). Even minor numerical inaccuracies in internal force evaluation ($\Delta M, \Delta V$) compromise structural safety, rendering direct generation fundamentally unsuitable for engineering analysis.

### 1.2.2. Inability to Enforce Prescriptive Building Code Provisions
Structural engineering design is strictly bounded by legal and regulatory frameworks, such as ASCE 7-16/22 for environmental and occupancy loads, and ACI 318-19/25 for reinforced concrete design. Direct LLM prompts fail to maintain fidelity to complex, conditionally branching code logic, such as:
- Tributary area live load reduction formulas based on influence area $K_{LL} A_T$;
- Equivalent Lateral Force (ELF) seismic base shear equations ($V = C_s W$) and upper/lower period bounds ($T_a, C_u T_a$);
- Factored LRFD and ASD load combination envelopes ($1.2D + 1.6L, 1.2D + 1.0E + 1.0L$);
- Non-linear axial-flexural ($P\text{--}M$) interaction boundaries and tension-controlled strength reduction factors ($\phi$).

When prompted directly, LLMs frequently invent non-existent code clauses, omit governing load combinations, or apply obsolete equation factors (Zhang et al., 2024).

### 1.2.3. Brittleness of Script-Generation Paradigms ("LLM-as-a-Coder")
To circumvent calculation hallucinations, several researchers have explored prompting LLMs to synthesize executable Python, MATLAB, or OpenSees scripts (Lu et al., 2024; Zheng et al., 2024). While this shifts computation to an external Python interpreter, the paradigm remains fragile:
- Generated scripts regularly crash due to deprecated library syntax, invalid coordinate transformations, unconstrained degrees of freedom (singular stiffness matrices), or dimensional unit inconsistencies;
- Standard code-generation workflows lack closed-loop sensory feedback: if the script terminates with an error or produces a structure with $\text{DCR} > 1.0$, the language model has no programmatic mechanism to inspect internal memory structures, diagnose the governing failure mode, or iteratively converge upon a compliant design.

---

## 1.3. Literature Review: From Point Solutions to Neuro-Symbolic Agents

To overcome these foundational limitations, contemporary research has converged toward **Neuro-Symbolic Agentic Architectures**, wherein the probabilistic reasoning of an LLM is tightly coupled with deterministic, symbolic computational engines.

```
+--------------------------------------------------------------------------------------------------+
|                                  EVOLUTION OF AI IN STRUCTURAL DESIGN                            |
|                                                                                                  |
|   1. Direct LLM Prompting       2. Script-Generation          3. Neuro-Symbolic Multi-Tool       |
|      (Zero/Few-Shot)               (LLM writes Python/FEM)       Agentic Architecture (This Work)|
|   +-----------------------+     +-----------------------+     +--------------------------------+ |
|   | Human -> Prompt       |     | Human -> Prompt       |     | Human -> Text / Floor Plan     | |
|   |         v             |     |         v             |     |         v                      | |
|   | [LLM guesses numbers] |     | [LLM writes script]   |     | [Neural Cognitive Controller]  | |
|   |         v             |     |         v             |     |         v                      | |
|   | High Hallucinations   |     | Script Crashes /      |     | [Deterministic Tool Engines]   | |
|   | & Unsafe Designs      |     | No Self-Healing Loop  |     |   (Load, FEM, Code, CAD, CAE)  | |
|   +-----------------------+     +-----------------------+     |         v                      | |
|                                                               | [Self-Healing Reflection Loop] | |
|                                                               |   (Autonomous Convergence)     | |
|                                                               +--------------------------------+ |
+--------------------------------------------------------------------------------------------------+
```

### 1.3.1. Tool-Augmented LLMs and Standardized Agent Protocols
The introduction of function calling, tool use, and cognitive reasoning frameworks such as ReAct (Reasoning and Acting) (Yao et al., 2023) and Reflexion (Shinn et al., 2023) demonstrated that foundation models could act as supervisors over external APIs. In the AEC literature, Wu et al. (2024) demonstrated tool-augmented generative agents for computational mechanics simulations, reporting substantial improvements in task execution compared to raw prompting. 

More recently, Elbasani et al. (2026) applied the Model Context Protocol (MCP) to automate the interface between computer-aided design and structural analysis tools. Their findings showed that providing structured, schema-validated tool definitions enables LLMs to assemble multi-step simulation pipelines without hallucinating intermediate numerical results. Concurrently, Liang et al. (2024) introduced MASSE (Multi-Agent System for Structural Engineering), decomposing structural tasks across specialized sub-agents. However, existing multi-agent systems remain predominantly conceptual or restricted to idealized 2D frames, lacking integrated multi-dimensional dynamic analysis, standardized reinforced concrete detailing, and production-ready CAD generation.

### 1.3.2. Structural Ontologies, Open Data Schemas, and Commercial CAE Interoperability
A persistent barrier to agentic engineering is the absence of an open, lightweight data exchange standard tailored specifically to analytical wireframes and code-checking states. While the Industry Foundation Classes (IFC) under the OpenBIM initiative provide rich geometric and facility-management semantics (Sacks et al., 2018; Bilal et al., 2023), IFC is notoriously verbose, computationally heavy, and poorly suited for rapid, in-memory state manipulation during high-frequency agentic optimization cycles.

Commercial structural software vendors (e.g., Computers and Structures, Inc. [CSI] with SAP2000 and ETABS) utilize proprietary text-based exchange formats (`.s2k`, `.e2k`) or COM/OAPI desktop interfaces. When AI researchers couple LLMs directly to proprietary software APIs, the resulting implementations suffer from closed-ecosystem lock-in, non-reproducibility, platform dependency, and high licensing costs. Consequently, an urgent scientific need exists for a lightweight, schema-validated neutral structural language that bridges verified open-source finite element solvers with commercial production platforms.

### 1.3.3. Multimodal Drawing Interpretation and Automated CAD Detailing
While text-prompted design is valuable, structural engineers rarely initiate projects from abstract text descriptions alone; they begin with architectural floor plans, grid layouts, and elevation drawings. Recent advances in Vision-Language Models have enabled the visual inspection of construction documentation (Lu et al., 2024). However, extracting structural geometry directly from raster pixel coordinates introduces scaling distortions and geometric discrepancies. A robust engineering pipeline requires semantic parameter extraction (identifying grid lines, written dimension strings, and structural callouts) coupled with programmatic drafting verification and interactive clarification for missing parameters (e.g., vertical story heights).

Furthermore, the design cycle cannot terminate at theoretical demand values or required steel reinforcement areas ($A_s$). Production engineering requires translation into construction drawings compliant with industry drafting conventions (stirrup spacing zones, longitudinal bar curtailments, bend hooks, and rebar schedules). To date, no published framework provides an end-to-end bridge connecting raw multimodal floor plans directly to production-grade DXF CAD drawings through verified structural analysis and design.

---

## 1.4. Research Gaps

A critical examination of the literature reveals five fundamental gaps in current computational structural engineering and AI research:

1. **The Arithmetic Hallucination Gap**: Few published works enforce a strict architectural boundary that completely prohibits the LLM from computing engineering values, leading to persistent safety risks in AI-assisted workflows.
2. **The Dimensionality and Dynamics Gap**: Most agentic structural design frameworks are limited to static 1D beams or 2D trusses; they do not support 3D space frames with biaxial bending, torsion, geometric buckling, modal eigenvalue analysis, and dynamic earthquake time-history integration (e.g., Newmark-Beta direct integration of real accelerograms).
3. **The Building Code Integrity Gap**: Prior frameworks frequently apply arbitrary load factors or simplified single-load cases, bypassing formal building code procedures for occupancy live load reduction, tributary area line load mapping, ASCE 7 seismic ELF distributions, and complete factored LRFD combination matrices.
4. **The Closed-Loop Self-Healing Gap**: Existing systems lack an autonomous reflection loop that observes governing element failure modes ($\text{DCR} > 1.0$), reasons over section modification heuristics, and converges iteratively on code-compliant, cost-effective structural dimensions without human intervention.
5. **The Full-Lifecycle CAD and CAE Interoperability Gap**: Current research stops at numerical analysis or table output, failing to bridge the upstream multimodal architectural plan ingestion with downstream production CAD detailing (`.dxf`) and bi-directional commercial software exchange (SAP2000 / ETABS).

Table 1 summarizes these gaps, comparing representative state-of-the-art frameworks against the system presented in this study.

**Table 1**: Comparative matrix of AI and automated structural design frameworks.

| Evaluation Dimension | Direct LLM (Zero-Shot) | Code-Gen LLM (Scripting) | MASSE (Liang et al., 2024) | MCP-Structural (Elbasani et al., 2026) | Proposed Neuro-Symbolic Ecosystem |
|:---|:---:|:---:|:---:|:---:|:---:|
| **Zero Calculation Hallucination** | ❌ (High) | ⚠️ (Syntax/Math Bugs) | ✅ | ✅ | **✅ (Strict Separation)** |
| **Solver Scope** | None | 1D / 2D Scripts | 2D / Simplified 3D | Commercial CAE Link | **2D & 3D FEA + Timoshenko + Buckling** |
| **Dynamic & Seismic Time-History** | ❌ | ❌ | ❌ | ❌ | **✅ (Newmark-Beta / El Centro / RSA)** |
| **Code Loading Engine** | ❌ | ⚠️ (Hardcoded) | ⚠️ (Rule Tables) | ❌ | **✅ (ASCE 7-16/22 ELF, Wind, LRFD)** |
| **Codified RC Design Engine** | ❌ | ⚠️ (Textbook Eq.) | ⚠️ (Simplified) | ❌ | **✅ (ACI 318-19 & 318-25 P-M Curves)** |
| **Autonomous Self-Healing Loop** | ❌ | ❌ | ⚠️ (Partial) | ❌ | **✅ (DCR-Guided Reflection Machine)** |
| **Multimodal Floor Plan Ingestion** | ⚠️ (Uncalibrated) | ❌ | ❌ | ❌ | **✅ (VLM Grid Parsing + Clarification)** |
| **Commercial CAE Bi-directional Link**| ❌ | ❌ | ❌ | ⚠️ (Unidirectional) | **✅ (SAP2000 .s2k & ETABS .e2k)** |
| **Production CAD Detailing** | ❌ | ❌ | ❌ | ❌ | **✅ (Native AutoCAD DXF Generation)** |

---

## 1.5. Proposed Approach ("What is Done Here")

To address these scientific and technological gaps, this study presents a comprehensive, open-source **Neuro-Symbolic Agentic Framework for Structural Engineering**. The core innovation lies in the strict separation of **neural cognitive orchestration** from **deterministic symbolic execution**, mediated by a vendor-neutral, Pydantic-validated data exchange schema ([`struct_core`](file:///c:/Users/lenovo/OneDrive%20-%20University%20of%20Nevada,%20Reno/extra%20research/structural_engineering/struct_core)).

The ecosystem comprises eight modular, decoupled subsystems:
1. **Schema and Validation Layer ([`struct_core`](file:///c:/Users/lenovo/OneDrive%20-%20University%20of%20Nevada,%20Reno/extra%20research/structural_engineering/struct_core))**: A centralized data language defining immutable, strongly-typed Pydantic v2 data models for structural geometry, materials, boundary conditions, internal force envelopes, code checks, and rebar detailing.
2. **Code Loading Subsystem ([`struct_load`](file:///c:/Users/lenovo/OneDrive%20-%20University%20of%20Nevada,%20Reno/extra%20research/structural_engineering/struct_load))**: A building code engine that automates ASCE 7-16 and ASCE 7-22 provisions, including occupancy-based live loads, continuous self-weight computation, surface-to-line tributary area distributions, lateral wind MWFRS pressure distributions, Equivalent Lateral Force (ELF) seismic distributions, and factored LRFD/ASD load combinations.
3. **Multi-Dimensional Finite Element Solvers ([`fem2d`](file:///c:/Users/lenovo/OneDrive%20-%20University%20of%20Nevada,%20Reno/extra%20research/structural_engineering/fem2d) and [`fem3d`](file:///c:/Users/lenovo/OneDrive%20-%20University%20of%20Nevada,%20Reno/extra%20research/structural_engineering/fem3d))**: Verified Python-based direct stiffness solvers supporting 2D plane frames (3 DOF/node) and general 3D space frames (6 DOF/node), incorporating Euler-Bernoulli and Timoshenko beam-column theory, member releases/hinges, linear elastic buckling ($K_g$ eigenvalue analysis), and corotational geometric non-linearity.
4. **Structural Dynamics Engine ([`structdyn`](file:///c:/Users/lenovo/OneDrive%20-%20University%20of%20Nevada,%20Reno/extra%20research/structural_engineering/structdyn))**: A dynamic analysis package providing modal eigenvalue analysis, response spectrum analysis (RSA) with SRSS modal combination, and direct numerical time integration (Newmark-Beta and Central Difference) under real multi-directional ground motion accelerograms (e.g., 1940 El Centro), coupled with peak dynamic force enveloping.
5. **Codified Reinforced Concrete Design Engine ([`aci318`](file:///c:/Users/lenovo/OneDrive%20-%20University%20of%20Nevada,%20Reno/extra%20research/structural_engineering/aci318))**: A modular design library enforcing ACI 318-19 and ACI 318-25 provisions for flexure, one-way shear, punching shear, and column axial-flexural ($P\text{--}M$) interaction diagrams, alongside an automated section search optimizer.
6. **Production CAD Detailing Subsystem ([`struct_draw`](file:///c:/Users/lenovo/OneDrive%20-%20University%20of%20Nevada,%20Reno/extra%20research/structural_engineering/struct_draw))**: A CAD engine generating production-ready AutoCAD DXF drawings with native multileaders, rebar callouts, stirrup schedules, and section views directly from ACI 318 design results.
7. **Commercial CAE Interoperability Link ([`struct_link`](file:///c:/Users/lenovo/OneDrive%20-%20University%20of%20Nevada,%20Reno/extra%20research/structural_engineering/struct_link))**: A bi-directional translation engine supporting full round-trip model synchronization with CSI SAP2000 (`.s2k`, `.$2k`) and ETABS (`.e2k`, `.$et`) files.
8. **Cognitive Agent Orchestrator ([`struct_agent`](file:///c:/Users/lenovo/OneDrive%20-%20University%20of%20Nevada,%20Reno/extra%20research/structural_engineering/struct_agent))**: An autonomous multi-turn reasoning engine that wraps the entire ecosystem in OpenAI-compatible JSON function-calling schemas. It features a multimodal vision pipeline (`struct_agent.vision`) that extracts structural grids from floor plans (PDF, PNG, JPG), enforces multi-turn clarification for underspecified parameters (e.g., story heights), and drives an autonomous **self-healing reflection loop** to iteratively resize members until all code constraints ($\text{DCR} \le 1.0$) are satisfied.
9. **Interactive Visual Studio ([`struct_gui`](file:///c:/Users/lenovo/OneDrive%20-%20University%20of%20Nevada,%20Reno/extra%20research/structural_engineering/struct_gui))**: A desktop GUI built on PySide6 and PyVista (VTK) providing real-time 3D deformed mesh visualization, DCR color heatmaps, modal vibration animations, and an interactive LLM copilot panel.

---

## 1.6. Objectives and Scope of this Study

The overarching objective of this research is to formulate, implement, and empirically validate a neuro-symbolic agentic framework that autonomously executes the complete structural engineering lifecycle from ambiguous human intent to code-compliant production deliverables without calculation hallucinations. 

Specific research objectives are:
1. **Formulate and Formalize the Neuro-Symbolic Agentic Architecture**: Define the mathematical separation between probabilistic language planning and deterministic structural mechanics, mediated by the [`struct_core`](file:///c:/Users/lenovo/OneDrive%20-%20University%20of%20Nevada,%20Reno/extra%20research/structural_engineering/struct_core) schema and a finite state machine tracking lifecycle stages from `MODEL_CREATED` to `DRAWINGS_GENERATED`.
2. **Empirically Quantify Hallucination Elimination (H1)**: Benchmark the neuro-symbolic agent against raw zero-shot LLMs and code-generating LLMs across fundamental and indeterminate structural mechanics problems, establishing that tool grounding guarantees 0% calculation hallucinations.
3. **Validate the Self-Healing Reflection Mechanism (H2)**: Evaluate the efficiency and convergence properties of the DCR-guided reflection loop across 24 benchmark cases, tracking iteration count, failure-mode recovery rate, and material economy relative to expert human designs.
4. **Demonstrate Full-Lifecycle Multimodal and Commercial Interoperability (H3)**: Validate the end-to-end pipeline on complex practical case studies, including multimodal floor plan ingestion, dynamic earthquake time-history analysis under the 1940 El Centro ground motion, bidirectional CSI ETABS/SAP2000 synchronization, and automated DXF CAD drawing generation.

---

## 1.7. Structure of the Manuscript

The remainder of this manuscript is organized into six core sections:
- **Section 2** provides a comprehensive literature review spanning large language models in structural engineering, tool-augmented scientific agents, multimodal computer vision for AEC drawing interpretation, and codified structural design automation.
- **Section 3** establishes the complete methodology, formalizing the ontology-grounded intermediate representation ([`struct_core`](file:///c:/Users/lenovo/OneDrive%20-%20University%20of%20Nevada,%20Reno/extra%20research/structural_engineering/struct_core)), the deterministic symbolic mechanics and design engines ([`struct_load`](file:///c:/Users/lenovo/OneDrive%20-%20University%20of%20Nevada,%20Reno/extra%20research/structural_engineering/struct_load), [`fem2d`](file:///c:/Users/lenovo/OneDrive%20-%20University%20of%20Nevada,%20Reno/extra%20research/structural_engineering/fem2d), [`fem3d`](file:///c:/Users/lenovo/OneDrive%20-%20University%20of%20Nevada,%20Reno/extra%20research/structural_engineering/fem3d), [`structdyn`](file:///c:/Users/lenovo/OneDrive%20-%20University%20of%20Nevada,%20Reno/extra%20research/structural_engineering/structdyn), [`aci318`](file:///c:/Users/lenovo/OneDrive%20-%20University%20of%20Nevada,%20Reno/extra%20research/structural_engineering/aci318), [`struct_draw`](file:///c:/Users/lenovo/OneDrive%20-%20University%20of%20Nevada,%20Reno/extra%20research/structural_engineering/struct_draw), [`struct_link`](file:///c:/Users/lenovo/OneDrive%20-%20University%20of%20Nevada,%20Reno/extra%20research/structural_engineering/struct_link)), and the neural cognitive orchestrator with closed-loop reflection ([`struct_agent`](file:///c:/Users/lenovo/OneDrive%20-%20University%20of%20Nevada,%20Reno/extra%20research/structural_engineering/struct_agent)).
- **Section 4** presents the experimental setup, detailing the standardized 24-case structural and seismic benchmark suite, comparative baselines, multi-model evaluation testbed (`gemini-3.8-flash`, `qwen3.5:9b`, `gpt-oss:120b-cloud`, `nemotron-3-ultra:cloud`), and quantitative evaluation metrics.
- **Section 5** presents the empirical results, including commercial CAE solver verification, baseline comparison for calculation hallucination elimination, ablation studies, self-healing convergence trajectories, volumetric material economy, and end-to-end multimodal case studies.
- **Section 6** discusses engineering boundary conditions, computational limitations, future research trajectories, and concluding remarks.
- Complete bibliographic citations are compiled in [`references.md`](file:///c:/Users/lenovo/OneDrive%20-%20University%20of%20Nevada,%20Reno/extra%20research/structural_engineering/research%20paper/manuscript/references.md).

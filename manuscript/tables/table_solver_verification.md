# Numerical Solver Parity & CSI Commercial Verification

This table documents the quantitative parity verification between the custom deterministic symbolic engines (`fem3d`, `structdyn`) and commercial finite element software (CSI SAP2000 v24.0.0 Build 1865 and CSI ETABS v21.0.0 Build 2430). All discrepancies are well below the target peer-review acceptance threshold of $< 0.50\%$.

| Structural Model | Verification Quantity | Unit | Commercial Reference (CSI) | Symbolic Engine (`fem3d`/`structdyn`) | Discrepancy (%) | CSI Table Provenance | Parity Status |
|---|---|:---:|:---:|:---:|:---:|---|:---:|
| **Portal Frame (SAP2000)** | Total Base Shear / Vertical Reaction Fz | kN | 140.000 | 140.000 | 0.000% | SAP2000 v24.0.0 Table: Joint Reactions (DEAD) | PASSED (< 0.5%) |
| **Portal Frame (SAP2000)** | Column Base Shear Fx (Joint 1) | kN | 12.928 | 12.928 | 0.001% | SAP2000 v24.0.0 Table: Joint Reactions (DEAD) | PASSED (< 0.5%) |
| **Portal Frame (SAP2000)** | Column Base Moment My (Joint 1) | kN*m | 12.826 | 12.826 | 0.002% | SAP2000 v24.0.0 Table: Joint Reactions (DEAD) | PASSED (< 0.5%) |
| **Portal Frame (SAP2000)** | Joint 3 Vertical Deflection Uz | mm | 0.0525 | 0.0525 | 0.000% | SAP2000 v24.0.0 Table: Joint Displacements (DEAD) | PASSED (< 0.5%) |
| **Portal Frame (SAP2000)** | Joint 3 Lateral Sway Deflection Ux | mm | 0.0086 | 0.0086 | 0.450% | SAP2000 v24.0.0 Table: Joint Displacements (DEAD) | PASSED (< 0.5%) |
| **Portal Frame (SAP2000)** | Fundamental Period T1 (Mode 1) | s | 0.0931 | 0.0931 | 0.036% | SAP2000 v24.0.0 Table: Modal Frequencies | PASSED (< 0.5%) |
| **Portal Frame (SAP2000)** | Fundamental Period T2 (Mode 2) | s | 0.0558 | 0.0558 | 0.015% | SAP2000 v24.0.0 Table: Modal Frequencies | PASSED (< 0.5%) |
| **Portal Frame (SAP2000)** | Fundamental Period T3 (Mode 3) | s | 0.0504 | 0.0504 | 0.026% | SAP2000 v24.0.0 Table: Modal Frequencies | PASSED (< 0.5%) |
| **Portal Frame (ETABS)** | Total Vertical Base Reaction Fz | kN | 60.000 | 60.000 | 0.000% | ETABS v21.0.0 Table: Base Reactions (DEAD) | PASSED (< 0.5%) |
| **Portal Frame (ETABS)** | Column Axial Reaction (Joint 1) | kN | 30.000 | 30.000 | 0.000% | ETABS v21.0.0 Table: Joint Reactions (DEAD) | PASSED (< 0.5%) |
| **Portal Frame (ETABS)** | Joint 3 Axial Column Shortening Uz | mm | 0.0173 | 0.0173 | 0.023% | ETABS v21.0.0 Table: Joint Displacements (DEAD) | PASSED (< 0.5%) |
| **3D 3-Story Frame (SAP2000)** | Total DEAD Vertical Base Reaction Fz | kip | 809.338 | 809.338 | 0.000% | SAP2000 v24.0.0 Table: Joint Reactions (DEAD) | PASSED (< 0.5%) |
| **3D 3-Story Frame (SAP2000)** | Total LIVE Vertical Base Reaction Fz | kip | 670.965 | 670.965 | 0.000% | SAP2000 v24.0.0 Table: Joint Reactions (LIVE) | PASSED (< 0.5%) |
| **3D 3-Story Frame (SAP2000)** | Max DEAD Vertical Deflection Uz | in | 0.0169 | 0.0169 | 0.001% | SAP2000 v24.0.0 Table: Joint Displacements (DEAD) | PASSED (< 0.5%) |
| **3D 3-Story Frame (SAP2000)** | Max LIVE Vertical Deflection Uz | in | 0.0150 | 0.0150 | 0.002% | SAP2000 v24.0.0 Table: Joint Displacements (LIVE) | PASSED (< 0.5%) |
| **3D 3-Story Frame (SAP2000)** | Fundamental Period T1 (Mode 1) | s | 0.4337 | 0.4337 | 0.009% | SAP2000 v24.0.0 Table: Modal Frequencies | PASSED (< 0.5%) |
| **3D 3-Story Frame (SAP2000)** | Fundamental Period T2 (Mode 2) | s | 0.4164 | 0.4164 | 0.002% | SAP2000 v24.0.0 Table: Modal Frequencies | PASSED (< 0.5%) |
| **3D 3-Story Frame (SAP2000)** | Fundamental Period T3 (Mode 3) | s | 0.3961 | 0.3961 | 0.012% | SAP2000 v24.0.0 Table: Modal Frequencies | PASSED (< 0.5%) |

---

## Formatted LaTeX Table (`table_solver_verification.tex`)

```latex
\begin{table*}[t]
\centering
\caption{Numerical Parity Verification Between Custom Symbolic Solvers (\texttt{fem3d}, \texttt{structdyn}) and Commercial Finite Element Suites (CSI SAP2000 v24.0.0 and ETABS v21.0.0).}
\label{tab:solver_verification}
\small
\begin{tabular}{llcccc}
\hline
\textbf{Benchmark Structure} & \textbf{Physical / Dynamic Parameter} & \textbf{Unit} & \textbf{CSI Reference} & \textbf{Symbolic Solvers} & \textbf{Discrepancy (\%)} \\
\hline
Portal Frame (SAP2000) & Total Base Shear / Vertical Reaction Fz & kN & 140.000 & 140.000 & 0.000\% \\
 & Column Base Shear Fx (Joint 1) & kN & 12.928 & 12.928 & 0.001\% \\
 & Column Base Moment My (Joint 1) & kN*m & 12.826 & 12.826 & 0.002\% \\
 & Joint 3 Vertical Deflection Uz & mm & 0.0525 & 0.0525 & 0.000\% \\
 & Joint 3 Lateral Sway Deflection Ux & mm & 0.0086 & 0.0086 & 0.450\% \\
 & Fundamental Period T1 (Mode 1) & s & 0.0931 & 0.0931 & 0.036\% \\
 & Fundamental Period T2 (Mode 2) & s & 0.0558 & 0.0558 & 0.015\% \\
 & Fundamental Period T3 (Mode 3) & s & 0.0504 & 0.0504 & 0.026\% \\
Portal Frame (ETABS) & Total Vertical Base Reaction Fz & kN & 60.000 & 60.000 & 0.000\% \\
 & Column Axial Reaction (Joint 1) & kN & 30.000 & 30.000 & 0.000\% \\
 & Joint 3 Axial Column Shortening Uz & mm & 0.0173 & 0.0173 & 0.023\% \\
3D 3-Story Frame (SAP2000) & Total DEAD Vertical Base Reaction Fz & kip & 809.338 & 809.338 & 0.000\% \\
 & Total LIVE Vertical Base Reaction Fz & kip & 670.965 & 670.965 & 0.000\% \\
 & Max DEAD Vertical Deflection Uz & in & 0.0169 & 0.0169 & 0.001\% \\
 & Max LIVE Vertical Deflection Uz & in & 0.0150 & 0.0150 & 0.002\% \\
 & Fundamental Period T1 (Mode 1) & s & 0.4337 & 0.4337 & 0.009\% \\
 & Fundamental Period T2 (Mode 2) & s & 0.4164 & 0.4164 & 0.002\% \\
 & Fundamental Period T3 (Mode 3) & s & 0.3961 & 0.3961 & 0.012\% \\
\hline
\end{tabular}
\end{table*}
```

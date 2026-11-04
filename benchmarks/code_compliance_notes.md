# Code-Compliance Notes: Gaps and Simplifications

What the design tools (`aci318` against ACI 318-25, `struct_load` against ASCE 7-22) do not implement, and where
they simplify. The manuscript (Sections 4.1 and 6.2) refers to this list. Every other check that the benchmark
relies on (member strength, Chapter 15 joints, the Chapter 18 requirements of IMF and SMF, slenderness by moment
magnification, story drift and stability) is implemented, with regression tests in its package
(`aci318/tests/test_code_compliance_318_25.py` and the `struct_load` and `struct_agent` test suites).

## Not implemented

- **Isolated footings under seismic uplift.** Footings are sized for the allowable soil pressure under the
  ASCE 7-22 §2.4 service combinations and designed for the factored reactions (ACI 318-25 R13.2.6.1), but the
  vertical load is the column reaction alone: the footing's own weight and the soil above it are not included. Under
  $(0.6 - 0.14 S_{DS})D - 0.7E$, perimeter columns of the seismic cases carry little axial load with a large base
  moment, and no isolated footing within the sizer's range keeps the resultant inside the base; the result is then
  reported as a failed footing with a nominal DCR (the 999 ksf overturning value divided by the allowable pressure,
  about 319 at 150 kPa). Combined footings, grade beams, and tension piles are not designed by the agent's tools.
  Footings are not scored by the benchmark.
- §18.7.3.3 (columns not designed as part of the lateral system, using the alternative to strong-column/weak-beam)
  is not offered.
- Circular columns get member design and slenderness, but no Chapter 18 or joint checks.
- Response-history envelopes (`run_time_history`) get no second-order magnification or drift checks.
- An imported CSI model (C02) has no seismic system, so Chapter 18 is not applied; Chapter 15 joints and slenderness
  are.

## Simplifications (conservative)

- Non-square columns use the smaller dimension and the weaker axis for joint and Chapter 18 checks.
- $M_{2,\min}$ is applied about both axes at once.
- The stability index $Q$ uses the largest $\Sigma P_u$ among the lateral combinations.
- The column $P_u$ range covers all combinations.
- IMF and OMF capacity-design shear uses option (a) ($M_n$ at both ends).
- $P_x = 1.0D + 0.4L$ covers the gravity load of §12.8.6.1.
- Beams assume equal top and bottom steel for $M_{pr}$ and the joint forces.
- A record-spectrum response spectrum analysis (B06) has no $S_{DS}$, so it is not scaled to the ELF base shear.
- Column bar layouts keep each face's bar spacing within 14 in, assuming every bar is tied by a hoop leg or crosstie.
  The 8 in limit of §18.7.5.2(f), for $P_u > 0.3 A_g f'_c$, is checked but not designed for.
- Column bars are not increased for the column capacity-design shear (§18.7.6.1), which more column steel raises;
  the shear is checked with the designed bars.
- Deflections are not computed; design cases use the minimum beam depth ℓ/18.5 of ACI 318-25 Table 9.3.1.1.

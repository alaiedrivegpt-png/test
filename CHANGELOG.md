# Version history

## v1 reconstructed revision on 19 November 2026

- Reconstructed the project from the conversation and surviving v0 Google Doc. Original v0 archive bytes were not recovered; its quoted SHA is retained only as historical provenance.
- Regenerated native FreeCAD documents and STEP solids. Reconstructed the four triangular sacrificial ribs explicitly; their exact v0 CAD definition was unavailable.
- Added independent CadQuery/Open CASCADE geometry and fit tests on delivered solids, including both-end assembly, clearance, interference and hardware checks.
- Added a single local/hosted CI entry point, deliberate-negative tests, full saved run logs, structured requirement verdicts and actionable next-iteration feedback.
- Added AI_REFERENCE.md and an explicit R01–R19 requirement map.
- Refetched source evidence and retained historical quote dates. Added actual washer OD/ID tolerance bounds to hardware checks.
- Recomputed calculations and actual Gmsh/CalculiX analyses for v1; previous v0 numerical values are not substituted for fresh execution.
- Losslessly compressed finest-mesh raw solver fields and retained all inputs, logs and coarse convergence metrics. Regenerable coarse field files are explicitly listed as omitted; the full CI mode regenerates every configured solve.

## v0 historical record

The conversation recorded 243 PASS, 2 FAIL and 12 BLOCKED at delivery. Its numerical failures were principal-stress convergence (14.44% versus 10%) and beam mesh volume error (0.503225% versus 0.5%). These are historical results; consult the v1 CI summary for the reconstructed model's current result.

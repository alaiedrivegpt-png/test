# AI reference for beam wall mount v1

## Purpose and origin

Design a purchased **400 mm beam** held by **two 3D printed press-fit brackets**, bolted to opposite walls, for a **10 N quasistatic force plus selfweight**. This v1 is reconstructed from the chat and saved v0 report. The original v0 code, CAD and FEM outputs were unavailable; do not claim byte-for-byte continuity or recycle old numbers as current results.

## Read first

1. `requirement.md`: R01–R19 and acceptance criteria; its SHA is frozen.
2. `config/design.json`: authoritative dimensions, materials, loads and mesh settings.
3. `results/ci_summary.json`: current execution and engineering verdicts.
4. `results/next_iteration.md`: exact failures, blocked gates and next actions.
5. `logs/`: the full saved execution evidence, not just the summary.

## File map

| Folder or file | Role |
| --- | --- |
| `cad/`, `drawings/` | FreeCAD sources, STEP solids, fit coupons, geometry manifest and previews |
| `scripts/check_geometric_fit.py` | CadQuery plus Open CASCADE on the actual STEP files; both ends, clearance, intentional rib interference and hardware |
| `scripts/calculate.py` | Full analytical formulas and numerical substitutions |
| `mesh/`, `fem/` | Real Gmsh STL/meshes and losslessly compressed CalculiX evidence |
| `tests/`, `scripts/run_ci.py` | Independent mathematical tests, deliberate-negative tests, complete requirements runner |
| `results/` | CAD-fit measurements, calculations, 3D stresses, structured CI feedback and next-iteration instructions |
| `bom.csv`, `evidence/` | Purchase links, catalogue/material evidence and reconstruction provenance |
| `report/` | Full report plus verified native Google Doc URL |
| `config/physical_acceptance.json` | Real observations only; null means BLOCKED |

## Requirement coverage

- R01, R07, R09, R17–R19: package, report, BOM, logs and provenance checks in CI.
- R02–R04, R11, R15: FreeCAD validation and actual CadQuery/OCC fit checks.
- R05, R08, R10, R12–R14: calculations, actual FEM, source hashes, stress/mesh/convergence gates and full requirements mapping.
- R16: executed unit tests and deliberate failures for collisions, misplaced parts, missing STL, stale results and unavailable/failed executables.
- Physical portions of R02–R06 and current procurement in R09 stay BLOCKED until authentic records exist.

## Commands and decisions

```bash
python scripts/run_ci.py --mode selftest
python scripts/run_ci.py --mode audit
python scripts/run_ci.py --mode full
# Optional: reproduce two saved-FEM integrity fault injections in isolated copies
python scripts/check_fem_audit_integrity.py --root .
```

Exit 0 = selected mode passes; 1 = FAIL; 2 = BLOCKED; 3 = execution ERROR. **A functional test system is not a passing engineering design.** Read both fields. `selftest` never authorizes release. The final local run is authoritative; a hosted workflow file alone is not a completed hosted CI run.

## Rules for the next iteration

- Keep the 400 mm beam separate from the 431.6 mm wall gap.
- Preserve the unmodified v1 archive; work in a new version directory.
- Change the actual design/model or complete missing evidence. Do not weaken thresholds or edit a result to PASS.
- Separate unwanted core collision from intentional crush-rib interference. CAD fit alone cannot establish printed retention.
- Never invent material certificates, wall condition, torque, print strength or load-test observations.
- On a code/config/CAD change, rerun every affected stage and rebuild report/evidence hashes.
- For release status and next actions, read the latest saved CI summary; do not infer status from this static guide.

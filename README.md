# Beam wall mount v1

This project reconstructs the 400 mm purchased aluminum beam and two printed press-fit wall brackets from the conversation and the surviving v0 engineering report. The original v0 CAD, scripts and solver files were unavailable. **These are newly generated v1 artifacts, not recovered v0 files.** The source report and reconstruction record are retained in `evidence/`.

Start with `AI_REFERENCE.md`, `requirement.md`, and `results/ci_summary.json`. The latest engineering decision and concrete next actions are in `results/next_iteration.md`. Passing software tests does not establish that a manufactured bracket, press fit or wall installation can carry the required load.

## Design

- Beam: Online Metals 23437, 6061-T6 aluminum square tube, finished to 400 +/-0.5 mm.
- Nominal section: 38.1 mm outside, 3.175 mm flat wall, 31.75 mm opening; outer corner radius 3.175 mm and inner radius 1.5748 mm.
- Brackets: Prusament PETG, 60 x 150 mm wall plate, 7.8 mm thickness at bolts and 13.8 mm at the reinforced center, 2 mm root fillet.
- Plug: 31.55 mm chamfered structural core, 30 mm engagement, 2 mm root relief. Reconstructed sacrificial ribs reach a 31.85 mm envelope.
- Nominal wall bearing-face spacing: **431.6 mm**. The 400 mm requirement applies to the beam length.
- Anchors: two fischer 564572 M6 anchors per bracket, four steel sleeves and four large retention washers. Solid C20/25 concrete is an assumption to verify physically.

The service-load scope is a quasistatic 10 N force in any direction and at any span station, over at least a 10 x 10 mm footprint, plus selfweight. Aluminum and PETG use material screening factor three. No assembly-wide certified safety factor is claimed.

## Project layout

| Path | Purpose |
| --- | --- |
| `requirement.md`, `frozen_requirements.sha256` | Reconstructed, extended v1 requirements and frozen checksum |
| `AI_REFERENCE.md` | Short guide for another AI or engineer |
| `config/design.json` | Authoritative dimensions, loads, material inputs and unchanged numerical acceptance limits |
| `config/physical_acceptance.json` | Actual observation records; null means not qualified |
| `cad/` | Native FreeCAD documents, STEP exports, fit coupons and geometry provenance |
| `drawings/` | Assembly and bracket illustrations generated from actual CAD |
| `mesh/` | Gmsh-generated printable STL and volume mesh evidence |
| `fem/` | All CalculiX inputs/logs and per-mesh numerical evidence; complete raw fields for the finest meshes are losslessly compressed |
| `bom.csv` | Exact catalogue IDs, quantities, prices, currencies, purchase links and notes |
| `evidence/` | Refetched supplier evidence, source hashes, retained v0 report and reconstruction provenance |
| `manufacturing/PRINT_AND_ASSEMBLY.md` | Printing, fit selection, wall installation and physical qualification procedure |
| `report/` | v1 engineering report, native Google Doc receipt and offline copies |
| `scripts/check_geometric_fit.py` | Independent CadQuery/Open CASCADE checks on the actual STEP files |
| `scripts/calculate.py`, `scripts/run_fem.py` | Executable hand calculations and actual Gmsh/CalculiX analysis |
| `scripts/render_fem.py` | Reproducible figure postprocessing from the retained actual stress field; included after the solves in full CI |
| `scripts/run_ci.py`, `.github/workflows/ci.yml` | Shared local/hosted CI command and workflow |
| `tests/` | Independent mathematics tests, geometric fault injections and CI failure controls |
| `logs/ci_<run_id>.log` | Separate full CI execution log: commands, versions, timestamps, stdout/stderr and exit codes |
| `results/geometric_fit.json` | Measured CAD fit quantities, criteria and next actions |
| `results/ci_summary.json` | Latest complete structured requirements and execution verdict |
| `results/requirement_matrix.md` | Requirement-by-requirement status |
| `results/next_iteration.md` | Actionable failures, blocked qualifications and evidence paths |
| `results/stress_viewer.html` | Offline 3D stress-field viewer |
| `MANIFEST.sha256` | Frozen static-file integrity manifest |

## Run the CI

Use Python 3.12. Install FreeCAD 1.0 separately; the native validation stage uses `FREECAD_PYTHON` or `/usr/bin/python3`. Install the tested Python dependencies in a virtual environment:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock

# Execute the unit tests and deliberate-negative controls only
.venv/bin/python scripts/run_ci.py --mode selftest

# Execute CAD validation, fresh calculations and actual OCC fit checks;
# audit retained Gmsh/CalculiX results and every requirement
.venv/bin/python scripts/run_ci.py --mode audit

# Recompute the numerical models and actually rerun CalculiX
.venv/bin/python scripts/run_ci.py --mode full
```

Every mode saves a separate log. `selftest` writes `results/selftest_summary.json` and does not evaluate engineering release. Other modes write `results/ci_summary.json`, `results/requirement_matrix.md` and `results/next_iteration.md`. The hosted workflow uploads logs and results even when engineering checks fail. A local execution is recorded as local; no hosted GitHub run is claimed unless one actually occurs.

| Exit code | Meaning |
| --- | --- |
| 0 | All checks in the selected mode pass; selftest alone is not engineering acceptance |
| 1 | At least one engineering or artifact check fails |
| 2 | No failures, but physical qualification remains blocked |
| 3 | Required execution could not be completed or evidence is stale/malformed |

`test_system_functional: true` means the tools, meaningful tests, failure controls and result readers completed as intended. Read `engineering_release` and `project_complete` separately. A correctly functioning CI system can correctly report FAIL or BLOCKED for this design.

The fit test imports delivered STEP files through CadQuery and uses Open CASCADE operations. It tests the structural core and fit ribs separately, both ends and insertion samples, dimensional tolerance cases and hardware clearances. Intentional rib interference is not silently discarded as a collision, and it is not proof of insertion force or retention. Actual measured openings and print qualification remain mandatory.

To keep the archive practical to download, full raw stress/displacement fields are retained for the finest beam and bracket meshes. Coarser meshes retain all inputs, solver logs, reaction/quality data and computed convergence metrics; their large regenerable field files are omitted and listed explicitly in the FEM retention record. Audit mode validates this recorded evidence; full mode regenerates every configured solve. The numerical mesh study and acceptance thresholds are not reduced to shrink the ZIP.

## Rebuild and version

```bash
/usr/bin/python3 scripts/build_cad.py --root .
.venv/bin/python scripts/build_bom.py
.venv/bin/python scripts/run_ci.py --mode full
```

Any design or source change can invalidate downstream evidence. Fix the actual input/model or complete the real test, then regenerate its dependent files. Never lower acceptance limits to conceal a failing result. Make a new version directory for future changes.

For packaging, complete the report and native Google Doc receipt first, then run:

```bash
python3 scripts/package_project.py --freeze --manifest-only
.venv/bin/python scripts/run_ci.py --mode audit
python3 scripts/package_project.py --freeze
python3 scripts/package_project.py --verify
```

The static manifest excludes run logs and mutable JSON/Markdown/text under `results/`, except the preserved executed-run `fem_summary.json`. Mutable records carry their own source hashes and the CI regenerates or validates them. The manifest includes CAD, code, supplier evidence, retained raw solver files, the executed FEM summary, report files and static figures. ZIP CRC verification checks every archived file. A full recomputation verifies the original static manifest before deliberately regenerating solver outputs; refreeze a new snapshot before redistributing those outputs.

## Report, costs and limitations

The native v1 report URL is in `report/google_doc.json`. The offline report explains formulas, assumptions, finite-element boundary conditions and the current numerical/fit decision. Source material for v0 is stored as historical evidence only.

The native report was created from a copy of the source Google Doc to preserve its 22 editable equation objects, then updated with the complete v1 text, tables and figures. `report/native_report_plan.json` records those ordered changes, and `report/google_doc_readback.json` records the actual final native structure. `python scripts/build_native_report_plan.py` regenerates the local plan using the included sanitized source readback; applying it to Google Docs requires an authenticated connector and fresh document indexes. The verified native export is also included as `report/google_doc_export.pdf`.

The BOM quotes are explicitly dated 17 November 2026 unless a row says otherwise. USD, EUR and GBP remain separate, and minimum-order cash differs from material consumed. Shipping, applicable taxes, labor, tools and print waste are excluded. Do not interpret an archived price or catalogue page as confirmation of current stock.

Required physical evidence includes printed-process strength, measured tube openings, fit/retention, actual wall substrate and anchor installation, sleeve projection, proof loading and sustained/environmental loading. Do not build a safety-critical installation from this screening package without completing those requirements.

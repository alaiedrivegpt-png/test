# Beam wall mount v1 requirements

This is a **reconstructed and extended baseline**, based on the user's original message, subsequent instructions and the retained v0 Google Doc. The exact original requirement.md bytes were not recovered. Do not describe this as a byte-identical continuation of v0. Freeze this file by SHA-256 after the v1 revision is assembled.

## Required deliverables and acceptance

| ID | Requirement | Evidence and acceptance |
| --- | --- | --- |
| R01 | Each version is a self-contained ZIP with frozen requirements and a layout guide. | All project inputs, evidence, native CAD, scripts and results included; manifest and ZIP integrity verified. Engineering software is an external runtime dependency. |
| R02 | Purchased beam is 40 cm long. | CAD and design length 400 mm; actual finished length 400 +/-0.5 mm remains a physical measurement gate. |
| R03 | Two printed end brackets press fit into the beam. | Actual delivered solids checked independently by CadQuery/Open CASCADE on both ends; no prohibited core collision; intended sacrificial rib interference quantified separately; real insertion/retention requires measured tube openings and print qualification. |
| R04 | Brackets have bolt mounts and attach to two walls. | Mount geometry, sleeve/washer stack and conditional anchor calculations checked; actual substrate and anchor installation qualified physically. |
| R05 | Assembly must not fail under 10 N. | Quasistatic force in any direction/any station with >=10 x 10 mm contact footprint plus selfweight. Material screening factor 3 for aluminum/PETG only; 1 mm displacement screening target. Strength, geometry and convergence must each pass. Physical load, creep, fit and installation qualification remain mandatory. |
| R06 | Purchased beam has exact catalogue, cross section and material properties with stored evidence. | Online Metals 23437 and original/refetched supplier evidence, source URLs, dates, hashes and assumptions. Actual material lot certificate remains outstanding. |
| R07 | Engineering report is in Google Docs. | Native v1 Google Doc, verified readback and offline report copies. Retain v0 source report separately. |
| R08 | Full calculations with formulas demonstrate conditional compliance. | Executable Python, units, substitutions, assumptions, independent tests and computed results. Failures cannot be hidden by prose. |
| R09 | BOM CSV includes parts, numbers, cost, external purchase links and notes. | Every purchased item accounted for; historical versus current quotes clearly identified; currencies and minimum orders separate. |
| R10 | FEM shows stresses in 3D. | Actual executed CalculiX results for reconstructed v1 geometry with figures and offline viewer; v0 values cannot masquerade as v1 results. |
| R11 | FreeCAD is used for native bracket CAD. | Rebuildable generator and valid native FCStd documents plus STEP exports. |
| R12 | Gmsh generates printable STL files. | Executed Gmsh meshing, STL files, versions, input/output hashes and mesh checks. |
| R13 | CalculiX performs FEM. | Real executable invocation, input decks, successful solve logs, raw results, force balance, mesh-quality and convergence checks. |
| R14 | Python automatically audits every requirement and returns actionable pass/fail feedback. | Requirement-to-check mapping; explicit PASS, FAIL, BLOCKED and ERROR; missing/skipped/stale mandatory stages cannot pass. |
| R15 | CadQuery plus Open CASCADE tests geometric fit. | Import delivered STEP geometry; validity, dimensions, assembly, both-end collisions, clearance, insertion samples, intentional ribs, hardware and tolerance checks, with engine versions and provenance. |
| R16 | CI is functional and its checks actually test requirements. | One local/hosted entry point; executed positive and deliberate-negative tests for geometry, missing artifacts, stale results and solver errors. Hosted workflow execution is not claimed without a real hosted run. |
| R17 | CI logs and next-iteration feedback are separate saved files and included in layout/docs. | logs/ci_<run_id>.log captures commands, times, versions, stdout/stderr and exit status; results/ci_summary.json and results/next_iteration.md contain evidence and concrete actions. |
| R18 | Simple AI reference file explains layout and requirements. | AI_REFERENCE.md names authoritative inputs, requirement mapping, run commands, current decision and rules for preserving evidence/thresholds. |
| R19 | Reconstruction provenance is explicit. | Source report and chat reconstruction note retained; newly generated CAD, calculations and solver results identified as v1; unrecovered v0 results are historical only. |

## Numerical gates

- Aluminum stress reference: 240 MPa; PETG screening reference: 14 MPa from a typical interlayer test, not a certified print allowable. Divide by 3 for material screens.
- Last-two-mesh stress change <=10%; displacement change <=5%; no stress exclusion to manufacture convergence.
- Beam mesh volume error versus exact CAD <=0.5%; positive element Jacobians; force and moment residuals <=0.5%.
- Global beam displacement compared with the comparable Euler section measure within 15%; local indentation reported separately.
- Actual dimensional/print fit, anchor preload, sleeve projection >=0.1 mm, physical proof and sustained/environmental loading remain BLOCKED without authentic measurements.
- Source price excerpts from v0 dated 17 November 2026 are historical quotes, not refreshed offers, unless independently rechecked.
- A functioning test suite can correctly return an engineering FAIL. Never weaken thresholds or fill missing physical records with simulated PASS.

## Frozen version policy

Rebuild and record the v1 artifacts, run the CI and create the final archive. Later changes belong in a new version. Hashes bind geometry, analysis inputs, results and evidence. Mutable run logs and latest summaries are excluded from the static manifest and each records its source hashes.

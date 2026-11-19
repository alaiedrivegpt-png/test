# Saved execution logs

The authoritative release audit is the run named by `results/ci_summary.json`.
That summary records the log filename, its SHA-256, actual commands, tool
versions, source hashes, exit code and requirement-level decisions.

Earlier development runs are retained intentionally. Some captured missing
artifacts, a geometry-check association defect that was subsequently repaired,
or source edits while a long FEM run was active. Their failures remain in the
record; they are not the final release verdict.

The complete FEM sweep and the final stable audit have different roles. The
sweep actually executes all configured CalculiX jobs. Audit mode reruns the
current unit tests, FreeCAD validation, calculations and CadQuery/Open CASCADE
geometry checks, then reparses the retained fine-mesh solver fields and checks
the protected evidence for all mesh levels. It does not claim to rerun every
solver job. `fem/` retains individual solver logs and inputs.

`fem_integrity_negative_controls.log` records deliberate changes in isolated
temporary copies and the audit's rejection of those changes. It never modifies
the delivered solver evidence.

Each later CI invocation creates a new timestamped log. `selftest` updates only
the test-system summary; it does not overwrite the full engineering decision.

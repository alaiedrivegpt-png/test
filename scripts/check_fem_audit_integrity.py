"""Isolated negative controls for the completed, real v1 FEM evidence.

The temporary projects share read-only inputs by symlink. Only their copied
top-level summary is altered; the released project and solver data are untouched.
Run only after a complete --force run has produced its final retention manifest.
"""
import argparse
import copy
import datetime
import hashlib
import importlib.util
import json
import tempfile
import time
from pathlib import Path


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    summary_path = root / "results/fem_summary.json"
    original_hash = digest(summary_path)
    saved = json.loads(summary_path.read_text())
    assert saved["execution_complete"] and saved["actual_solver_runs"] == 20
    spec = importlib.util.spec_from_file_location("executed_fem_mutation_test", root / "scripts/run_fem.py")
    fem = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fem)
    results = []
    lines = ["FEM audit mutation negative controls", "Started: " + datetime.datetime.now(datetime.timezone.utc).isoformat()]
    for mutation in ["saved_check_status", "coarse_metric"]:
        altered = copy.deepcopy(saved)
        if mutation == "saved_check_status":
            relevant = [c for c in altered["checks"] if c["id"].startswith("fem:convergence:")]
            chosen = next((c for c in relevant if c["status"] == "FAIL"), relevant[0])
            old = chosen["status"]
            chosen["status"] = "PASS" if old != "PASS" else "FAIL"
            change = {"id": chosen["id"], "old": old, "new": chosen["status"]}
        else:
            chosen = next(l for l in altered["levels"] if l["part"] == "bracket")
            old = chosen["max_vm_bound_MPa"]
            chosen["max_vm_bound_MPa"] = old + 100.0
            change = {"level": chosen["label"], "field": "max_vm_bound_MPa", "old": old, "new": chosen["max_vm_bound_MPa"]}
        with tempfile.TemporaryDirectory(prefix="v1_fem_audit_mutation_") as folder:
            isolated = Path(folder)
            for p in root.iterdir():
                if p.name == "results":
                    (isolated / "results").mkdir()
                    for result in p.iterdir():
                        if result.name in ["fem_summary.json", "fem_audit.json"]:
                            continue
                        (isolated / "results" / result.name).symlink_to(result, target_is_directory=result.is_dir())
                else:
                    (isolated / p.name).symlink_to(p, target_is_directory=p.is_dir())
            (isolated / "results/fem_summary.json").write_text(json.dumps(altered, indent=2) + "\n")
            start = time.monotonic()
            output, code = fem.audit(isolated)
            gate = next(c for c in output["checks"] if c["id"] == "fem:audit_recomputed_checks")
            passed = code == 3 and output["execution_complete"] is False and gate["status"] == "FAIL" and bool(gate["next_action"])
            results.append({"mutation": mutation, "changed": change, "negative_control_passed": passed, "audit_exit_code": code, "audit_execution_complete": output["execution_complete"], "elapsed_seconds": time.monotonic() - start, "detector": gate})
            lines.append(json.dumps(results[-1], sort_keys=True))
            print(mutation, "PASS" if passed else "FAIL", "audit exit", code, flush=True)
    unchanged = digest(summary_path) == original_hash
    complete = unchanged and all(c["negative_control_passed"] for c in results)
    output = {"schema": "fem-integrity-negative-controls-v1", "execution_complete": complete, "source_summary_sha256": original_hash, "source_summary_unchanged": unchanged, "original_solver_cases": saved["actual_solver_runs"], "method": "Altered only isolated copies of the real top-level summary. Per-level evidence, original solver artifacts and hashes remained unchanged. The real audit function reparsed the retained fine fields and rejected the mismatches.", "controls": results}
    (root / "results/fem_integrity_negative_controls.json").write_text(json.dumps(output, indent=2) + "\n")
    lines.append("Source summary unchanged: " + str(unchanged))
    lines.append("All negative controls passed: " + str(complete))
    (root / "logs/fem_integrity_negative_controls.log").write_text("\n".join(lines) + "\n")
    return 0 if complete else 1


if __name__ == "__main__":
    raise SystemExit(main())

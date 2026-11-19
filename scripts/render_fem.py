#!/usr/bin/env python3
"""Center the solved beam figure without changing any FEM numerical result.

This is an explicit postprocessing stage. It projects the retained 3D surface
orthographically, preserves actual nodal stress values, and updates figure-only
provenance. It never remeshes or invokes CalculiX.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import lzma
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def numerical_digest(summary):
    content = {k: summary[k] for k in ("levels", "checks", "actual_solver_runs", "execution_complete")}
    return hashlib.sha256(json.dumps(content, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def render(root):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import PolyCollection
    from matplotlib.colors import Normalize

    summary_path = root / "results/fem_summary.json"
    summary = json.loads(summary_path.read_text())
    if not summary.get("execution_complete"):
        raise ValueError("A complete executed FEM result is required before figure postprocessing")
    numerical_before = numerical_digest(summary)
    data_path = root / "results/stress_surface_data.json.xz"
    if sha(data_path) != summary["artifact_hashes"]["results/stress_surface_data.json.xz"]:
        raise ValueError("Retained surface data no longer match the executed result provenance")
    data = json.loads(lzma.decompress(data_path.read_bytes()))["beam"]
    finest = min((level for level in summary["levels"] if level["part"] == "beam"), key=lambda level: level["size_mm"])
    if data["metrics"] != finest:
        raise ValueError("Retained surface metrics differ from the executed finest-beam summary")
    xyz = np.asarray(data["xyz"], dtype=float)
    triangles = np.asarray(data["triangles"], dtype=int)
    stress = np.asarray(data["vm"], dtype=float)
    if len(stress) != len(xyz) or not np.all(np.isfinite(stress)) or np.any(stress < 0):
        raise ValueError("Malformed retained nodal stress field")

    # Rigid orthonormal view: preserve the real 3D geometry and depth ordering.
    # An explicit projection avoids the Mplot3D axis-box framing issue.
    azimuth, elevation = np.deg2rad([10.0, 20.0])
    horizontal = np.array([np.cos(azimuth), np.sin(azimuth), 0.0])
    vertical = np.array([-np.sin(azimuth) * np.sin(elevation), np.cos(azimuth) * np.sin(elevation), np.cos(elevation)])
    normal = np.cross(horizontal, vertical)
    centered = xyz - (xyz.max(axis=0) + xyz.min(axis=0)) / 2
    projected = centered @ np.array([horizontal, vertical, normal]).T
    order = np.argsort(projected[triangles, 2].mean(axis=1))
    norm = Normalize(0, float(stress.max()))
    colors = plt.get_cmap("viridis")(norm(stress[triangles].mean(axis=1)))

    fig = plt.figure(figsize=(14, 4.4), facecolor="white")
    ax = fig.add_axes([0.035, 0.20, 0.84, 0.60])
    ax.add_collection(PolyCollection(projected[triangles[order], :2], facecolors=colors[order], edgecolors="none", antialiased=False, rasterized=True))
    lower, upper = projected[:, :2].min(axis=0), projected[:, :2].max(axis=0)
    pad = (upper - lower) * 0.025
    ax.set_xlim(lower[0] - pad[0], upper[0] + pad[0])
    ax.set_ylim(lower[1] - pad[1], upper[1] + pad[1])
    ax.set_aspect("equal", adjustable="box")
    ax.set_axis_off()
    colorbar_ax = fig.add_axes([0.905, 0.265, 0.016, 0.40])
    bar = fig.colorbar(plt.cm.ScalarMappable(norm=norm, cmap="viridis"), cax=colorbar_ax)
    bar.set_label("Von Mises stress (MPa)", fontsize=10, labelpad=10)
    bar.ax.tick_params(labelsize=9)
    fig.text(0.035, 0.925, "Beam stress | 10 N central patch + gravity", fontsize=18, fontweight="bold")
    fig.text(0.035, 0.86, "Actual CalculiX result · undeformed 3D orthographic view · 400 mm beam", fontsize=10, color="#334455")
    peak = max(finest["max_nodal_vm_MPa"], finest["max_IP_vm_MPa"])
    fig.text(0.035, 0.145, f"Raw node/IP peak: {peak:.6g} MPa     Local maximum displacement: {finest['max_displacement_mm']:.7f} mm", fontsize=11)
    numerical_pass = all(check["status"] == "PASS" for check in summary["checks"])
    numerical_note = "Numerical model screens pass." if numerical_pass else "Numerical verification has failed checks; see fem_summary.json."
    fig.text(0.035, 0.065, "Triangle colors use actual nodal means; all raw peaks remain in the numerical checks.\n" + numerical_note + " Manufactured assembly qualification remains BLOCKED.", fontsize=9, color="#334455" if numerical_pass else "#a13613")
    output_path = root / "results/beam_stress.png"
    fig.savefig(output_path, dpi=180, facecolor="white")
    plt.close(fig)

    inputs = {
        "scripts/render_fem.py": sha(Path(__file__)),
        "results/stress_surface_data.json.xz": sha(data_path),
        f"fem/{finest['label']}/summary.json": sha(root / "fem" / finest["label"] / "summary.json"),
    }
    outputs = {"results/beam_stress.png": sha(output_path)}
    summary["artifact_hashes"].update(outputs)
    summary["input_hashes"]["scripts/render_fem.py"] = inputs["scripts/render_fem.py"]
    summary["postprocessing"] = {
        "kind": "figure-only postprocessing after the genuine solver run",
        "script": "scripts/render_fem.py",
        "input_hashes": inputs,
        "artifact_hashes": outputs,
        "numerical_digest_before": numerical_before,
        "numerical_digest_after": numerical_digest(summary),
        "note": "No numerical level, acceptance check, mesh, load, solver result or raw field changed. The renderer was applied after the solves, not used to produce them.",
    }
    if numerical_digest(summary) != numerical_before:
        raise ValueError("Figure-only postprocessing unexpectedly changed numerical results")
    write_json(summary_path, summary)
    checks = [{
        "id": "fem_render:solved_3d_figure", "requirements": ["R10"], "status": "PASS",
        "message": "Centered beam figure projects the retained actual finest-mesh 3D surface and nodal stress values.",
        "observed": {"surface_nodes": len(xyz), "surface_triangles": len(triangles), "raw_peak_MPa": peak, "image_pixels": [2520, 792]},
        "criterion": "Actual solved data; readable 3D scientific figure; unchanged numerical results",
        "next_action": "Retain the numerical evidence and complete physical qualification before release.",
        "evidence": ["results/beam_stress.png", "results/stress_surface_data.json.xz", "results/fem_summary.json"],
    }, {
        "id": "fem_render:numerics_preserved", "requirements": ["R10", "R13"], "status": "PASS",
        "message": "All executed numerical levels, checks and solver-run counts remain byte-equivalent under canonical JSON hashing.",
        "observed": numerical_before, "criterion": "Identical numerical digest before and after rendering",
        "next_action": "Use --force for a changed physical model; this stage only renders retained data.",
        "evidence": ["results/fem_summary.json", "results/fem_render.json"],
    }]
    return {"schema": "fem-figure-postprocessing-v1", "execution_complete": True, "actual_solver_runs": 0, "postprocessing_only": True, "input_hashes": inputs, "artifact_hashes": outputs, "checks": checks, "numerical_digest": numerical_before}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        receipt = render(root)
        code = 0
    except Exception as error:
        receipt = {"schema": "fem-figure-postprocessing-v1", "execution_complete": False, "postprocessing_only": True, "actual_solver_runs": 0, "checks": [{"id": "fem_render:error", "requirements": ["R10"], "status": "ERROR", "message": str(error), "observed": repr(error), "criterion": "Valid retained solved fields and preserved numerics", "next_action": "Restore the executed surface evidence and rerun this plotting stage; do not invent stress values.", "evidence": ["results/stress_surface_data.json.xz"]}], "input_hashes": {"scripts/render_fem.py": sha(Path(__file__))}}
        code = 3
    write_json(root / "results/fem_render.json", receipt)
    print(json.dumps({"stage": "FEM figure postprocessing", "execution_complete": receipt["execution_complete"], "checks": len(receipt["checks"]), "exit_code": code}))
    return code


if __name__ == "__main__":
    raise SystemExit(main())

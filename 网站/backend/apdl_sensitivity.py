"""Run and report LS-DYNA mesh/loading-time sensitivity studies."""
from __future__ import annotations

import copy
import json
import threading
import time
import uuid
from pathlib import Path

import numpy as np

from .runner import _atomic_json
from .system_info import sha256


DEFAULT_MESHES = [
    {"label": "coarse", "nx": 21, "ny": 3, "layers": 2},
    {"label": "baseline", "nx": 41, "ny": 5, "layers": 4},
    {"label": "fine", "nx": 61, "ny": 7, "layers": 6},
]
DEFAULT_LOADING_TIMES = [0.002, 0.004]


def _study_path(server, study_id):
    server.validate_id(study_id)
    path = server.runtime / "apdl_sensitivity" / study_id / "status.json"
    if not path.is_file():
        raise FileNotFoundError("敏感性研究不存在")
    return path


def _write(study_path, status):
    _atomic_json(study_path, status)


def _number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not np.isfinite(value) or value <= 0:
        raise ValueError(f"{label}必须是正的有限数值")
    return float(value)


def _meshes(value):
    value = DEFAULT_MESHES if value is None else value
    if not isinstance(value, list) or not 2 <= len(value) <= 3:
        raise ValueError("网格敏感性至少需要两组、最多三组网格")
    result = []
    labels = set()
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("网格工况必须是对象")
        label = str(item.get("label", "")).strip()
        if not label or label in labels:
            raise ValueError("网格名称必须非空且不重复")
        labels.add(label)
        values = {}
        for key in ("nx", "ny", "layers"):
            number = item.get(key)
            if isinstance(number, bool) or not isinstance(number, int) or number < 2:
                raise ValueError(f"{key}必须是不小于2的整数")
            values[key] = number
        if values["nx"] % 2 == 0 or values["ny"] % 2 == 0:
            raise ValueError("网格 nx、ny 必须为奇数节点数")
        result.append({"label": label, **values})
    return result


def _times(value):
    value = DEFAULT_LOADING_TIMES if value is None else value
    if not isinstance(value, list) or not 2 <= len(value) <= 4:
        raise ValueError("加载时间敏感性至少需要两个、最多四个时间")
    result = [_number(item, "加载时间") for item in value]
    if len(set(result)) != len(result):
        raise ValueError("加载时间不能重复")
    return result


def _source_material(server, source_id, spec):
    material = spec.get("material_source") or {}
    input_path = material.get("input_path")
    source_path = server.runtime / "jobs" / source_id / input_path if input_path else None
    source = material.get("source") or {}
    return {
        "name": source.get("name") or (source_path.name if source_path else "inline plastic curve"),
        "sha256": source.get("sha256") or (sha256(source_path) if source_path and source_path.is_file() else None),
        "points": len(spec["options"].get("plastic_curve") or []),
        "max_plastic_strain": float((spec["options"].get("plastic_curve") or [[0, 0]])[-1][0]),
        "status": "material_curve_applied_structural_response_unverified",
    }


def _metric(case, state):
    result = state.get("result") or state.get("summary") or {}
    fracture = (result.get("results") or {}).get("fracture") or result.get("fracture") or {}
    options = result.get("options") or {}
    stats = result.get("stats") or {}
    markers = fracture.get("stage_markers") or {}
    separation = markers.get("load_path_separation") or {}
    return {
        "case_id": case["job_id"],
        "mesh_label": case["mesh_label"],
        "loading_time_s": case["loading_time_s"],
        "nx": options.get("nx", case["nx"]),
        "ny": options.get("ny", case["ny"]),
        "layers": options.get("layers", case["layers"]),
        "element_count": stats.get("element_count"),
        "peak_force_n": fracture.get("peak_force_n"),
        "peak_engineering_strain": fracture.get("peak_engineering_strain"),
        "first_deletion_time_s": fracture.get("first_deletion_time_s"),
        "separation_time_s": separation.get("time_s"),
        "separation_displacement_mm": separation.get("applied_displacement_mm"),
        "final_force_ratio": fracture.get("final_force_ratio"),
        "energy_ratio": fracture.get("prefracture_max_kinetic_internal_ratio"),
        "damping_ratio": fracture.get("prefracture_max_damping_internal_ratio"),
        "quasistatic_screen_passed": fracture.get("quasistatic_screen_passed"),
        "fracture_confirmed": fracture.get("fracture_confirmed"),
        "state": state.get("state"),
        "error": state.get("error"),
    }


def _with_deltas(rows, baseline):
    keys = ("peak_force_n", "peak_engineering_strain", "separation_displacement_mm")
    for row in rows:
        for key in keys:
            base = baseline.get(key)
            value = row.get(key)
            row[key + "_delta_pct"] = (100 * (value - base) / base
                                        if isinstance(value, (int, float)) and isinstance(base, (int, float)) and base else None)


def _render(study_dir, status):
    rows = [row for row in status.get("results", []) if row.get("state") == "completed"]
    if not rows:
        return
    baseline = next((row for row in rows if row["mesh_label"] == "baseline" and abs(row["loading_time_s"] - .002) < 1e-12), rows[0])
    _with_deltas(rows, baseline)
    status["results"] = rows
    status["baseline_case"] = {key: baseline.get(key) for key in (
        "case_id", "mesh_label", "loading_time_s", "peak_force_n", "peak_engineering_strain",
        "separation_displacement_mm", "final_force_ratio", "quasistatic_screen_passed")}
    _atomic_json(study_dir / "sensitivity_report.json", status)
    headers = [
        "case_id", "mesh_label", "loading_time_s", "nx", "ny", "layers", "element_count",
        "peak_force_n", "peak_engineering_strain", "first_deletion_time_s", "separation_time_s",
        "separation_displacement_mm", "final_force_ratio", "energy_ratio", "damping_ratio",
        "quasistatic_screen_passed", "fracture_confirmed", "peak_force_n_delta_pct",
        "peak_engineering_strain_delta_pct", "separation_displacement_mm_delta_pct", "state", "error",
    ]
    with (study_dir / "sensitivity_summary.csv").open("w", encoding="utf-8", newline="") as stream:
        stream.write(",".join(headers) + "\n")
        for row in rows:
            stream.write(",".join("" if row.get(key) is None else str(row.get(key)) for key in headers) + "\n")
    try:
        import matplotlib
        matplotlib.use("Agg")
        from matplotlib import pyplot as plt
        fig, axes = plt.subplots(1, 2, figsize=(10, 4.2), constrained_layout=True)
        for label in sorted({row["mesh_label"] for row in rows}):
            group = sorted((row for row in rows if row["mesh_label"] == label), key=lambda row: row["loading_time_s"])
            axes[0].plot([row["loading_time_s"] * 1000 for row in group], [row["peak_force_n"] for row in group], "o-", label=label)
            axes[1].plot([row["element_count"] for row in group], [row["peak_force_n"] for row in group], "o-", label=f"{label} · time varied")
        axes[0].set(xlabel="Loading time (ms)", ylabel="Peak force (N)", title="Loading-time sensitivity")
        axes[1].set(xlabel="Element count", ylabel="Peak force (N)", title="Mesh sensitivity")
        for ax in axes:
            ax.grid(alpha=.2)
            ax.legend(fontsize=7)
        fig.savefig(study_dir / "sensitivity_metrics.png", dpi=160)
        plt.close(fig)
    except Exception as exc:
        status.setdefault("warnings", []).append(f"敏感性图绘制失败，CSV/JSON仍保留：{exc}")


def _run(server, study_id):
    study_dir = server.runtime / "apdl_sensitivity" / study_id
    status_path = study_dir / "status.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    status["state"] = "running"
    _write(status_path, status)
    try:
        for case in status["cases"]:
            if case["state"] == "completed":
                continue
            server.launch(case["job_id"])
            while True:
                state = server.get_job(case["job_id"])
                case["state"] = state.get("state")
                case["message"] = state.get("message")
                _write(status_path, status)
                if case["state"] not in {"queued", "running", "pending", "created"}:
                    break
                time.sleep(.5)
            metric = _metric(case, state)
            status["results"] = [row for row in status.get("results", []) if row["case_id"] != case["job_id"]]
            status["results"].append(metric)
            _render(study_dir, status)
            _write(status_path, status)
        status["state"] = "completed" if all(case["state"] == "completed" for case in status["cases"]) else "needs_attention"
        status["completed_count"] = sum(case["state"] == "completed" for case in status["cases"])
        status["failed_count"] = sum(case["state"] not in {"completed"} for case in status["cases"])
        _render(study_dir, status)
    except Exception as exc:
        status.update(state="failed", error=str(exc))
    finally:
        status["updated_at"] = time.time()
        _write(status_path, status)


def create_sensitivity(server, payload):
    if not isinstance(payload, dict):
        raise ValueError("敏感性请求必须是对象")
    source_id = payload.get("source_job_id")
    server.validate_id(source_id)
    source = server.get_job(source_id)
    if source.get("kind") != "apdl_tension" or source.get("state") != "completed":
        raise ValueError("敏感性研究必须从已完成的无腐蚀 APDL/LS-DYNA 任务开始")
    spec_path = server.runtime / "jobs" / source_id / "spec.json"
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    base_options = copy.deepcopy(spec.get("options") or {})
    if base_options.get("corrosion_mode") != "flat" or base_options.get("material_model") != "multilinear_iso":
        raise ValueError("P1 只接受无腐蚀 MISO 小试件")
    curve = base_options.get("plastic_curve") or []
    if len(curve) < 2:
        raise ValueError("源任务没有可复用的真实 MISO 曲线")
    meshes = _meshes(payload.get("meshes"))
    loading_times = _times(payload.get("loading_times_s"))
    study_id = uuid.uuid4().hex[:16]
    study_dir = server.runtime / "apdl_sensitivity" / study_id
    study_dir.mkdir(parents=True, exist_ok=False)
    cases = []
    try:
        for mesh in meshes:
            for loading_time in loading_times:
                options = copy.deepcopy(base_options)
                options.update(nx=mesh["nx"], ny=mesh["ny"], layers=mesh["layers"],
                               loading_time_s=loading_time, case_name=None)
                case_name = f"P1真实材料·{mesh['label']}·{loading_time:g}s"
                job = server.create_job({"kind": "apdl_tension", "run_mode": "solve", "options": options,
                                         "case_name": case_name}, launch=False)
                cases.append({"job_id": job["id"], "mesh_label": mesh["label"],
                              "loading_time_s": loading_time, "nx": mesh["nx"], "ny": mesh["ny"],
                              "layers": mesh["layers"], "state": "queued"})
    except Exception:
        for case in cases:
            server.pending_jobs.discard(case["job_id"])
            import shutil
            shutil.rmtree(server.runtime / "jobs" / case["job_id"], ignore_errors=True)
        study_dir.rmdir()
        raise
    status = {
        "id": study_id, "state": "queued", "source_job_id": source_id,
        "material_source": _source_material(server, source_id, spec),
        "meshes": meshes, "loading_times_s": loading_times, "cases": cases,
        "results": [], "created_at": time.time(),
        "warnings": ["本研究复用源任务的材料与 GISSMO 参数；仅改变网格和物理加载时间。",
                      "没有试验力—位移/DIC目标时，不把峰值匹配称为结构响应已标定。"],
    }
    _write(study_dir / "status.json", status)
    threading.Thread(target=_run, args=(server, study_id), daemon=True,
                     name=f"apdl-sensitivity-{study_id}").start()
    return status


def sensitivity_status(server, study_id):
    path = _study_path(server, study_id)
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("state") in {"completed", "needs_attention", "failed"}:
        report = path.parent / "sensitivity_report.json"
        if report.is_file():
            value = json.loads(report.read_text(encoding="utf-8"))
    return value


def sensitivity_file(server, study_id, name):
    path = _study_path(server, study_id).parent / name
    if not path.is_file() or path.name not in {"sensitivity_report.json", "sensitivity_summary.csv", "sensitivity_metrics.png"}:
        raise FileNotFoundError("敏感性结果文件不存在")
    return path

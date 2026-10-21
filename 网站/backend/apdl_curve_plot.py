"""Generate curve previews from saved APDL loading data."""
import io
from pathlib import Path

import numpy as np

from .apdl_solver import _write_curve_plot
from .runner import _atomic_json

MAX_CURVE_BYTES = 32_000_000


def generate_force_displacement_plot(service, job_id):
    return _generate_plot(service, job_id, 'force_displacement', 'load_displacement.png')


def generate_stress_strain_plot(service, job_id):
    return _generate_plot(service, job_id, 'stress_strain', 'engineering_stress_strain.png')


def _generate_plot(service, job_id, kind, filename):
    service.validate_id(job_id)
    job = service.get_job(job_id)
    summary = job.get('summary') or {}
    if job.get('kind') != 'apdl_tension' or job.get('state') not in {
            'completed', 'failed', 'interrupted', 'stopped'}:
        raise ValueError('只能为已结束且保存了加载数据的 APDL 任务生成曲线')

    output = service.runtime / 'jobs' / job_id / 'outputs'
    source = output / 'force_displacement.csv'
    if (source.is_symlink() or not source.is_file() or source.stat().st_size > MAX_CURVE_BYTES or
            source.resolve().parent != output.resolve()):
        raise ValueError('任务缺少有效的 force_displacement.csv')
    try:
        with source.open('rb') as stream:
            data = stream.read(MAX_CURVE_BYTES + 1)
        if len(data) > MAX_CURVE_BYTES:
            raise ValueError('force_displacement.csv 超过大小限制')
        curve = np.loadtxt(io.BytesIO(data), delimiter=',', ndmin=2)
    except (OSError, ValueError) as exc:
        raise ValueError('force_displacement.csv 无法读取为六列数值曲线') from exc
    if curve.ndim != 2 or curve.shape[1] != 6 or len(curve) < 2 or not np.isfinite(curve).all():
        raise ValueError('force_displacement.csv 必须至少有两行、六列有限数值')

    saved_curve = (summary.get('results') or {}).get('curve')
    if saved_curve is not None:
        saved_curve = np.asarray(saved_curve, dtype=float)
        if saved_curve.shape != curve.shape or not np.array_equal(saved_curve, curve):
            raise ValueError('CSV 与求解完成时保存的曲线不一致，拒绝绘图')

    if kind == 'force_displacement':
        _write_curve_plot(output / filename, curve)
    else:
        _write_stress_strain_plot(output / filename, curve)
    result = summary.setdefault('results', {})
    key = 'curve_plot' if kind == 'force_displacement' else 'stress_strain_plot'
    partial = job.get('state') != 'completed' or summary.get('solve_state') != 'solved'
    report = {
        'state': 'completed',
        'file': filename,
        'generated_after_solve': True,
        'data_quality': 'partial' if partial else 'validated',
        'note': ('任务求解未完整通过；该图仅表示 force_displacement.csv 中已保存的计算过程，'
                 '不能作为完整有效求解结果。' if partial else
                 '图像依据已保存并通过求解后校核的加载曲线生成。'),
    }
    result[key] = report
    result['files'] = list(dict.fromkeys([*result.get('files', []), filename]))
    summary[key] = report
    _atomic_json(output / 'summary.json', summary)
    return service.get_job(job_id)


def _write_stress_strain_plot(path: Path, curve: np.ndarray) -> None:
    import matplotlib
    matplotlib.use('Agg')
    from matplotlib import pyplot as plt
    from matplotlib.font_manager import FontProperties
    font_path = Path(r'C:\Windows\Fonts\msyh.ttc')
    font = FontProperties(fname=str(font_path)) if font_path.is_file() else None
    fig, axis = plt.subplots(figsize=(7.2, 4.8), constrained_layout=True)
    try:
        axis.plot(curve[:, 4] * 100.0, curve[:, 5], marker='o', markersize=2.5,
                  linewidth=1.7, color='#26734e')
        axis.set_xlabel('Engineering strain (%)', fontproperties=font)
        axis.set_ylabel('Nominal stress (MPa)', fontproperties=font)
        axis.set_title('Engineering stress-strain response', fontproperties=font)
        axis.grid(True, color='#d8dfda', linewidth=.65, alpha=.8)
        axis.spines[['top', 'right']].set_visible(False)
        for tick in [*axis.get_xticklabels(), *axis.get_yticklabels()]:
            if font is not None:
                tick.set_fontproperties(font)
        fig.savefig(path, dpi=180)
    finally:
        plt.close(fig)

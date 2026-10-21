"""Multi-task engineering stress-strain plots from completed MAPDL results."""
import csv
import hashlib
import io
import re
import uuid
from pathlib import Path

import numpy as np

from .runner import _atomic_json

MAX_CURVE_BYTES = 32_000_000
ALLOWED_EXPORTS = {'curve.csv', 'curve.png', 'curve.svg', 'report.json'}


def _completed_curve(service, job_id):
    service.validate_id(job_id)
    state = service.get_job(job_id)
    if state.get('kind') != 'apdl_tension' or state.get('state') != 'completed':
        raise ValueError(f'任务 {job_id} 不是已完成的 APDL 求解任务')
    if (state.get('summary') or {}).get('solve_state') != 'solved':
        raise ValueError(f'任务 {job_id} 没有已完成的 MAPDL 求解结果')
    output = service.runtime / 'jobs' / job_id / 'outputs'
    path = output / 'force_displacement.csv'
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_CURVE_BYTES:
        raise ValueError(f'任务 {job_id} 缺少有效的 force_displacement.csv')
    if path.resolve().parent != output.resolve():
        raise ValueError(f'任务 {job_id} 的曲线文件路径无效')
    try:
        with path.open('rb') as stream:
            snapshot = stream.read(MAX_CURVE_BYTES + 1)
        if len(snapshot) > MAX_CURVE_BYTES:
            raise ValueError('CSV 超过大小限制')
        values = np.loadtxt(io.BytesIO(snapshot), delimiter=',', ndmin=2)
    except (OSError, ValueError) as exc:
        raise ValueError(f'任务 {job_id} 的曲线 CSV 无法读取') from exc
    if values.ndim != 2 or values.shape[1] != 6 or len(values) < 2 or not np.isfinite(values).all():
        raise ValueError(f'任务 {job_id} 的曲线必须是至少两行、六列有限数值')
    strain, stress = values[:, 4], values[:, 5]
    if np.any(strain < -1e-10) or np.any(np.diff(strain) < -1e-10):
        raise ValueError(f'任务 {job_id} 的工程应变不是非负单调加载数据')
    original = (state.get('summary') or {}).get('results') or {}
    if original.get('curve') is not None:
        verified = np.asarray(original['curve'], dtype=float)
        if verified.shape != values.shape or not np.array_equal(verified, values):
            raise ValueError(f'任务 {job_id} 的 CSV 与求解时保存的曲线不一致')
    with np.errstate(over='ignore'):
        points = np.column_stack((strain * 100.0, stress))
    if not np.isfinite(points).all():
        raise ValueError(f'任务 {job_id} 的应变百分数超出有限数值范围')
    return points, hashlib.sha256(snapshot).hexdigest(), {
        'validation_state': original.get('validation_state', 'not_recorded'),
        'warnings': original.get('warnings', []),
        'rst_validation': original.get('rst_validation'),
    }


def list_stress_strain_sources(service):
    sources = []
    for job in service.list_jobs(include_hidden=True, limit=1000):
        if job.get('kind') != 'apdl_tension' or job.get('state') != 'completed':
            continue
        if (job.get('summary') or {}).get('solve_state') != 'solved':
            continue
        path = service.runtime / 'jobs' / job['id'] / 'outputs' / 'force_displacement.csv'
        if path.is_file() and not path.is_symlink() and path.stat().st_size <= MAX_CURVE_BYTES:
            sources.append({'id': job['id'], 'name': job.get('display_name') or job['id'],
                            'created_at': job.get('created_at')})
    return sources


def create_stress_strain_comparison(service, payload):
    selection = payload.get('sources')
    if not isinstance(selection, list) or not 2 <= len(selection) <= 20:
        raise ValueError('请选择 2 至 20 个已完成的 APDL 求解任务')
    ids = [item.get('job_id') for item in selection if isinstance(item, dict)]
    if len(ids) != len(selection) or any(not isinstance(value, str) for value in ids) or len(set(ids)) != len(ids):
        raise ValueError('任务选择必须是不同的有效任务')

    curves = []
    for item in selection:
        label = item.get('label')
        if not isinstance(label, str) or not label.strip() or len(label.strip()) > 80 or any(ord(c) < 32 for c in label):
            raise ValueError('每条曲线标签须为 1 至 80 个可显示字符')
        points, digest, validation = _completed_curve(service, item['job_id'])
        curves.append({'job_id': item['job_id'], 'label': label.strip(),
                       'points': points, 'sha256': digest, 'source_validation': validation})

    folder_id = uuid.uuid4().hex[:16]
    root = service.runtime / 'apdl_stress_strain_comparisons' / folder_id
    root.mkdir(parents=True, exist_ok=False)
    report_sources = []
    with (root / 'curve.csv').open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.writer(stream)
        writer.writerow(['source_job_id', 'curve_label', 'point_index',
                         'engineering_strain_percent', 'nominal_stress_mpa'])
        for curve in curves:
            for index, (strain_percent, stress_mpa) in enumerate(curve['points']):
                writer.writerow([curve['job_id'], curve['label'], index,
                                 format(strain_percent, '.17g'), format(stress_mpa, '.17g')])
            report_sources.append({'job_id': curve['job_id'], 'label': curve['label'],
                                   'point_count': len(curve['points']),
                                   'engineering_strain_percent_range': [
                                       float(curve['points'][:, 0].min()), float(curve['points'][:, 0].max())],
                                   'nominal_stress_mpa_range': [
                                       float(curve['points'][:, 1].min()), float(curve['points'][:, 1].max())],
                                   'sha256': curve['sha256'],
                                   'source_validation': curve['source_validation']})

    import matplotlib
    matplotlib.use('Agg')
    from matplotlib.font_manager import FontProperties
    from matplotlib import pyplot as plt
    font_path = Path(r'C:\Windows\Fonts\msyh.ttc')
    font = FontProperties(fname=str(font_path)) if font_path.is_file() else None
    fig, ax = plt.subplots(figsize=(8.2, 5.6), layout='constrained')
    try:
        colors = matplotlib.colormaps['tab20'].colors
        for index, curve in enumerate(curves):
            points = curve['points']
            ax.plot(points[:, 0], points[:, 1], color=colors[index], linewidth=1.8, label=curve['label'])
        ax.set_xlabel('Engineering strain (%)', fontproperties=font)
        ax.set_ylabel('Nominal stress (MPa)', fontproperties=font)
        ax.grid(True, which='major', color='#d8dfda', linewidth=.65)
        ax.grid(True, which='minor', color='#edf0ed', linewidth=.45)
        ax.minorticks_on()
        ax.spines[['top', 'right']].set_visible(False)
        ax.legend(frameon=False, prop=font)
        for tick in [*ax.get_xticklabels(), *ax.get_yticklabels()]:
            tick.set_fontproperties(font)
        fig.savefig(root / 'curve.png', dpi=600, facecolor='white')
        fig.savefig(root / 'curve.svg', facecolor='white')
    finally:
        plt.close(fig)

    report = {'id': folder_id, 'state': 'completed', 'plot': 'nominal stress vs engineering strain',
              'x_axis': {'label': 'Engineering strain (%)', 'source_column': 5,
                         'source_unit': 'fraction', 'conversion': 'value * 100'},
              'y_axis': {'label': 'Nominal stress (MPa)', 'source_column': 6,
                         'source_unit': 'MPa', 'conversion': 'none'},
              'sources': report_sources,
              'note': '仅绘图，不重新求解、不平滑或重采样。保留原反力与应力符号。曲线标签由用户填写；来源任务的警告与校核限制保留在报告中，绘图不代表新增物理验收。'}
    _atomic_json(root / 'report.json', report)
    return report


def comparison_file(service, comparison_id, name):
    if not re.fullmatch(r'[0-9a-f]{16}', comparison_id) or name not in ALLOWED_EXPORTS:
        raise FileNotFoundError('对比成果不存在')
    root = (service.runtime / 'apdl_stress_strain_comparisons' / comparison_id).resolve()
    path = root / name
    if not path.resolve().is_relative_to(root) or path.is_symlink() or not path.is_file():
        raise FileNotFoundError('对比成果文件不存在')
    return path

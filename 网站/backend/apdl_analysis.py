"""Evidence-only solver diagnosis and independent trial/simulation comparisons."""
from pathlib import Path
import re
import shutil
import uuid

import numpy as np

from .runner import _atomic_json
from .system_info import sha256


def diagnose_output(output):
    output = Path(output)
    evidence, categories = [], set()
    rules = {
        'license': (r'license|licensing|flexnet', '检查许可证可用性与实际退出日志，不通过放宽求解参数处理'),
        'mesh': (r'distort|jacobian|negative volume|element shape', '核对问题单元、厚度和节点顺序；结合网格质量报告检查'),
        'convergence': (r'not converg|did not converg|unconverged|bisection|too many equilibrium', '核对最后收敛子步、载荷、材料和约束；不自动放宽容差'),
        'material': (r'plastic|material|negative slope', '检查材料定义、单位、曲线范围及下降段'),
    }
    files, last_converged = [], None
    counts = dict(error=0, warning=0)
    names = ['mapdl.out', 'mapdl_launcher.log', 'mesh_quality_report.txt']
    names.extend(path.name for path in sorted(output.glob('corrosion*.err')))
    for name in names:
        path = output / name
        if not path.is_file():
            continue
        files.append(name)
        remaining_context = 0
        with path.open(encoding='utf-8', errors='replace') as stream:
            for number, raw in enumerate(stream, 1):
                line = raw.strip()[:700]
                error = bool(re.search(r'\*{3}\s*ERROR\s*\*{3}|SOLUTION\s+(?:DID\s+NOT\s+CONVERGE|NOT\s+CONVERGED)|UNCONVERGED\s+SOLUTION|^APDL_SELF_CHECK_FAILED', line, re.I))
                warning = bool(re.search(r'\*{3}\s*WARNING\s*\*{3}', line, re.I))
                converged = bool(re.search(r'LOAD STEP.*SUBSTEP.*COMPLETED|EQUILIBRIUM ITERATION.*CONVERGED', line, re.I))
                if converged and not error:
                    last_converged = dict(file=name, line=number, text=line)
                if error or warning:
                    counts['error' if error else 'warning'] += 1
                    remaining_context = 3
                if (error or warning or remaining_context) and len(evidence) < 160:
                    evidence.append(dict(file=name, line=number, level='error' if error else 'warning' if warning else 'context', text=line))
                    for category, (pattern, _) in rules.items():
                        if re.search(pattern, line, re.I):
                            categories.add(category)
                remaining_context = max(0, remaining_context - 1)
    return dict(state='errors_found' if counts['error']
                else 'warnings_found' if counts['warning']
                else 'no_explicit_errors' if files else 'no_solver_logs',
                files=files, evidence=evidence, counts=counts, evidence_limit=160, categories=sorted(categories),
                suggestions=[rules[key][1] for key in sorted(categories)],
                last_explicit_converged_record=last_converged, convergence_verified=False,
                note='仅解析已保存日志；未发现错误不代表求解或物理验收通过，未自动修改命令')


def _curve(values, label):
    try:
        array = np.asarray(values, dtype=float)
    except (ValueError, TypeError) as exc:
        raise ValueError(label + '必须为两列有限数据') from exc
    if array.ndim != 2 or array.shape[1] != 2 or len(array) < 2 or not np.isfinite(array).all():
        raise ValueError(label + '至少需要两个有限位移—力点')
    if np.any(np.diff(array[:, 0]) <= 0):
        raise ValueError(label + '位移必须严格递增；请明确提供单调加载分支，不能重复位移或自动排序')
    return array


def compare_curves(simulation, experiment, *, displacement_unit='mm', force_unit='N'):
    sim = _curve(simulation, '模拟曲线')
    trial = _curve(experiment, '试验曲线').copy()
    if displacement_unit not in {'mm', 'm'} or force_unit not in {'N', 'kN'}:
        raise ValueError('位移单位仅支持mm/m，力单位仅支持N/kN')
    trial[:, 0] *= 1000 if displacement_unit == 'm' else 1
    trial[:, 1] *= 1000 if force_unit == 'kN' else 1
    if not np.isfinite(trial).all():
        raise ValueError('单位换算后数据超出有限范围')
    low, high = max(sim[0, 0], trial[0, 0]), min(sim[-1, 0], trial[-1, 0])
    if high <= low:
        raise ValueError('模拟与试验没有有效的共同位移范围')
    mask = (trial[:, 0] >= low) & (trial[:, 0] <= high)
    if mask.sum() < 2:
        raise ValueError('共同位移范围至少需要两个试验点')
    x, observed = trial[mask].T
    predicted = np.interp(x, sim[:, 0], sim[:, 1])
    residual = predicted - observed
    if not np.isfinite(residual).all() or not np.isfinite(residual ** 2).all():
        raise ValueError('力差值超出可计算范围')
    # JSON API and plot previews are bounded; full comparison is saved as CSV.
    return dict(overlap_mm=[float(low), float(high)], compared_points=int(mask.sum()),
        outside_overlap_points=int((~mask).sum()), rmse_N=float(np.sqrt(np.mean(residual ** 2))),
        mae_N=float(np.mean(np.abs(residual))),
        comparison=np.column_stack((x, observed, predicted, residual)).tolist(),
        simulation=sim.tolist(), experiment=trial.tolist(),
        note='在原始试验位移处线性插值模拟值；不外推、不平移、不归零，力保留原符号；仅评价共同范围')


def save_comparison(service, payload):
    from .apdl_commands import _source
    from .apdl_materials import uploaded_table, numeric_pair
    export = payload.get('export_directory', '')
    if not isinstance(export, str):
        raise ValueError('导出目录必须为字符串')
    export = export.strip()
    state, output = _source(service, payload.get('source_job_id'))
    if state.get('spec', {}).get('execution_mode') == 'custom_commands' and payload.get('confirm_csv_contract') is not True:
        raise ValueError('自定义命令须确认CSV仍为原六列，第二列位移mm、第三列加载端总反力N')
    curve_path = output / 'force_displacement.csv'
    if not curve_path.is_file() or curve_path.stat().st_size > 32_000_000:
        raise ValueError('缺少或超出32MB的force_displacement.csv；需要真实求解结果')
    before = sha256(curve_path)
    try:
        values = np.loadtxt(curve_path, delimiter=',', ndmin=2)
    except ValueError as exc:
        raise ValueError('模拟曲线不是原六列数值CSV') from exc
    if values.shape[1] != 6:
        raise ValueError('模拟曲线必须是原六列数值CSV')
    selection = payload.get('selection') or {}
    table, source, source_path = uploaded_table(service, payload)
    pairs = numeric_pair(table, selection, 'displacement_column', 'force_column')
    report = compare_curves(values[:, [1, 2]], pairs,
        displacement_unit=selection.get('displacement_unit'), force_unit=selection.get('force_unit'))
    name = payload.get('name', '试验模拟对照')
    if not isinstance(name, str) or not name.strip() or len(name) > 100:
        raise ValueError('对照名称必须为1至100字')
    report.update(name=name.strip(), source=source, selection=selection,
                  source_job_id=state['id'], simulation_sha256=before)
    if sha256(curve_path) != before:
        raise ValueError('读取期间模拟曲线发生变化')
    target = output / 'analyses' / ('comparison_' + uuid.uuid4().hex[:12])
    target.mkdir(parents=True)
    shutil.copy2(source_path, target / ('experiment_original' + source_path.suffix))
    shutil.copy2(curve_path, target / 'simulation_original.csv')
    if sha256(target / 'simulation_original.csv') != before or sha256(target / ('experiment_original' + source_path.suffix)) != source['sha256']:
        raise ValueError('对照来源冻结校验失败')
    np.savetxt(target / 'comparison.csv', report['comparison'], delimiter=',',
        header='displacement_mm,experiment_N,simulation_N,residual_N', comments='')
    import matplotlib
    matplotlib.use('Agg')
    from matplotlib import pyplot as plt
    fig, ax = plt.subplots(figsize=(7.5, 5), layout='constrained')
    try:
        sim, trial = np.asarray(report['simulation']), np.asarray(report['experiment'])
        ax.plot(sim[:, 0], sim[:, 1], label='Simulation', linewidth=1.8)
        ax.plot(trial[:, 0], trial[:, 1], 'o-', label='Experiment', markersize=3, linewidth=1)
        ax.axvspan(*report['overlap_mm'], color='#26734e', alpha=.07, label='Compared range')
        ax.set(xlabel='Displacement (mm)', ylabel='Reaction / Force (N)')
        ax.legend(frameon=False)
        ax.spines[['top', 'right']].set_visible(False)
        fig.savefig(target / 'comparison.png', dpi=300)
        fig.savefig(target / 'comparison.svg')
    finally:
        plt.close(fig)
    report['relative_directory'] = target.relative_to(output).as_posix()
    if export:
        from .task_io import validate_task_io
        settings = validate_task_io(dict(name=name, export_directory=export), service.runtime)
        parent = Path(settings['export_directory'])
        parent.mkdir(parents=True, exist_ok=True)
        safe_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name).strip(' .')[:60]
        destination = parent / ('对照_' + safe_name + '_' + uuid.uuid4().hex[:8])
        report['export_directory'] = str(destination)
        _atomic_json(target / 'report.json', report)
        shutil.copytree(target, destination)
    _atomic_json(target / 'report.json', report)
    report = dict(report)
    for key in ('simulation', 'experiment'):
        points = report[key]
        step = max(1, (len(points) + 1199) // 1200)
        report[key] = points[::step] + ([points[-1]] if (len(points)-1) % step else [])
    report.pop('comparison', None)
    return report

"""Joint force-displacement and DIC necking evidence report."""
from __future__ import annotations

import json
import re
import shutil
import uuid
from pathlib import Path

import numpy as np

from .apdl_analysis import compare_curves
from .apdl_commands import _source
from .apdl_materials import numeric_pair, uploaded_table
from .runner import _atomic_json
from .system_info import sha256


ALLOWED_FILES = {'joint_calibration_report.json', 'joint_calibration.csv', 'joint_calibration.png'}


def _finite_pairs(service, payload, x_key, y_key, label):
    table, source, path = uploaded_table(service, payload)
    pairs = numeric_pair(table, payload.get('selection') or {}, x_key, y_key)
    values = np.asarray(pairs, dtype=float)
    if not np.isfinite(values).all() or len(values) < 2:
        raise ValueError(label + '至少需要两个有限数值点')
    if np.any(np.diff(values[:, 0]) <= 0):
        raise ValueError(label + '第一列必须严格递增，不能自动排序')
    return values, source, path


def _unit(value, allowed, label):
    if value not in allowed:
        raise ValueError(label + '单位无效')
    return value


def _read_dic(service, payload):
    selection = payload.get('selection') or {}
    table, source, path = uploaded_table(service, payload)
    pairs = numeric_pair(table, selection, 'displacement_column', 'position_column')
    values = np.asarray(pairs, dtype=float)
    field_column = selection.get('field_column')
    if field_column is not None:
        if type(field_column) is not int or not 0 <= field_column < len(table['columns']):
            raise ValueError('DIC 局部场列不是有效列号')
        fields = []
        for row in table['rows']:
            value = row[field_column]
            if not isinstance(value, (int, float)) or not np.isfinite(value):
                raise ValueError('DIC 局部场包含非有限值')
            fields.append(float(value))
        values = np.column_stack((values, fields))
    if not np.isfinite(values).all() or len(values) < 2:
        raise ValueError('DIC 数据至少需要两个有限数值点')
    if np.any(np.diff(values[:, 0]) <= 0):
        raise ValueError('DIC 位移列必须严格递增，不能自动排序')
    selection = dict(selection)
    displacement_unit = _unit(selection.get('displacement_unit'), {'mm', 'm'}, 'DIC 位移')
    position_unit = _unit(selection.get('position_unit'), {'mm', 'm'}, 'DIC 颈缩位置')
    field_type = selection.get('field_type', 'none')
    if field_type not in {'none', 'equivalent_plastic_strain', 'engineering_strain'}:
        raise ValueError('DIC 局部场类型无效')
    values[:, 0] *= 1000 if displacement_unit == 'm' else 1
    values[:, 1] *= 1000 if position_unit == 'm' else 1
    return values, source, path, selection


def _simulation_local_field(output, applied_displacement):
    path = output / 'damage_history.csv'
    if not path.is_file():
        return None
    values = np.loadtxt(path, delimiter=',', skiprows=1, ndmin=2)
    if values.ndim != 2 or values.shape[1] < 4 or not np.isfinite(values[:, :4]).all():
        return None
    spec = json.loads((output.parent / 'spec.json').read_text(encoding='utf-8'))
    options = spec.get('options') or {}
    axis = 0 if options.get('tensile_direction', 'X') == 'X' else 1
    length = float(options['length_mm'] if axis == 0 else options['width_mm'])
    time = values[:, 0]
    duration = float(options['loading_time_s'])
    curve = np.loadtxt(output / 'force_displacement.csv', delimiter=',', ndmin=2)
    displacement = np.interp(time, curve[:, 0] * duration, curve[:, 1])
    return np.column_stack((displacement, values[:, 3]))


def _neck_position(report, spec):
    value = report.get('necking_position_mm')
    if value is not None:
        return float(value)
    section_index = report.get('section_index')
    if section_index is None:
        return None
    options = spec.get('options') or {}
    axis = 0 if options.get('tensile_direction', 'X') == 'X' else 1
    length = float(options['length_mm'] if axis == 0 else options['width_mm'])
    count = int(options['nx'] if axis == 0 else options['ny'])
    return float(section_index) * length / max(1, count - 1)


def _weights(payload):
    value = payload.get('weights') or {'force': 1., 'neck_position': 1., 'dic_field': 1.}
    if not isinstance(value, dict):
        raise ValueError('联合目标权重必须是对象')
    result = {}
    for key in ('force', 'neck_position', 'dic_field'):
        item = value.get(key, 1.)
        if isinstance(item, bool) or not isinstance(item, (int, float)) or not np.isfinite(item) or item < 0:
            raise ValueError('联合目标权重必须是有限非负数')
        result[key] = float(item)
    if not any(result.values()):
        raise ValueError('联合目标至少需要一个正权重')
    return result


def create_joint_calibration(service, payload):
    if not isinstance(payload, dict):
        raise ValueError('联合校准请求必须是对象')
    source_id = payload.get('source_job_id')
    state, output = _source(service, source_id)
    if state.get('kind') != 'apdl_tension' or state.get('state') != 'completed':
        raise ValueError('联合校准必须来自已完成的 APDL/LS-DYNA 任务')
    summary = state.get('summary') or state.get('result') or {}
    if summary.get('solver_type') != 'ls-dyna':
        raise ValueError('颈缩位置联合校准当前需要 LS-DYNA 断裂后处理结果')
    trial_payload = payload.get('trial')
    dic_payload = payload.get('dic')
    if not isinstance(trial_payload, dict) or not isinstance(dic_payload, dict):
        raise ValueError('请同时提供试验力—位移和 DIC 局部场文件')
    trial, trial_source, trial_path = _finite_pairs(service, trial_payload, 'displacement_column', 'force_column', '试验曲线')
    trial_selection = trial_payload.get('selection') or {}
    trial_units = dict(displacement_unit=_unit(trial_selection.get('displacement_unit'), {'mm', 'm'}, '试验位移'),
                       force_unit=_unit(trial_selection.get('force_unit'), {'N', 'kN'}, '试验力'))
    sim_path = output / 'force_displacement.csv'
    if not sim_path.is_file():
        raise ValueError('缺少真实 force_displacement.csv')
    simulation = np.loadtxt(sim_path, delimiter=',', ndmin=2)[:, [1, 2]]
    force = compare_curves(simulation, trial, **trial_units)
    dic, dic_source, dic_path, dic_selection = _read_dic(service, dic_payload)
    dic_field_type = dic_selection.get('field_type', 'none')
    spec = json.loads((output.parent / 'spec.json').read_text(encoding='utf-8'))
    report_path = output / 'fracture_report.json'
    fracture = json.loads(report_path.read_text(encoding='utf-8')) if report_path.is_file() else {}
    neck_position = _neck_position(fracture, spec)
    if neck_position is None:
        raise ValueError('模拟结果没有颈缩位置；请重新运行带位置后处理的 LS-DYNA 版本')
    position_error = dic[:, 1] - neck_position
    position_rmse = float(np.sqrt(np.mean(position_error ** 2)))
    field_report = dict(comparable=False, field_type=dic_field_type, note='DIC 局部场未进入目标函数')
    if dic_field_type == 'equivalent_plastic_strain' and dic.shape[1] >= 3:
        local = _simulation_local_field(output, dic[:, 0])
        if local is not None:
            predicted = np.interp(dic[:, 0], local[:, 0], local[:, 1])
            residual = predicted - dic[:, 2]
            field_report = dict(comparable=True, field_type=dic_field_type, rmse=float(np.sqrt(np.mean(residual ** 2))),
                                mae=float(np.mean(np.abs(residual))), predicted=predicted.tolist(), observed=dic[:, 2].tolist())
    weights = _weights(payload)
    force_scale = max(float(np.max(np.abs(np.asarray(force['experiment'])[:, 1]))), 1e-12)
    position_scale = max(float(spec['options']['length_mm']), float(spec['options']['width_mm']), 1e-12)
    field_scale = max(float(np.max(np.abs(dic[:, 2]))) if dic.shape[1] >= 3 else 0., 1e-12)
    components = {'force': float(force['rmse_N'] / force_scale),
                  'neck_position': float(position_rmse / position_scale)}
    active_weights = {'force': weights['force'], 'neck_position': weights['neck_position']}
    if field_report['comparable']:
        components['dic_field'] = float(field_report['rmse'] / field_scale)
        active_weights['dic_field'] = weights['dic_field']
    denominator = sum(active_weights.values())
    objective = float(sum(active_weights[key] * components[key] for key in components) / denominator)
    analysis_id = uuid.uuid4().hex[:12]
    target = output / 'analyses' / ('joint_calibration_' + analysis_id)
    target.mkdir(parents=True, exist_ok=False)
    shutil.copy2(trial_path, target / ('trial_original' + trial_path.suffix))
    shutil.copy2(dic_path, target / ('dic_original' + dic_path.suffix))
    shutil.copy2(sim_path, target / 'simulation_original.csv')
    rows = np.column_stack((dic[:, 0], dic[:, 1], position_error,
                            dic[:, 2] if dic.shape[1] >= 3 else np.full(len(dic), np.nan)))
    np.savetxt(target / 'joint_calibration.csv', rows, delimiter=',',
               header='applied_displacement_mm,dic_neck_position_mm,position_residual_mm,dic_local_field', comments='')
    report = {
        'id': analysis_id, 'state': 'completed', 'source_job_id': state['id'],
        'calibration_status': 'joint_evidence_report_only',
        'trial_source': trial_source, 'dic_source': dic_source,
        'simulation_sha256': sha256(sim_path), 'necking_position_mm': neck_position,
        'force': {key: value for key, value in force.items() if key not in {'comparison', 'simulation', 'experiment'}},
        'neck_position': {'observed_median_mm': float(np.median(dic[:, 1])), 'rmse_mm': position_rmse,
                          'max_abs_error_mm': float(np.max(np.abs(position_error)))},
        'dic_field': field_report, 'objective_components': components,
        'weights': weights, 'weighted_objective': objective,
        'note': '该报告联合评价力—位移、颈缩位置和可比的DIC等效塑性应变；不会凭解析误差自动修改材料曲线或 GISSMO 参数。要形成材料标定，需用候选曲线重新求解并复核网格/加载时间敏感性。',
        'warnings': [] if field_report['comparable'] else ['当前 DIC 局部场不是等效塑性应变，未把局部场 RMSE 混入联合目标；颈缩位置仍已计入。'],
    }
    _atomic_json(target / 'joint_calibration_report.json', report)
    try:
        import matplotlib
        matplotlib.use('Agg')
        from matplotlib import pyplot as plt
        fig, axes = plt.subplots(1, 2, figsize=(10, 4.2), constrained_layout=True)
        sim = np.asarray(force['simulation'], dtype=float)
        exp = np.asarray(force['experiment'], dtype=float)
        axes[0].plot(sim[:, 0], sim[:, 1], label='Simulation')
        axes[0].plot(exp[:, 0], exp[:, 1], 'o', ms=3, label='Experiment')
        axes[0].set(xlabel='Displacement (mm)', ylabel='Force (N)', title='Force-displacement')
        axes[1].plot(dic[:, 0], dic[:, 1], 'o-', label='DIC neck position')
        axes[1].axhline(neck_position, color='#b91c1c', ls='--', label='FE neck position')
        axes[1].set(xlabel='Displacement (mm)', ylabel='Position (mm)', title='Necking position')
        for ax in axes:
            ax.grid(alpha=.2); ax.legend(fontsize=7)
        fig.savefig(target / 'joint_calibration.png', dpi=180)
        plt.close(fig)
    except Exception as exc:
        report['warnings'].append('联合校准图绘制失败，CSV/JSON仍保留：' + str(exc))
        _atomic_json(target / 'joint_calibration_report.json', report)
    report['relative_directory'] = target.relative_to(output).as_posix()
    return report


def joint_calibration_file(service, job_id, analysis_id, name):
    service.validate_id(job_id)
    if not re.fullmatch(r'[0-9a-f]{12}', analysis_id) or name not in ALLOWED_FILES:
        raise FileNotFoundError('联合校准成果不存在')
    root = (service.runtime / 'jobs' / job_id / 'outputs' / 'analyses' / ('joint_calibration_' + analysis_id)).resolve()
    path = root / name
    if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(root):
        raise FileNotFoundError('联合校准文件不存在')
    return path

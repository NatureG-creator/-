"""LS-DYNA MAT_024 + GISSMO tension, using the existing frozen hex geometry."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import subprocess
import time
import zipfile

import numpy as np

DEFAULTS = dict(damage_model='none', density_tonne_mm3=7.85e-9,
                loading_time_s=.002, damage_output_intervals=200,
                damage_critical_strain=.12, damage_exponent=2., damage_fading_exponent=2.,
                damage_failure_curve=[[-.333333, 1.], [0., .6], [.333333, .4], [.666667, .25], [1., .2]],
                damage_size_curve=[[.25, 1.], [1., 1.], [4., 1.]],
                damage_parameter_basis='example', neck_imperfection_fraction=0., neck_width_mm=2.,
                damage_damping_per_s=0.)


def normalise_fracture(options):
    result = {key: options.get(key, value) for key, value in DEFAULTS.items()}
    if result['damage_model'] not in ('none', 'gissmo'):
        raise ValueError('损伤模型必须为 none 或 gissmo。')
    if result['damage_model'] == 'none':
        return DEFAULTS.copy()
    if options['material_model'] != 'multilinear_iso' or not options['large_deflection']:
        raise ValueError('GISSMO 拉断需要 MISO 真实塑性曲线并启用大变形。')
    if options['mesh_type'] != 'solid185_hex' or options['boundary_mode'] in {'legacy_recommended', 'single_end_reference_center'}:
        raise ValueError('GISSMO 当前支持八节点六面体及自由泊松/两端夹持边界。')
    if any(b[1] < a[1] for a, b in zip(options['plastic_curve'], options['plastic_curve'][1:])):
        raise ValueError('损伤模式的塑性硬化曲线不能含下降段；软化由 GISSMO 描述。')
    for key in ('density_tonne_mm3', 'loading_time_s', 'damage_critical_strain',
                'damage_exponent', 'damage_fading_exponent', 'neck_width_mm'):
        value = result[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError(key+' 必须是正的有限数值。')
        result[key] = float(value)
    count = result['damage_output_intervals']
    if type(count) is not int or not 20 <= count <= 500:
        raise ValueError('损伤输出间隔数须为 20 至 500 的整数。')
    if result['damage_parameter_basis'] not in ('example', 'calibrated'):
        raise ValueError('请明确损伤参数为示例或试验标定值。')
    damping = result['damage_damping_per_s']
    if isinstance(damping, bool) or not isinstance(damping, (int, float)) or not math.isfinite(damping) or damping < 0:
        raise ValueError('数值阻尼系数必须为有限非负实数。')
    for key in ('damage_failure_curve', 'damage_size_curve'):
        curve = result[key]
        if not isinstance(curve, list) or not 2 <= len(curve) <= 100:
            raise ValueError(key+' 需要 2 至 100 个二维数值点。')
        cleaned = []
        for point in curve:
            if not isinstance(point, (list, tuple)) or len(point) != 2 or any(
                    isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in point):
                raise ValueError(key+' 每点须为两个有限实数。')
            x, y = map(float, point)
            if y <= 0 or (key == 'damage_size_curve' and x <= 0) or (cleaned and x <= cleaned[-1][0]):
                raise ValueError(key+' 横坐标须严格递增，因变量须大于零。')
            cleaned.append([x, y])
        result[key] = cleaned
    if result['damage_critical_strain'] >= min(p[1] for p in result['damage_failure_curve']):
        raise ValueError('耦合临界塑性应变必须小于失效曲线中的最小失效应变。')
    value = result['neck_imperfection_fraction']
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= .1:
        raise ValueError('初始厚度缺陷比例必须在 0 至 0.1 之间。')
    if value and options['corrosion_mode'] != 'flat':
        raise ValueError('初始缺陷仅用于无腐蚀示例；腐蚀模型保留实际形貌。')
    return result


def dyna_capabilities(mapdl_candidates=None):
    if mapdl_candidates is None:
        from .apdl_solver import mapdl_capabilities
        mapdl_candidates = mapdl_capabilities()['candidates']
    candidates = []
    configured = os.environ.get('LSDYNA_BIN', '').strip().strip('"')
    if configured and Path(configured).is_absolute():
        candidates.append(Path(configured))
    for exe in mapdl_candidates:
        candidates.append(Path(exe).parent/'lsdyna_dp.exe')
    executable = next((str(p.resolve()) for p in candidates if p.is_file()), None)
    reader = importlib.util.find_spec('lasso') is not None
    return dict(available=bool(executable and reader), executable=executable, reader_available=reader,
                license_state='unchecked', solver='ls-dyna',
                note='真实求解时验证许可证；后处理需要 requirements-fracture.txt 中的读取库。')


def _curve(identifier, values):
    return ['*DEFINE_CURVE', str(identifier)] + [f'{x:.12g},{y:.12g}' for x, y in values]


def estimated_result_bytes(stats, options):
    return (options['damage_output_intervals']+2)*(stats['element_count']*8*24+stats['node_count']*9)*8


def grip_nodes(geometry):
    o = geometry['options']
    axis = 0 if o['tensile_direction'] == 'X' else 1
    xyz = geometry['nodes'][:, 1:]
    low, high = xyz[:, axis].min(), xyz[:, axis].max()
    fixed = o['grip_length_fixed_mm'] if o['boundary_mode'] == 'clamped_grips' else 0.
    loaded = o['grip_length_loaded_mm'] if o['boundary_mode'] == 'clamped_grips' else 0.
    if fixed+loaded >= high-low:
        raise ValueError('损伤拉伸的两端夹持区域必须分离。')
    return axis, np.flatnonzero(xyz[:, axis] <= low+fixed+1e-9), np.flatnonzero(xyz[:, axis] >= high-loaded-1e-9)


def create_fracture_bundle(geometry, output, provenance):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    o = geometry['options']
    axis, fixed, loaded = grip_nodes(geometry)
    nodes, elements = geometry['nodes'], geometry['elements']
    duration = o['loading_time_s']
    interval = duration/o['damage_output_intervals']
    lines = ['*KEYWORD LONG=Y', '*TITLE', 'Corrosion tension: MAT024 + GISSMO; N-mm-s-tonne',
             '*CONTROL_TERMINATION', f'{duration:.12g}', '*CONTROL_TIMESTEP', '0,0.8',
             '*DATABASE_BINARY_D3PLOT', f'{interval:.12g}',
             '*DATABASE_EXTENT_BINARY', '16,0,3,1,1,1,1,1', '0,0,0,0,1,0', '8',
             '*DATABASE_BNDOUT', f'{interval:.12g},3',
             '*DATABASE_GLSTAT', f'{interval:.12g},3',
             '*DATABASE_SPCFORC', f'{interval:.12g},3',
             '*SECTION_SOLID', '1,2', '*PART', 'Frozen corrosion specimen', '1,1,1',
             '*MAT_PIECEWISE_LINEAR_PLASTICITY',
             f'1,{o["density_tonne_mm3"]:.12g},{o["E_MPa"]:.12g},{o["poisson_ratio"]:.12g},0,0,0,0',
             '0,0,101', '0,0,0,0,0,0,0,0', '0,0,0,0,0,0,0,0',
             '*MAT_ADD_DAMAGE_GISSMO', '1,0,1,0,1',
             f'102,{o["damage_critical_strain"]:.12g},{o["damage_exponent"]:.12g},0,{o["damage_fading_exponent"]:.12g},103',
             '0,0,0,0,0,0,0,0']
    if o['damage_damping_per_s']:
        lines += ['*DAMPING_GLOBAL', f'0,{o["damage_damping_per_s"]:.12g}']
    lines += _curve(101, o['plastic_curve']) + _curve(102, o['damage_failure_curve']) + _curve(103, o['damage_size_curve'])
    # Smooth displacement has zero velocity at both ends; no mass scaling.
    ramp = [(duration*.9*t, o['target_displacement_mm']*(3*t*t-2*t*t*t)) for t in np.linspace(0, 1, 1001)]
    ramp.append((duration, o['target_displacement_mm']))
    ramp.append((duration*1.1, o['target_displacement_mm']))
    lines += _curve(104, ramp) + ['*NODE']
    lines += [f'{int(n[0])},'+','.join(f'{v:.12g}' for v in n[1:]) for n in nodes]
    lines += ['*ELEMENT_SOLID']
    lines += [f'{int(e[0])},1,'+','.join(str(int(v)) for v in e[1:9]) for e in elements]
    lines += ['*SET_NODE_LIST', '1']
    lines += [','.join(str(int(v)) for v in nodes[loaded, 0][i:i+8]) for i in range(0, len(loaded), 8)]
    lines += ['*BOUNDARY_PRESCRIBED_MOTION_SET', f'1,{axis+1},2,104', '*BOUNDARY_SPC_NODE']
    masks = {}
    for index in fixed:
        masks[int(nodes[index, 0])] = [1 if d == axis or o['boundary_mode'] == 'clamped_grips' else 0 for d in range(3)]
    if o['boundary_mode'] == 'clamped_grips':
        for index in loaded:
            masks[int(nodes[index, 0])] = [int(d != axis) for d in range(3)]
    elif o['boundary_mode'] == 'single_end_center':
        for anchor in geometry['stats']['end_center_anchors']:
            for dof in anchor['dofs']:
                masks[anchor['node_id']][{'UX':0,'UY':1,'UZ':2}[dof]]=1
    else:
        # End-plane corners constrain rigid translations/rotation, leaving the gauge free.
        transverse = 1-axis
        corner = fixed[np.argmin(nodes[fixed, 1+transverse])]
        second = fixed[np.argmax(nodes[fixed, 1+transverse])]
        masks[int(nodes[corner, 0])] = [1, 1, 1]
        masks[int(nodes[second, 0])][2] = 1
    lines += [f'{nid},0,'+','.join(map(str, flags))+',0,0,0' for nid, flags in masks.items()]
    lines += ['*END', '']
    (output/'tension.k').write_text('\n'.join(lines), encoding='ascii')
    np.savez_compressed(output/'fracture_geometry.npz', nodes=nodes, elements=elements,
                        fixed=fixed, loaded=loaded)
    notes = ['GISSMO 参数需通过试验标定；单元失效是有限元断裂近似，结果依赖网格和正则化标定。',
             '本模式采用 LS-DYNA 显式大变形、平滑位移加载和全积分六面体，不启用质量缩放；最后10%时间保持位移。',
             '输出保留真实时间（秒）与加载比例；损伤、单元存活和变形取自原生 d3plot。']
    if o['damage_parameter_basis'] == 'example':
        notes.append('当前为演示参数，不能作为钢材或腐蚀试件的定量断裂预测。')
    if o['damage_damping_per_s']:
        notes.append(f'使用数值质量比例阻尼 {o["damage_damping_per_s"]:g} /s，须检查阻尼耗能并减小系数复算；它不是试验标定的材料粘性。')
    text = '# LS-DYNA 损伤断裂输入包\n\n'+'\n\n'.join(notes)+'\n\n运行 tension.k；单位 N、mm、s、tonne。\n'
    (output/'README_zh.md').write_text(text, encoding='utf-8')
    (output/'run_lsdyna.cmd').write_text(
        '@echo off\nsetlocal\nif "%~1"=="" exit /b 2\npushd "%~dp0"\n'
        f'"%~1" i=tension.k ncpu={o["cores"]} memory=100m\n'
        'set "DYNA_CODE=%ERRORLEVEL%"\npopd\nexit /b %DYNA_CODE%\n', encoding='ascii')
    files = ['tension.k', 'fracture_geometry.npz', 'README_zh.md', 'run_lsdyna.cmd']
    manifest = dict(schema_version=1, solver='ls-dyna', options=o, stats=geometry['stats'], provenance=provenance,
                    files={name:hashlib.sha256((output/name).read_bytes()).hexdigest() for name in files})
    (output/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    with zipfile.ZipFile(output/'lsdyna_fracture_input_bundle.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for name in files+['manifest.json']:
            archive.write(output/name, name)
    return dict(analysis='tension', solver_type='ls-dyna', build_state='built', options=o,
                stats=geometry['stats'], provenance=provenance, warnings=geometry['warnings']+notes,
                files=files+['manifest.json', 'lsdyna_fracture_input_bundle.zip'])


def run_fracture(output, options, progress=None):
    from .apdl_solver import mapdl_environment
    from .apdl_process import launch_owned
    from .runner import _atomic_json
    import psutil
    output = Path(output).resolve()
    if any((output/name).exists() for name in ('d3hsp', 'd3plot', 'mapdl_execution.json', 'mapdl_process.json')):
        raise ValueError('已有求解输出，拒绝覆盖；请创建独立任务。')
    manifest = json.loads((output/'manifest.json').read_text(encoding='utf-8'))
    required = estimated_result_bytes(manifest['stats'], options)*1.8
    available = psutil.virtual_memory().available
    if required > available*.8:
        raise RuntimeError(f'预计后处理需要约 {required/1e9:.2f} GB 内存，当前可用 {available/1e9:.2f} GB。请减少输出间隔数或明确调整网格后重新预检；不会自动降采样。')
    capability = dyna_capabilities()
    if not capability['available']:
        raise RuntimeError('LS-DYNA 或 d3plot 读取依赖未安装；输入包已保留。')
    command = [capability['executable'], 'i=tension.k', f'ncpu={options["cores"]}', 'memory=100m']
    record = dict(solver='ls-dyna', state='running', command=command, capabilities=capability)
    started = time.perf_counter()
    process = None
    try:
        with (output/'lsdyna.log').open('wb') as stream:
            process = launch_owned(command, output, stream, env=mapdl_environment(capability['executable']))
            _atomic_json(output/'mapdl_execution.json', record)
            while process.poll() is None:
                if time.perf_counter()-started > options['timeout_seconds']:
                    raise RuntimeError('LS-DYNA 求解超时，已有文件保留。')
                if progress:
                    progress(dict(phase='apdl_solve', message='LS-DYNA 正在计算塑性、颈缩与损伤断裂。', solver_pid=process.pid))
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    pass
            record['exit_code'] = process.poll()
        log = (output/'lsdyna.log').read_text(encoding='utf-8', errors='replace')
        if record['exit_code'] != 0 or not re.search(r'N\s+o\s+r\s+m\s+a\s+l\s+t\s+e\s+r\s+m\s+i\s+n\s+a\s+t\s+i\s+o\s+n', log):
            raise RuntimeError('LS-DYNA 未正常结束；请检查 lsdyna.log 和 d3hsp。')
        record['state'] = 'completed'
    except Exception as exc:
        record.update(state='failed', error=str(exc))
        raise
    finally:
        if process:
            record['cleanup'] = process.close()
        record['elapsed_seconds'] = time.perf_counter()-started
        _atomic_json(output/'mapdl_execution.json', record)
    if process and not record['cleanup'].get('verified_empty'):
        raise RuntimeError('LS-DYNA 求解组未确认清理完成。')
    return record

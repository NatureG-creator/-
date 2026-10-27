"""Local MAPDL discovery, owned batch process control and strict CSV validation.

Process-mocked tests exercise orchestration only. No numerical result is generated
by this module; actual values must come from MAPDL's result file and post macro.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import subprocess
import time

import numpy as np

from .apdl_geometry import normalise_options
from .apdl_process import launch_owned
from .apdl_reports import read_diagnostics_reports


def mapdl_capabilities() -> dict:
    candidates: list[Path] = []
    for name in ('MAPDL_BIN', 'ANSYS_BIN'):
        value = os.environ.get(name, '').strip().strip('"')
        if value:
            path = Path(value)
            if path.is_absolute():
                if path.suffix.lower() == '.exe':
                    candidates.append(path)
                elif path.is_dir():
                    candidates.extend(sorted(path.glob('ansys*.exe'), reverse=True))
    for name, value in sorted(os.environ.items(), reverse=True):
        if re.fullmatch(r'AWP_ROOT\d+', name.upper()) and value:
            root = Path(value.strip().strip('"'))
            if root.is_absolute():
                candidates.extend(sorted((root/'ansys'/'bin'/'winx64').glob('ansys*.exe'), reverse=True))
    # Fixed bounded locations; never recursively traverse project/user input paths.
    for root in (Path('C:/Program Files/ANSYS Inc'), Path('D:/Program Files/ANSYS Inc'),
                 Path('E:/Program Files/ANSYS Inc'), Path('C:/ANSYS Inc'),
                 Path('D:/ANSYS Inc'), Path('E:/ANSYS Inc')):
        if root.is_dir():
            candidates.extend(sorted(root.glob('v*/ansys/bin/winx64/ansys*.exe'), reverse=True))
    found = []
    for candidate in candidates:
        try:
            path = candidate.resolve()
            if path.suffix.lower() == '.exe' and path.is_file() and str(path) not in found:
                found.append(str(path))
        except OSError:
            continue
    warnings = ['仅发现本机MAPDL可执行文件；许可证及实际求解能力尚未验证。'] if found else [
        '未发现MAPDL；可配置MAPDL_BIN或ANSYS_BIN为已安装ANSYS可执行文件的完整路径。']
    from .apdl_fracture import dyna_capabilities
    return {'available': bool(found), 'executable': found[0] if found else None,
            'candidates': found, 'license_state': 'unchecked', 'warnings': warnings,
            'fracture': dyna_capabilities(found)}


def mapdl_environment(executable: str | Path) -> dict:
    """Build an ANSYS-only child environment without changing system PATH."""
    exe = Path(executable).resolve()
    bin_dir = exe.parent
    root = bin_dir.parent.parent.parent
    search_dirs = [
        bin_dir,
        bin_dir / 'BLAS' / 'INTEL', bin_dir / 'BLAS' / 'AMD',
        bin_dir / 'GPU' / 'SIM', bin_dir / 'GPU' / 'NVIDIA',
        bin_dir / 'MPI' / 'StubMPI', bin_dir / 'MPI' / 'MSMPI', bin_dir / 'MPI' / 'IntelMPI',
        root / 'tp' / 'IntelCompiler' / '2023.1.0' / 'winx64',
        root / 'tp' / 'IntelMKL' / '2024.2.3' / 'winx64',
        root / 'licensingclient' / 'winx64',
    ]
    existing = os.environ.get('PATH', '')
    additions = [str(path) for path in search_dirs if path.is_dir()]
    env = dict(os.environ)
    env['AWP_ROOT' + root.name.lstrip('v')] = str(root)
    env['ANSYS' + root.name.lstrip('v') + '_DIR'] = str(root / 'ansys')
    env['PATH'] = os.pathsep.join(dict.fromkeys(additions + [existing]))
    return env


def _stop_process_tree(process) -> dict:
    """Stop a controlled group, including grandchildren after launcher exit."""
    return process.close()


def _launch_mapdl(command, output, stream, executable):
    """Start MAPDL with its isolated environment, retaining old test doubles."""
    environment = mapdl_environment(executable)
    try:
        return launch_owned(command, output, stream, env=environment)
    except TypeError as exc:
        if "unexpected keyword argument 'env'" not in str(exc):
            raise
        return launch_owned(command, output, stream)


def _solver_errors(output: Path) -> list[str]:
    errors = []
    pattern = re.compile(r'\*{3}\s*ERROR\s*\*{3}|SOLUTION\s+(?:DID\s+NOT\s+CONVERGE|NOT\s+CONVERGED)|UNCONVERGED\s+SOLUTION|^\s*APDL_SELF_CHECK_FAILED(?:\b|,)', re.I)
    for name in ('mapdl.out', 'mapdl_launcher.log', 'corrosion.err', 'mesh_quality_report.txt'):
        path = output/name
        if not path.is_file():
            continue
        with path.open('r', encoding='utf-8', errors='replace') as stream:
            for line in stream:
                if pattern.search(line):
                    errors.append(f'{name}: {line.strip()[:500]}')
                    if len(errors) == 20:
                        return errors
    return errors


def run_mapdl(output: Path, options: dict, progress=None, *, allow_recovered=False) -> dict:
    if options.get('damage_model') == 'gissmo':
        from .apdl_fracture import run_fracture
        return run_fracture(output, options, progress)
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    old_names = [name for name in ('force_displacement.csv', 'nodal_results.csv', 'mapdl.out',
                                  'mapdl_launcher.log', 'mapdl_execution.json', 'mapdl_process.json',
                                  'apdl_self_check.csv', 'mesh_quality_report.txt',
                                  'material_coverage_history.csv') if (output/name).exists()]
    old_names += [path.name for path in output.glob('corrosion.*') if path.is_file()]
    if old_names:
        raise ValueError('输出目录已有旧求解文件，拒绝覆盖或复用；请创建新任务：'+', '.join(old_names[:10]))
    start = time.perf_counter()
    record = {'state': 'starting', 'started_at': datetime.now(timezone.utc).isoformat(),
              'warnings': [], 'command': None, 'exit_code': None,
              'log_file': 'mapdl.out', 'launcher_log_file': 'mapdl_launcher.log'}
    process = None
    primary_error = None
    def persist():
        temporary = output/'mapdl_execution.json.tmp'
        temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
        temporary.replace(output/'mapdl_execution.json')
    try:
        o = normalise_options(options)
        capability = mapdl_capabilities()
        record['capabilities'] = capability
        record['warnings'].extend(capability.get('warnings', []))
        if not capability['available']:
            record['state'] = 'unavailable'
            raise RuntimeError('未找到MAPDL可执行文件；输入包已保留，可在已安装ANSYS的计算机运行。')
        if not (output/'main.inp').is_file():
            raise ValueError('缺少 main.inp，必须先生成APDL输入包。')
        if any(ord(char) > 127 for char in str(output)):
            record['warnings'].append('任务路径含非ASCII字符；若该ANSYS版本不支持中文路径，请使用英文工作目录运行输入包。')
        command = [capability['executable'], '-b', '-np', str(o['cores']), '-j', 'corrosion',
                   '-i', 'main.inp', '-o', 'mapdl.out']
        record['command'] = command
        with (output/'mapdl_launcher.log').open('wb') as stream:
            process = _launch_mapdl(command, output, stream, capability['executable'])
            record['supervision'] = dict(process.record)
            record['process_record_file'] = 'mapdl_process.json'
            record['pid'] = process.pid
            record['state'] = 'running'
            persist()
            if progress:
                progress({'phase': 'apdl_solve', 'message': 'MAPDL正在批量求解；许可证是否可用以实际日志为准。', 'solver_pid': process.pid})
            try:
                record['exit_code'] = process.wait(timeout=o['timeout_seconds'])
            except subprocess.TimeoutExpired as exc:
                record['state'] = 'timeout'
                raise RuntimeError(f'MAPDL求解超时（超过 {o["timeout_seconds"]} 秒）；监管组清理状态见执行记录。') from exc
        errors = _solver_errors(output)
        record['solver_errors'] = errors
        recovered = False
        if allow_recovered and (errors or record['exit_code'] != 0):
            from .apdl_outcome import explain_result
            explanation = explain_result(output, dict(options=options, solver=record))
            recovered = explanation['recovered_distortion']
            record['result_explanation'] = explanation
        if record['exit_code'] != 0 and not recovered:
            raise RuntimeError(f'MAPDL进程退出码为 {record["exit_code"]}；请查看结果说明中的具体日志原因和最后完成子步。')
        if errors and not recovered:
            raise RuntimeError('MAPDL日志包含错误或最终不收敛信息：'+errors[0])
        if recovered:
            record['warnings'].append('中途单元畸变后自动切步恢复；日志与曲线均达到目标加载，继续执行结果校核。')
        if not (output/'mapdl.out').is_file() or (output/'mapdl.out').stat().st_size == 0:
            raise RuntimeError('MAPDL未生成非空mapdl.out，不能确认批处理已执行。')
        record['state'] = 'process_finished'
        record['message'] = ('中途畸变试算已切步恢复并达到目标加载；继续核验数值输出，原错误保留为警告。' if recovered
                             else 'MAPDL批处理退出且日志未发现明确错误；仍须验收RST和目标加载步结果。')
        return record
    except BaseException as exc:
        primary_error = exc
        if record['state'] not in {'unavailable', 'timeout'}:
            record['state'] = 'failed'
        record['error'] = f'{type(exc).__name__}: {exc}'
        raise
    finally:
        cleanup_failure = None
        if process is not None:
            try:
                record['cleanup'] = _stop_process_tree(process)
            except BaseException as exc:
                record['cleanup'] = {'state': 'failed', 'verified_empty': False,
                                     'error': f'{type(exc).__name__}: {exc}'}
            if not record['cleanup'].get('verified_empty'):
                cleanup_failure = RuntimeError('MAPDL监管组清理失败：'+record['cleanup'].get('error', '未确认全部进程退出'))
                record.setdefault('error_notes', []).append(str(cleanup_failure))
                if primary_error is None:
                    record['state'] = 'failed'
                    record['error'] = str(cleanup_failure)
                else:
                    primary_error.add_note(str(cleanup_failure))
        record['elapsed_seconds'] = time.perf_counter()-start
        record['finished_at'] = datetime.now(timezone.utc).isoformat()
        try:
            persist()
        except BaseException as persistence_error:
            note = f'最终执行记录未持久化（{output / "mapdl_execution.json"}）：{type(persistence_error).__name__}: {persistence_error}'
            record.setdefault('error_notes', []).append(note)
            record['persistence'] = {'state': 'failed', 'error': str(persistence_error)}
            pending_error = primary_error if primary_error is not None else cleanup_failure
            if pending_error is not None:
                pending_error.add_note(note)
            else:
                record['state'] = 'failed'
                record['error'] = str(persistence_error)
                persistence_error.add_note(note)
                raise
        if cleanup_failure is not None and primary_error is None:
            raise cleanup_failure


def _read_csv(path: Path, columns: int) -> np.ndarray:
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError(f'结果文件不存在或为空：{path.name}。')
    try:
        values = np.loadtxt(path, delimiter=',', ndmin=2, encoding='utf-8-sig')
    except (OSError, ValueError) as exc:
        raise ValueError(f'{path.name} 必须是无表头的 {columns} 列数值CSV。') from exc
    if values.size == 0 or values.shape[1] != columns or not np.isfinite(values).all():
        raise ValueError(f'{path.name} 必须是非空、有限的 {columns} 列数值CSV。')
    return values


def _write_curve_plot(path: Path, curve: np.ndarray) -> None:
    import matplotlib
    matplotlib.use('Agg')
    from matplotlib import pyplot as plt
    fig, axis = plt.subplots(figsize=(6.5, 4), constrained_layout=True)
    try:
        axis.plot(curve[:, 1], curve[:, 2], marker='o', markersize=3)
        axis.set(xlabel='Applied displacement (mm)', ylabel='Loaded-end reaction (N)',
                 title='MAPDL uniaxial tension results')
        axis.grid(alpha=.25)
        fig.savefig(path, dpi=150)
    finally:
        plt.close(fig)


def _result_reference_nodes(output: Path, expected_nodes, count: int, warnings: list,
                            tensile_direction: str = 'X') -> np.ndarray | None:
    """Read the actual bundle's N,id,x,y,z commands, never infer a replacement mesh."""
    supplied = expected_nodes is not None
    try:
        if not supplied:
            rows = []
            for line in (output/'nodes.dat').read_text(encoding='ascii').splitlines():
                fields = line.strip().split(',')
                if len(fields) != 5 or fields[0].upper() != 'N':
                    raise ValueError('nodes.dat 不是 N,id,x,y,z 节点命令格式')
                rows.append([float(value) for value in fields[1:]])
            expected_nodes = rows
        nodes = np.asarray(expected_nodes, dtype=float)
        if nodes.shape != (count, 4) or not np.isfinite(nodes).all():
            raise ValueError('预期节点必须是与网格节点数一致的有限 N×4 ID/XYZ 数组')
        ids = nodes[:, 0]
        if np.any(ids < 1) or np.any(ids != np.floor(ids)) or len(np.unique(ids)) != count:
            raise ValueError('预期网格节点编号必须是唯一正整数')
        if tensile_direction not in {'X', 'Y'}:
            raise ValueError('tensile_direction 只支持 X 或 Y')
        axis_index = 1 if tensile_direction == 'X' else 2
        if np.ptp(nodes[:, axis_index]) <= 0:
            raise ValueError('预期网格的加载方向长度必须为正')
        return nodes[np.argsort(ids)]
    except (OSError, UnicodeError, TypeError, ValueError) as exc:
        if supplied:
            raise ValueError(f'无法核验指定的预期网格节点：{exc}。') from exc
        warnings.append(f'缺少可核验的原始网格节点，节点坐标与边界位移未核验：{exc}。')
        return None


def _check_nodal_geometry(nodal: np.ndarray, expected: np.ndarray, displacement: float,
                          tensile_direction: str = 'X', boundary_mode: str = 'poisson_free', anchors=None) -> None:
    ordered = nodal[np.argsort(nodal[:, 0])]
    if not np.array_equal(ordered[:, 0], expected[:, 0]):
        raise ValueError('节点结果编号与实际输入网格不一致。')
    # Without 1P, Fortran E13.5 writes 0.xxxxxE+nn: five significant digits,
    # with maximum relative rounding of 5e-5 (unlike Python's %13.5E).
    if not np.allclose(ordered[:, 1:4], expected[:, 1:4], rtol=5.1e-5, atol=1e-10):
        raise ValueError('节点结果初始坐标与实际输入网格不一致，超出E13.5五有效位导出精度容差。')
    if tensile_direction not in {'X', 'Y'}:
        raise ValueError('tensile_direction 只支持 X 或 Y。')
    axis_index = 1 if tensile_direction == 'X' else 2
    displacement_index = 4 if tensile_direction == 'X' else 5
    axis = expected[:, axis_index]
    fixed = axis == axis.min()
    loaded = axis == axis.max()
    dof = 'UX' if tensile_direction == 'X' else 'UY'
    fixed_value = -displacement/2 if boundary_mode == 'centered_symmetry' else 0.
    loaded_value = displacement/2 if boundary_mode == 'centered_symmetry' else displacement
    if not np.allclose(ordered[fixed, displacement_index], fixed_value, rtol=5.1e-5, atol=1e-10):
        if boundary_mode == 'centered_symmetry':
            raise ValueError(f'中心对拉起始端{dof}位移应为端到端伸长的负一半。')
        raise ValueError(f'固定端节点{dof}位移与零位移边界不一致。')
    if not np.allclose(ordered[loaded, displacement_index], loaded_value, rtol=5.1e-5, atol=1e-10):
        raise ValueError(f'加载端节点{dof}位移与末步曲线及目标加载位移不一致，超出E13.5五有效位导出精度容差。')
    if boundary_mode == 'single_end_center':
        if not anchors or len(anchors)!=2:raise ValueError('单端中心定位缺少已核验A/B节点记录。')
        for anchor in anchors:
            index=np.flatnonzero(expected[:,0]==anchor['node_id'])
            if len(index)!=1:raise ValueError('单端中心定位A/B节点编号与输入网格不一致。')
            for dof in anchor['dofs']:
                column={'UX':4,'UY':5,'UZ':6}[dof]
                if not np.isclose(ordered[index[0],column],0.,rtol=0.,atol=1e-8*max(1.,abs(displacement))):
                    raise ValueError(f'单端中心定位{anchor["name"]}点{dof}不为零。')
    if boundary_mode == 'centered_symmetry':
        for coord in range(3):
            axis = expected[:,coord+1]
            mask = np.isclose(axis,(axis.min()+axis.max())/2,rtol=0.,atol=1e-10)
            if not mask.any() or not np.allclose(ordered[mask,coord+4],0.,rtol=0.,atol=1e-8*max(1.,abs(displacement))):
                raise ValueError('中心对拉中面法向位移不为零或中面缺少节点。')


def read_tension_results(output: Path, stats: dict, options: dict | None = None, *, expected_nodes=None) -> dict:
    output = Path(output)
    if options is None and (output/'manifest.json').is_file():
        try:
            manifest = json.loads((output/'manifest.json').read_text(encoding='utf-8'))
            if not isinstance(manifest, dict) or not isinstance(manifest.get('options'), dict):
                raise ValueError('manifest options 无效')
            options = manifest['options']
        except (OSError, ValueError) as exc:
            raise ValueError('无法从 manifest.json 读取原始求解参数。') from exc
    o = normalise_options(options or {})
    if o.get('damage_model') == 'gissmo':
        from .apdl_fracture_results import read_fracture_results
        return read_fracture_results(output, stats, o)
    rst = output/'corrosion.rst'
    if not rst.is_file() or rst.stat().st_size == 0:
        raise ValueError('缺少非空 corrosion.rst，不能把CSV视为已验证求解结果。')
    curve = _read_csv(output/'force_displacement.csv', 6)
    time_values, displacement, loaded, fixed, strain, stress = curve.T
    length = float(o['length_mm'] if o['tensile_direction'] == 'X' else o['width_mm'])
    area = float(stats['nominal_area_mm2'])
    if not math.isfinite(length) or not math.isfinite(area) or length <= 0 or area <= 0:
        raise ValueError('用于验收的标距和名义面积必须为正的有限数值。')
    if np.any(time_values < 0) or np.any(time_values > 1+1e-6) or np.any(np.diff(time_values) <= 0):
        raise ValueError('结果集时间必须递增且位于静力加载步 0 至 1 内。')
    if not math.isclose(float(time_values[-1]), 1., rel_tol=0, abs_tol=1e-6):
        raise ValueError('结果未达到 TIME=1，可能是求解中断或未收敛的部分结果。')
    if not math.isclose(float(displacement[-1]), o['target_displacement_mm'], rel_tol=1e-5, abs_tol=1e-8):
        raise ValueError('末步位移未达到目标加载位移，不能认定完整求解成功。')
    if np.any(displacement < -1e-8) or np.any(np.diff(displacement) < -1e-8):
        raise ValueError('单调拉伸加载位移出现负值或回退，请核对输入与结果来源。')
    if not np.allclose(displacement, time_values*o['target_displacement_mm'], rtol=1e-5, atol=1e-8):
        raise ValueError('中间加载步位移与 KBC=0、TIME=1 的线性加载规则不一致。')
    residual = np.abs(loaded+fixed)
    force_scale = np.maximum(np.abs(loaded), np.abs(fixed))
    if np.any(residual > np.maximum(1e-4, force_scale*.01)):
        raise ValueError('两端反力不平衡，超出 1% 或 1e-4 N 验收阈值。')
    if not np.allclose(strain, displacement/length, rtol=1e-6, atol=1e-10):
        raise ValueError('工程应变与位移/原始标距不一致。')
    if not np.allclose(stress, loaded/area, rtol=1e-6, atol=1e-8):
        raise ValueError('名义应力与加载端反力/原始面积不一致。')
    rst_validation = {'state': 'unverified',
                      'reason': '仅确认corrosion.rst非空；尚未读取RST结果集并与CSV交叉核验，不能据此证明真实数值结果完整或一致。'}
    warnings = [rst_validation['reason']]
    reference_nodes = _result_reference_nodes(output, expected_nodes, int(stats['node_count']), warnings,
                                               o['tensile_direction'])
    nodal_coordinates = None
    nodal_displacements = None
    nodal_summary = None
    files = ['force_displacement.csv', 'corrosion.rst']
    reports = read_diagnostics_reports(output, stats, o, time_values, reference_nodes)
    if reports is not None:
        warnings.extend(reports['warnings'])
        files.extend(reports['files'])
    if (output/'nodal_results.csv').exists():
        nodal = _read_csv(output/'nodal_results.csv', 9)
        ids = nodal[:, 0]
        expected_ids = reference_nodes[:, 0] if reference_nodes is not None else np.arange(1, int(stats['node_count'])+1)
        if len(ids) != int(stats['node_count']) or not np.array_equal(np.sort(ids), expected_ids):
            raise ValueError('节点结果的编号、唯一性或节点数量与输入网格不一致。')
        if reference_nodes is not None:
            _check_nodal_geometry(nodal, reference_nodes, float(displacement[-1]),
                                  o['tensile_direction'], o['boundary_mode'], stats.get('end_center_anchors'))
            nodal_coordinates = nodal_displacements = True
        if np.any(nodal[:, 7:] < -1e-8):
            raise ValueError('等效应力或等效塑性应变不应为负。')
        if o['material_model'] == 'elastic' and np.any(np.abs(nodal[:, 8]) > 1e-8):
            raise ValueError('弹性材料出现非零塑性应变，请核对节点结果来源。')
        nodal_summary = {'node_count': len(ids),
                         'max_displacement_mm': float(np.linalg.norm(nodal[:, 4:7], axis=1).max()),
                         'max_equivalent_stress_mpa': float(nodal[:, 7].max()),
                         'max_equivalent_plastic_strain': float(nodal[:, 8].max()),
                         'note': 'SEQV/EPPL为平均节点值，不代表积分点峰值；节点CSV采用无1P的E13.5格式，以五有效位导出。'}
        files.append('nodal_results.csv')
    elif o['export_full_field']:
        raise ValueError('已请求完整节点场，但未找到 nodal_results.csv，不能将部分输出认定为完整成功。')
    else:
        warnings.append('未导出节点场，节点坐标与边界位移未核验。')
    # A balanced pair of zero forces still satisfies equilibrium. Treat forces
    # below the existing absolute equilibrium tolerance as unresolved response.
    nonzero_response = bool(abs(loaded[-1]) > 1e-4)
    if not nonzero_response:
        warnings.append('末步承载反力为零或不超过1e-4 N，无法确认有效拉伸响应，请复核约束、载荷和结果来源。')
    significant = loaded[np.abs(loaded) > 1e-4]
    if np.any(significant > 0) and np.any(significant < 0):
        nonzero_response = False
        warnings.append('单调拉伸的显著反力发生符号反转，响应异常，需要复核；未预设加载端反力的正负号。')
    stiffness = float(loaded[-1]/displacement[-1])
    analytic = None
    if o['corrosion_mode'] == 'flat' and o['material_model'] == 'elastic' and o['boundary_mode'] == 'poisson_free' and not o['large_deflection']:
        reference = o['E_MPa']*area/length
        analytic = {'stiffness_n_per_mm': reference,
                    'force_n': reference*o['target_displacement_mm'],
                    'stiffness_relative_error': abs(abs(stiffness)-reference)/reference,
                    'comparison': '比较刚度幅值；CSV与汇总反力保留求解器原始符号。',
                    'scope': '小变形弹性、无腐蚀、自由泊松伸缩的EA/L与EAδ/L参考。'}
        if analytic['stiffness_relative_error'] > .05:
            warnings.append('平板结果相对EA/L误差超过5%，应检查材料、约束及网格后再用于研究。')
    curve_plot = {'state': 'disabled'}
    if o['export_force_displacement_plot']:
        try:
            _write_curve_plot(output/'load_displacement.png', curve)
            files.append('load_displacement.png')
            curve_plot = {'state': 'completed', 'file': 'load_displacement.png'}
        except Exception as exc:
            curve_plot = {'state': 'failed', 'error': f'{type(exc).__name__}: {exc}'}
            warnings.append(f'曲线预览失败但数值结果已保留：{type(exc).__name__}: {exc}')
    return {**({'diagnostics': reports['diagnostics']} if reports is not None else {}),
            'solve_state': 'solved', 'point_count': len(curve), 'curve': curve.tolist(),
            'tensile_direction': o['tensile_direction'], 'axial_length_mm': length,
            'validation_state': 'needs_review',
            'curve_columns': ['time', 'displacement_mm', 'loaded_reaction_n', 'fixed_reaction_n',
                              'engineering_strain', 'nominal_stress_mpa'],
            'final_displacement_mm': float(displacement[-1]), 'final_load_n': float(loaded[-1]),
            'peak_load_n': float(np.max(loaded)), 'peak_nominal_stress_mpa': float(np.max(stress)),
            'secant_stiffness_n_per_mm': stiffness,
            'checks': {'target_time': True, 'target_displacement': True, 'reaction_balance': True,
                       'engineering_strain': True, 'nominal_stress': True, 'nonempty_rst': True,
                       'ramped_displacement': True,
                       'nodal_coordinates': nodal_coordinates, 'nodal_displacements': nodal_displacements,
                       'nonzero_response': nonzero_response, 'rst_consistency': None,
                       'analytic_reference': analytic['stiffness_relative_error'] <= .05 if analytic else None,
                       'max_reaction_residual_n': float(residual.max()),
                       'reaction_relative_tolerance': .01, 'reaction_absolute_tolerance_n': 1e-4},
            'nodal_summary': nodal_summary, 'analytic_reference': analytic, 'rst_validation': rst_validation,
            'curve_plot': curve_plot,
            'warnings': warnings, 'files': files}

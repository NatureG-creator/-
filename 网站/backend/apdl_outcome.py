"""Read-only explanations of loading completion, log events and result limits."""
from functools import lru_cache
import math
from pathlib import Path
import re

import numpy as np


_ERROR = re.compile(r'\*{3}\s*ERROR\s*\*{3}|SOLUTION\s+(?:DID NOT CONVERGE|NOT CONVERGED|TERMINATED)|UNCONVERGED SOLUTION|^\s*APDL_SELF_CHECK_FAILED|\*{3}\s*FATAL', re.I)
_COMPLETE = re.compile(r'LOAD STEP\s+(\d+)\s+SUBSTEP\s+(\d+)\s+COMPLETED\.', re.I)
_DETAILS = {
    'distortion': ('试算中出现单元严重畸变', '某次迭代的单元变形过大；试算报错不一定表示最终加载未完成。', '检查问题单元和加载步长；若已自动切步恢复，保留这一警告，无需仅因此重算。'),
    'material': ('塑性应变超出材料曲线范围', '局部变形超过已输入的多线性硬化曲线范围，后段材料响应缺少数据支持。', '核对真实应力—塑性应变数据与局部应变；补充有依据的材料数据，或缩小研究的加载范围。'),
    'convergence': ('非线性迭代或加载步未收敛', '某次试算未满足收敛条件，需要检查其后是否切步并恢复。', '核对最后完成子步、材料、约束和网格，再调整子步；不要仅放宽收敛容差。'),
    'license': ('许可证或求解器启动异常', '日志提示许可证获取或求解器启动存在问题。', '检查 ANSYS 许可证服务和日志中的具体授权错误后再运行。'),
    'self_check': ('模型导入或边界自检失败', '节点、单元或端面组件与预期不一致。', '检查原始输入和自检 CSV，修正后重新建模。'),
    'performance': ('内存或磁盘读写影响求解速度', 'ANSYS 提示实际耗时明显大于 CPU 计算时间，可能存在内存不足或磁盘读写瓶颈；这不是最终不收敛的证据。', '结合任务内存和磁盘用量检查瓶颈，再考虑减少输出或调整资源。'),
    'output': ('结果文件读写异常', '求解器无法读取或写入所需文件，已有数值结果可能不完整。', '检查日志指出的文件、目录权限、磁盘空间和文件占用。'),
    'constraints': ('检查时尚未发现 D 位移约束', '发出此警告时，模型尚未定义 D 命令约束；若边界在网格检查之后才施加，不表示最终模型一定缺少约束。', '核对后续 boundary.mac、端部组件自检和最终位移/反力；不要仅凭这条早期警告追加约束。'),
    'other': ('求解器报告了其他异常', '保留的日志包含尚未自动解释的警告或错误。', '查看下方原始证据及对应日志上下文；不能仅凭退出码确定根因。'),
}


def _category(text):
    text = text.lower()
    for key, pattern in (
        ('self_check', r'apdl_self_check_failed'),
        ('distortion', r'distort|inside out|negative volume'),
        ('material', r'plastic strain.*outside|hardening table|negative slope'),
        ('license', r'license|licensing|flexnet'),
        ('performance', r'elapsed time exceeds the cpu time|lack of physical memory|slow hard drive'),
        ('output', r'cannot (?:write|read|open)|unable to (?:write|read|open)|disk space'),
        ('constraints', r'no constraints have been defined|unconstrained|rigid body motion'),
        ('convergence', r'not converg|did not converg|unconverged|not completed|too many equilibrium'),
    ):
        if re.search(pattern, text):
            return key
    return 'other'


@lru_cache(maxsize=24)
def _scan(stamps):
    issues, errors = {}, []
    last_complete, last_time, last_bisection, last_main_error = None, None, 0, 0
    bisections = 0
    for path_text, _, _ in stamps:
        path = Path(path_text)
        block = None

        def finish():
            if block is None:
                return
            text = ' '.join(block['context'])
            category = _category(text)
            if block['severity'] == 'error':
                errors.append((path.name, block['line'], category))
            key = (category, block['severity'])
            if key not in issues:
                title, cause, action = _DETAILS[category]
                issues[key] = dict(category=category, severity=block['severity'], title=title,
                                   cause=cause, action=action, count=0,
                                   evidence=dict(file=path.name, line=block['line'], text=text[:1600]))
            issues[key]['count'] += 1

        with path.open(encoding='utf-8', errors='replace') as stream:
            for number, raw in enumerate(stream, 1):
                line = raw.strip()
                if ((block is None or len(block['context']) >= 14) and '***' not in line
                        and 'APDL_SELF_CHECK_FAILED' not in line
                        and 'SOLUTION' not in line.upper()):
                    continue
                main = path.name == 'mapdl.out'
                completed = _COMPLETE.search(line) if main else None
                if completed:
                    last_complete = dict(file=path.name, line=number,
                                         load_step=int(completed[1]), substep=int(completed[2]))
                    last_time = None
                time_match = re.search(r'^\*{3}\s*TIME\s*=\s*([\d.Ee+\-]+)', line) if main else None
                if time_match and last_complete and number-last_complete['line'] <= 3:
                    last_time = float(time_match[1])
                if main and 'BEGIN BISECTION NUMBER' in line:
                    last_bisection = number
                    bisections += 1
                severity = 'error' if _ERROR.search(line) else 'warning' if re.search(r'\*{3}\s*WARNING\s*\*{3}', line, re.I) else None
                if severity:
                    finish()
                    block = dict(line=number, severity=severity, context=[line])
                    if main and severity == 'error':
                        last_main_error = number
                elif block is not None and len(block['context']) < 14:
                    block['context'].append(line)
        finish()
    recovered = bool(errors and last_main_error and last_complete
                     and all(category == 'distortion' for _, _, category in errors)
                     and last_main_error < last_bisection < last_complete['line'])
    return dict(issues=list(issues.values()), errors=errors, last_complete=last_complete,
                last_time=last_time, bisections=bisections, recovered_distortion=recovered)


def explain_result(output, summary, state=None, error=None):
    """Enrich a terminal task without rewriting its historical status or files."""
    if summary.get('solver_type') == 'ls-dyna':
        results = summary.get('results') or {}
        complete = summary.get('solve_state') == 'solved' and results.get('validation_state') == 'native_binary_cross_checked'
        return dict(loading_complete=complete, outcome='completed_with_warnings' if complete else 'incomplete',
                    title='LS-DYNA 加载完成 · 请检查损伤与断裂报告' if complete else 'LS-DYNA 未完成或尚未通过后处理',
                    conclusion='已交叉核对原生网格、位移、反力、能量及单元存活状态；损伤与完整断开分别判定。' if complete else str(error or summary.get('error') or '尚无完整原生结果。'),
                    original_state=state, original_error=error, failure_stage=summary.get('failure_stage'),
                    note='LS-DYNA 显式结果不按 MAPDL 静力日志或线性加载规则判断。')
    output = Path(output)
    options = summary.get('options') or {}
    paths = [output/name for name in ('mapdl.out', 'mapdl_launcher.log', 'mesh_quality_report.txt')]
    paths.extend(sorted(output.glob('corrosion*.err')))
    stamps = tuple((str(p), p.stat().st_mtime_ns, p.stat().st_size) for p in paths if p.is_file())
    scan = _scan(stamps)
    execution = summary.get('solver') or {}
    exit_code = execution.get('exit_code', summary.get('exit_code'))
    target = options.get('target_displacement_mm')
    curve, curve_error = None, None
    path = output/'force_displacement.csv'
    if path.is_file():
        try:
            if path.stat().st_size > 32_000_000:
                raise ValueError('曲线文件超过 32 MB 读取上限')
            curve = np.loadtxt(path, delimiter=',', ndmin=2)
            if curve.shape[1] != 6 or not len(curve) or not np.isfinite(curve).all():
                raise ValueError('曲线必须是无表头的六列有限数值')
            if np.any(np.diff(curve[:, 0]) <= 0) or np.any(curve[:, 0] < 0) or np.any(curve[:, 0] > 1+1e-6):
                raise ValueError('曲线加载比例必须递增且位于 0 到 1')
        except (OSError, ValueError) as exc:
            curve_error, curve = str(exc), None
    final_time = float(curve[-1, 0]) if curve is not None else None
    displacement = float(curve[-1, 1]) if curve is not None else None
    target_reached = bool(isinstance(target, (int, float)) and math.isfinite(target) and target > 0
                          and curve is not None and math.isclose(final_time, 1., abs_tol=1e-6)
                          and math.isclose(displacement, target, rel_tol=1e-5, abs_tol=1e-8)
                          and np.allclose(curve[:, 1], curve[:, 0]*target, rtol=1e-5, atol=1e-8))
    rst = output/'corrosion.rst'
    loading_complete = bool(target_reached and scan['last_time'] is not None
                            and math.isclose(scan['last_time'], 1., abs_tol=1e-6)
                            and rst.is_file() and rst.stat().st_size > 0)
    safe_recovery = bool(loading_complete and scan['recovered_distortion'] and exit_code in (0, 1)
                         and not (output/'command_revision.json').exists())
    unhandled_errors = bool(scan['errors']) and not safe_recovery
    run_mode = summary.get('run_mode')
    failure = error or summary.get('error')
    if loading_complete:
        title = '目标加载已完成 · 存在警告，结果待复核' if scan['issues'] else '目标加载已完成 · 结果待复核'
        outcome = 'completed_with_warnings'
        conclusion = '日志确认最终子步收敛，曲线达到目标位移，且存在非空 RST。数值加载已完成；这不等于材料、网格和结果文件均已验收通过。'
        if unhandled_errors or exit_code not in (None, 0, 1):
            title = '目标加载已达到 · 仍有未解释错误'
            outcome = 'needs_review'
        if summary.get('failure_stage') == 'postprocess':
            title = '目标加载已完成 · 后处理或结果校核失败'
    elif summary.get('build_state') == 'built' and (run_mode == 'build' or summary.get('solve_state') in ('built', 'not_requested')):
        title, outcome = '输入包已生成 · 未执行求解', 'not_requested'
        conclusion = '本任务只生成模型和命令文件，没有数值求解结果。'
    else:
        title, outcome = '任务未完成或尚不能确认完成目标加载', 'incomplete'
        conclusion = '需同时确认最后收敛子步、TIME=1、目标位移和结果文件；目前证据不足，已保存的曲线仅表示已有加载过程。'
    issues = [dict(item) for item in scan['issues']]
    for item in issues:
        if item['category'] == 'distortion' and safe_recovery:
            item.update(title='中途单元畸变，切步后已恢复收敛', severity='warning',
                        impact='ANSYS 缩小步长后继续完成加载；该试算错误不再单独判定为最终求解失败。')
        else:
            item['impact'] = '目标加载已达到，仍需审查此异常对结果的影响。' if loading_complete else '需结合最后完成子步判断；不能把已有文件当作完整求解成功。'
    material = output/'material_coverage_history.csv'
    limit = (options.get('plastic_curve') or [[None]])[-1][0] if options.get('material_model') == 'multilinear_iso' else None
    material_screening = None
    if material.is_file() and material.stat().st_size <= 32_000_000 and isinstance(limit, (int, float)):
        try:
            history = np.loadtxt(material, delimiter=',', ndmin=2)
            if history.shape[1] == 6 and len(history) and np.isfinite(history).all():
                flags = np.flatnonzero(history[:, 1] > limit*(1+5.1e-11))
                first = history[flags[0]] if len(flags) else None
                material_screening = dict(limit=limit, maximum=float(history[:, 1].max()),
                    first_time=float(first[0]) if first is not None else None,
                    first_element=int(first[2]) if first is not None else None,
                    first_centroid_mm=first[3:].tolist() if first is not None else None)
        except (OSError, ValueError):
            pass
    return dict(schema_version=1, outcome=outcome, title=title, conclusion=conclusion,
                loading_complete=loading_complete, recovered_distortion=safe_recovery,
                original_state=state, original_error=failure, exit_code=exit_code,
                failure_stage=summary.get('failure_stage'),
                target_displacement_mm=target, final_displacement_mm=displacement,
                final_load_N=float(curve[-1, 2]) if curve is not None else None,
                final_time=final_time, point_count=len(curve) if curve is not None else 0,
                last_converged=scan['last_complete'], log_final_time=scan['last_time'],
                bisection_count=scan['bisections'], issues=issues, curve_error=curve_error,
                material_screening=material_screening,
                diagnostic_files=[name for name in ('mesh_quality_report.txt', 'apdl_self_check.csv')
                                  if (output/name).is_file() and (output/name).stat().st_size > 0],
                note='根据当前保存的日志和 CSV 只读复核；保留原任务状态与原始文件。RST 二进制内容和积分点材料覆盖尚未独立核验。')

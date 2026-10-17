"""Native MAPDL last-set contour export, independent of the physical solve."""
from datetime import datetime, timezone
from pathlib import Path
import time

from .apdl_process import launch_owned
from .runner import _atomic_json


RESTORE_COMMANDS = """/CLEAR,START
RESUME,'../corrosion',db
/FILNAME,contours
/POST1
FILE,'../corrosion',rst
SET,LAST
RSYS,0
CSYS,0
ALLSEL,ALL
/INPUT,plots,mac
FINISH
/EXIT,NOSAVE
"""


def _fields(material_model):
    fields = [
        ('displacement', '总位移', 'mm', 'U,SUM', 'Total displacement (mm)'),
        ('equivalent_stress', '节点平均等效应力', 'MPa', 'S,EQV', 'Equivalent stress (MPa), nodal avg'),
    ]
    if material_model != 'elastic':
        fields.append(('equivalent_plastic_strain', '节点平均等效塑性应变', '1', 'EPPL,EQV',
                       'Equivalent plastic strain (1), nodal avg'))
    return fields


def contour_commands(material_model: str) -> str:
    lines = [
        '! Native last-set plots only; no solution or database update.',
        '! N-mm-MPa; deformed geometry at true scale 1; FULL nodal averaging.',
        '/GRAPHICS,FULL', '/DSCALE,1,1', '/VIEW,1,1,-2,2', '/VUP,1,Z',
        '/EDGE,1,0', '/GFILE,1800', '/AUTO,1',
        '/RGB,INDEX,100,100,100,0', '/RGB,INDEX,0,0,0,15', '/SHOW,PNG',
    ]
    for _, _, _, item, title in _fields(material_model):
        lines += ['/TITLE,'+title+'; last set; deformation x1',
                  'PLNSOL,'+item]
    return '\n'.join(lines+['/SHOW,CLOSE', ''])


def render_result_contours(output: Path, options: dict, progress=None) -> dict:
    """Restore parent DB/RST in a fresh child folder; never overwrite old exports.

    Plot failures are a separate report and do not invalidate a completed solve.
    The returned image list contains only files verified after MAPDL exits.
    """
    from PIL import Image
    from .apdl_solver import mapdl_capabilities, _solver_errors

    output = Path(output).resolve()
    work = output/'contour_plots'
    if work.exists():
        raise ValueError('已有云图输出目录，拒绝覆盖；请保留原图后使用新目录。')
    work.mkdir()
    start = time.perf_counter()
    model = options.get('material_model', 'elastic')
    report = dict(state='running', plots=[], source_result='corrosion.rst',
                  started_at=datetime.now(timezone.utc).isoformat(),
                  result_set='last', deformation_scale=1,
                  averaging='FULL nodal averaged S,EQV and EPPL,EQV; not integration-point peaks',
                  files=['contour_plots/plot_report.json'])
    process = None
    try:
        for name in ('corrosion.db', 'corrosion.rst'):
            if not (output/name).is_file() or (output/name).stat().st_size == 0:
                raise ValueError('云图需要已有非空 '+name+'；不自动重新求解。')
        capability = mapdl_capabilities()
        if not capability['available']:
            raise RuntimeError('未找到 MAPDL，无法进行原生云图后处理。')
        (work/'plots.mac').write_text(contour_commands(model), encoding='ascii')
        (work/'restore_plots.inp').write_text(RESTORE_COMMANDS, encoding='ascii')
        report['files'] += ['contour_plots/plots.mac', 'contour_plots/restore_plots.inp']
        command = [capability['executable'], '-b', '-np', str(options.get('cores', 2)),
                   '-j', 'contours', '-i', 'restore_plots.inp', '-o', 'mapdl.out']
        report['command'] = command
        if progress:
            progress({'phase': 'apdl_post', 'message': '正在读取已有末步结果并导出 MAPDL 云图，不重新求解。'})
        with (work/'mapdl_launcher.log').open('wb') as stream:
            process = launch_owned(command, work, stream)
            report['pid'] = process.pid
            report['exit_code'] = process.wait(timeout=600)
        if report['exit_code'] != 0:
            raise RuntimeError('MAPDL 云图进程退出码 '+str(report['exit_code']))
        errors = _solver_errors(work)
        if errors:
            raise RuntimeError(errors[0])
        if not (work/'mapdl.out').is_file() or not (work/'mapdl.out').stat().st_size:
            raise RuntimeError('缺少 MAPDL 后处理日志。')
        generated = sorted(work.glob('contours*.png'))
        fields = _fields(model)
        if len(generated) != len(fields):
            raise RuntimeError(f'原生云图数量不完整：预期 {len(fields)} 张，实际 {len(generated)} 张。')
        for path in generated:
            with Image.open(path) as picture:
                if min(picture.size) < 32 or picture.format != 'PNG':
                    raise ValueError('MAPDL 图像尺寸或格式无效：'+path.name)
                picture.verify()
        for path, (key, label, unit, item, _) in zip(generated, fields):
            destination = work/(key+'.png')
            path.rename(destination)
            name = 'contour_plots/'+destination.name
            report['plots'].append(dict(file=name, label=label, unit=unit, command='PLNSOL,'+item))
            report['files'].append(name)
        report['state'] = 'completed'
    except Exception as exc:
        report.update(state='failed', error=f'{type(exc).__name__}: {exc}', plots=[])
    finally:
        if process is not None:
            try:
                report['cleanup'] = process.close()
            except Exception as exc:
                report['cleanup'] = dict(verified_empty=False, error=str(exc))
            if not report['cleanup'].get('verified_empty'):
                report.update(state='failed', error='云图进程监管组未确认退出。', plots=[])
        report['elapsed_seconds'] = time.perf_counter()-start
        report['finished_at'] = datetime.now(timezone.utc).isoformat()
        _atomic_json(work/'plot_report.json', report)
    return report

"""Open existing local MAPDL databases in isolated interactive sessions."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import uuid

from .apdl_solver import mapdl_capabilities, mapdl_environment


def _apdl_text_encoding():
    """Use Windows' active code page so MAPDL can read Unicode-free commands with local paths."""
    return 'mbcs' if os.name == 'nt' else 'utf-8'

VIEWS = (
    ('model', '构件外形', 'EPLOT', '未变形外表面'),
    ('mesh', '有限元网格', 'EPLOT', '未变形实体网格'),
    ('displacement', '总位移', 'PLNSOL,U,SUM', 'mm；真实比例变形'),
    ('stress', '等效应力', 'PLNSOL,S,EQV', 'MPa；节点平均'),
    ('plastic_strain', '等效塑性应变', 'PLNSOL,EPPL,EQV', '无量纲；节点平均'),
)


def viewer_source(service, job_id):
    service.validate_id(job_id)
    job = service.get_job(job_id)
    if job.get('kind') != 'apdl_tension' or job.get('state') not in {'completed', 'failed', 'interrupted', 'stopped'}:
        raise ValueError('请选择已结束的有限元任务')
    root = service.runtime/'jobs'/job_id/'outputs'
    for name in ('corrosion.db', 'corrosion.rst'):
        path = root/name
        if path.exists() and (path.is_symlink() or not path.resolve().is_relative_to(root.resolve())):
            raise ValueError('查看文件必须在源任务输出目录内')
    if not (root/'corrosion.db').is_file() or not (root/'corrosion.db').stat().st_size:
        raise ValueError('本任务未保留 corrosion.db，无法打开交互模型')
    summary = job.get('summary') or {}
    options = summary.get('options') or job.get('spec', {}).get('options', {})
    has_results = (root/'corrosion.rst').is_file() and (root/'corrosion.rst').stat().st_size > 0
    custom = summary.get('execution_mode') == 'custom_commands' or job.get('spec', {}).get('execution_mode') == 'custom_commands'
    plastic = not custom and options.get('material_model') in {'bilinear_iso', 'multilinear_iso'}
    views = [dict(id=key, label=label, note=note) for key, label, _, note in VIEWS
             if (has_results or key in {'model', 'mesh'}) and (key != 'plastic_strain' or plastic)]
    note = '读取最后一个已保存结果集；可在 APDL 中旋转、缩放和切换显示。'
    if summary.get('result_explanation', {}).get('loading_complete'):
        note += ' 日志与曲线已确认达到目标加载；材料、网格及 RST 内容仍需复核。'
    elif summary.get('solve_state') != 'solved' or job.get('state') != 'completed':
        note += ' 此任务未确认完整求解，已有结果可能仅为部分载荷。'
    if custom:
        note += ' 自定义命令的材料与单位需自行核对。'
    return dict(id=job_id, name=job.get('display_name') or job.get('case_name') or job_id,
                views=views, note=note), root


def viewer_jobs(service):
    jobs = []
    folders = sorted((service.runtime/'jobs').iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
    for folder in folders:
        if len(jobs) >= 100:
            break
        if not folder.is_dir() or not (folder/'outputs/corrosion.db').is_file():
            continue
        try:
            jobs.append(viewer_source(service, folder.name)[0])
        except (ValueError, FileNotFoundError):
            continue
    return dict(jobs=jobs, available=mapdl_capabilities()['available'])


def open_viewer(service, job_id, payload):
    source, output = viewer_source(service, job_id)
    view = payload.get('view', 'stress')
    if view not in {item['id'] for item in source['views']}:
        raise ValueError('该任务不支持所选视图，请刷新后重新选择')
    capability = mapdl_capabilities()
    if not capability['available']:
        raise ValueError('未找到本机 MAPDL，请先安装或配置 MAPDL_BIN')
    session = service.runtime/'apdl_viewers'/uuid.uuid4().hex[:16]
    session.mkdir(parents=True)
    job_name = 'vw_' + session.name[:10]
    # Keep MAPDL command paths ASCII-only. The runtime root may contain Chinese
    # directory names, while the session-relative path does not.
    result_base = Path(os.path.relpath(output/'corrosion', session)).as_posix()
    lines = ['/CLEAR,NOSTART', f"RESUME,'{result_base}',db", 'FINISH', '/FILNAME,viewer',
             '/VIEW,1,1,-2,2', '/VUP,1,Z', '/AUTO,1']
    buttons = {'model': 'MODEL', 'mesh': 'MESH', 'displacement': 'DISP',
               'stress': 'STRESS', 'plastic_strain': 'PLASTIC'}
    for field in source['views']:
        key = field['id']
        macro_name = 'v_'+key
        display = ['FINISH']
        if key not in {'model', 'mesh'}:
            display += ['/POST1', f"FILE,'{result_base}',rst", 'SET,LAST', 'RSYS,0',
                        '/PLOPTS,INFO,1', '/PLOPTS,LEG1,1']
        display += ['/SHOW,WIN32', 'CSYS,0', 'ALLSEL,ALL', '/GRAPHICS,FULL', '/DSCALE,1,1',
                    '/EDGE,1,'+('1' if key == 'model' else '0'),
                    '/TITLE,Corrosion viewer - '+key,
                    next(item[2] for item in VIEWS if item[0] == key), '/REPLOT']
        (session/(macro_name+'.mac')).write_text(
            '\n'.join(display)+'\n', encoding=_apdl_text_encoding())
        lines.append(f"*ABBR,{buttons[key]},'/INPUT,{macro_name},mac'")
    lines.append('/INPUT,v_'+view+',mac')
    (session/'viewer.inp').write_text('\n'.join(lines)+'\n', encoding=_apdl_text_encoding())
    (session/'start.ans').write_text('/INPUT,viewer,inp\n', encoding=_apdl_text_encoding())
    executable = Path(capability['executable'])
    command = [str(executable), '-g', '-d', 'win32', '-dir', str(session),
               '-np', '1', '-j', job_name, '-s', 'read']
    record = dict(state='launch_requested', source_job_id=job_id, view=view,
                  started_at=datetime.now(timezone.utc).isoformat(), command=command,
                  session_directory=str(session), note=source['note'])
    try:
        with (session/'launcher.log').open('wb') as stream:
            process = subprocess.Popen(command, cwd=str(session), stdin=subprocess.DEVNULL,
                                       stdout=stream, stderr=subprocess.STDOUT, shell=False,
                                       env=mapdl_environment(capability['executable']))
        record['pid'] = process.pid
        if process.poll() is not None:
            raise RuntimeError('MAPDL 图形进程提前退出，请检查会话目录中的 launcher.log')
    except (OSError, RuntimeError) as exc:
        record.update(state='failed', error=str(exc))
        raise ValueError(str(exc)) from exc
    finally:
        (session/'session.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    return record


def render_view(service, job_id, payload):
    """Run one post-processing macro in batch mode and expose a PNG preview."""
    source, output = viewer_source(service, job_id)
    view = payload.get('view', 'stress')
    if view not in {item['id'] for item in source['views']}:
        raise ValueError('该任务不支持所选视图，请刷新后重新选择')
    capability = mapdl_capabilities()
    if not capability['available']:
        raise ValueError('未找到本机 MAPDL，请先安装或配置 MAPDL_BIN')
    session = service.runtime/'apdl_viewers'/uuid.uuid4().hex[:16]
    session.mkdir(parents=True)
    result_base = Path(os.path.relpath(output/'corrosion', session)).as_posix()
    macro_name = 'v_'+view
    macro = session/(macro_name+'.mac')
    lines = ['/CLEAR,NOSTART', f"RESUME,'{result_base}',db", 'FINISH', '/POST1',
             f"FILE,'{result_base}',rst", 'SET,LAST', 'RSYS,0', '/SHOW,PNG',
             f"/IMAGE,SAVE,'{view}',PNG",
             f"/TITLE,Corrosion viewer - {view}",
             next(item[2] for item in VIEWS if item[0] == view), '/REPLOT',
             '/SHOW,CLOSE', '/EXIT']
    macro.write_text('\n'.join(lines)+'\n', encoding=_apdl_text_encoding())
    command = [str(Path(capability['executable'])), '-b', '-np', '1', '-j', 'vw_'+session.name[:10],
               '-i', macro.name, '-o', 'render.out']
    with (session/'render.launcher.log').open('wb') as stream:
        process = subprocess.Popen(command, cwd=str(session), stdin=subprocess.DEVNULL,
                                   stdout=stream, stderr=subprocess.STDOUT, shell=False)
        exit_code = process.wait(timeout=180)
    generated = sorted(session.glob('*.png'), key=lambda path: path.stat().st_mtime, reverse=True)
    image = generated[0] if generated else None
    if exit_code != 0 or image is None or image.stat().st_size == 0:
        raise ValueError(f'MAPDL 云图生成失败，退出码 {exit_code}；请查看 {session / "render.out"}')
    return {'state': 'rendered', 'view': view, 'command': command,
            'image': str(image), 'session_directory': str(session),
            'apdl_command': next(item[2] for item in VIEWS if item[0] == view)}

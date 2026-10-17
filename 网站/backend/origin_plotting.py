"""Origin orchestration; fitting results are frozen, never re-fitted here."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import importlib.util
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
import uuid

from .runner import _atomic_json
from .system_info import sha256


DEFAULTS = dict(title='Fitted response',x_label='X',y_label='Y',z_label='Y',x_unit='',y_unit='',z_unit='',
    font_family='Arial',font_size=11,title_size=14,tick_size=10,legend_size=10,line_width=2,
    line_style='solid',line_color='#B23A48',symbol='circle',symbol_size=5,opacity=85,
    x_min=None,x_max=None,y_min=None,y_max=None,z_min=None,z_max=None,x_scale='linear',y_scale='linear',
    x_reverse=False,y_reverse=False,x_major_ticks=6,y_major_ticks=6,x_minor_ticks=1,y_minor_ticks=1,
    legend='top_right',legend_border=False,grid=False,width_mm=180,height_mm=140,dpi=300,
    formats=['png','pdf'],azimuth=35,elevation=25,colormap='viridis',color_min=None,color_max=None,
    colorbar_title='Fitted Y',show_observed=True)
ENUMS = dict(line_style={'solid','dash','dot'},symbol={'circle','square','triangle','none'},
    x_scale={'linear','log'},y_scale={'linear','log'},legend={'none','top_right','top_left','bottom_right','bottom_left'},
    colormap={'viridis','rainbow','grayscale'})
RANGES = dict(font_size=(6,48),title_size=(6,60),tick_size=(6,48),legend_size=(6,48),line_width=(.1,10),
    symbol_size=(1,30),opacity=(0,100),x_major_ticks=(2,30),y_major_ticks=(2,30),x_minor_ticks=(0,10),
    y_minor_ticks=(0,10),width_mm=(80,300),height_mm=(80,300),dpi=(72,600),azimuth=(-180,180),elevation=(-89,89))
BOUNDS = {f'{a}_{b}' for a in ('x','y','z','color') for b in ('min','max')}


def normalise_origin_options(raw=None):
    if raw is None: raw={}
    if not isinstance(raw,dict) or set(raw)-set(DEFAULTS): raise ValueError('Origin绘图选项无效或含未知字段')
    o={**DEFAULTS,**raw};o['formats']=list(o['formats']) if isinstance(o['formats'],list) else o['formats']
    for key,default in DEFAULTS.items():
        v=o[key]
        if isinstance(default,bool):
            if type(v) is not bool: raise ValueError(f'{key}必须是布尔值')
        elif key in RANGES or key in BOUNDS:
            if key in BOUNDS and v is None: continue
            if isinstance(v,bool):raise ValueError(f'{key}必须是数值')
            try:v=float(v)
            except (ValueError,TypeError):raise ValueError(f'{key}必须是数值') from None
            if not math.isfinite(v):raise ValueError(f'{key}必须是有限数值')
            if key in RANGES and not RANGES[key][0]<=v<=RANGES[key][1]:raise ValueError(f'{key}超出允许范围{RANGES[key]}')
            if 'ticks' in key or key=='dpi':
                if v!=int(v):raise ValueError(f'{key}必须是整数')
                v=int(v)
            o[key]=v
        elif key in ENUMS:
            if not isinstance(v,str) or v not in ENUMS[key]:raise ValueError(f'{key}选项无效')
        elif key=='formats':
            if not isinstance(v,list) or not v or any(not isinstance(x,str) or x not in {'png','tiff','pdf','svg'} for x in v):raise ValueError('请选择PNG、TIFF、PDF或SVG格式')
            o[key]=list(dict.fromkeys(v))
        else:
            if not isinstance(v,str) or len(v)>160 or any(c in v for c in '\\"\r\n;$%{}'):raise ValueError(f'{key}文本含不支持的控制符号或过长')
    if not re.fullmatch(r'#[0-9a-fA-F]{6}',o['line_color']):raise ValueError('线颜色需要#RRGGBB')
    for a in ('x','y','z','color'):
        lo,hi=o[a+'_min'],o[a+'_max']
        if lo is not None and hi is not None and lo>=hi:raise ValueError(f'{a}上下界顺序错误')
        if o.get(a+'_scale')=='log' and any(v is not None and v<=0 for v in (lo,hi)):raise ValueError('对数坐标上下界必须大于0')
    if o['width_mm']*o['height_mm']*(o['dpi']/25.4)**2>30_000_000:raise ValueError('输出像素过大，请降低尺寸或DPI')
    return o


def _origin_executable():
    if os.name!='nt':return None
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT,r'Origin.Application\CLSID') as k:clsid=winreg.QueryValue(k,None)
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT,'CLSID\\'+clsid+r'\LocalServer32') as k:path=winreg.QueryValue(k,None)
        # Origin's registered local server can include embedding switches.
        path=path.strip().strip('"')
        end=path.lower().find('.exe')
        return path[:end+4] if end>=0 and Path(path[:end+4]).is_file() else None
    except OSError:return None


def origin_capabilities():
    installed=bool(_origin_executable())
    deps=all(importlib.util.find_spec(n) is not None for n in ('originpro','OriginExt','psutil'))
    return dict(available=installed and deps,installed=installed,dependency=deps,defaults=normalise_origin_options(),
        note='通过本机独立Origin实例绘图。安装检测不代表许可和导出已通过；每次任务记录实际运行结果。' if installed and deps else '需要本机Windows Origin和当前网站Python中的originpro、OriginExt、psutil。')


def _read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def _vector(values,name):
    if not isinstance(values,list) or len(values)<2 or any(isinstance(x,bool) or not isinstance(x,(float,int)) or not math.isfinite(x) for x in values):raise ValueError(f'{name}需要至少两个有限数值')
    return values


def _snapshot(summary,spec):
    import numpy as np
    try:group=summary['groups'][spec['group_index']]
    except (IndexError,KeyError,TypeError):raise ValueError('数据组不存在') from None
    model=next((x for x in group['candidates'] if x['id']==spec['model_id'] and x.get('status') in {'ok','success'}),None)
    if model is None:raise ValueError('所选模型没有成功拟合结果')
    o=spec['options'];multi=summary.get('fitting_mode')=='multivariate2'
    if (spec['plot_type']=='surface')!=multi:raise ValueError('二维曲线/三维响应面与拟合数据类型不一致')
    data=dict(group=group.get('label',''),model_id=model['id'],parameters=model.get('parameters',{}),formula=model.get('formula',''))
    if multi:
        x=_vector(group['x1'],'X1');y=_vector(group['x2'],'X2');z=_vector(group['y'],'Y')
        if len({len(x),len(y),len(z)})!=1 or min(x)==max(x) or min(y)==max(y):raise ValueError('三维数据长度不匹配或自变量恒定')
        p=model['parameters'];a=np.linspace(min(x),max(x),30);b=np.linspace(min(y),max(y),30);xx,yy=np.meshgrid(a,b)
        if model['id']=='linear2':zz=p['a']*xx+p['b']*yy+p['c']
        elif model['id']=='interaction2':zz=p['a']*xx+p['b']*yy+p['c']*xx*yy+p['d']
        elif model['id']=='quadratic2':zz=p['a']*xx**2+p['b']*yy**2+p['c']*xx*yy+p['d']*xx+p['e']*yy+p['f']
        else:raise ValueError('该自定义双变量模型尚不支持Origin曲面；请选择已支持的二元线性、交互或二次响应面模型')
        if not np.all(np.isfinite(zz)):raise ValueError('固定系数生成的曲面含无效值')
        color_low=float(zz.min()) if o['color_min'] is None else o['color_min']
        color_high=float(zz.max()) if o['color_max'] is None else o['color_max']
        if color_low>=color_high and (o['color_min'] is not None or o['color_max'] is not None):raise ValueError('色标单侧范围与曲面范围冲突')
        data.update(observed=dict(x=x,y=y,z=z),surface=dict(x=a.tolist(),y=b.tolist(),z=zz.tolist()))
    else:
        x=_vector(group['x'],'X');y=_vector(group['y'],'Y');curve=model.get('curve') or {}
        cx=_vector(curve.get('x'),'曲线X');cy=_vector(curve.get('y'),'曲线Y')
        if len(x)!=len(y) or len(cx)!=len(cy):raise ValueError('曲线或观测数据长度不匹配')
        data.update(observed=dict(x=x,y=y),curve=dict(x=cx,y=cy))
    for axis in ('x','y')+ (('z',) if multi else ()):
        values=data['observed'][axis]+data.get('curve',{}).get(axis,[])
        if multi:values+=([v for row in data['surface']['z'] for v in row] if axis=='z' else data['surface'][axis])
        if o.get(axis+'_scale')=='log' and min(values)<=0:raise ValueError(f'{axis}含非正数，无法使用对数坐标')
        lo,hi=o[axis+'_min'],o[axis+'_max']
        if lo is not None and hi is None and lo>=max(values) or hi is not None and lo is None and hi<=min(values):raise ValueError(f'{axis}单侧范围不包含有效坐标跨度')
    return data


def prepare_origin(payload,source_job_dir):
    source_job_dir=Path(source_job_dir);state=_read(source_job_dir/'status.json')
    if state.get('state')!='completed' or state.get('kind')!='fitting':raise ValueError('Origin绘图需要已完成的拟合任务')
    summary=_read(source_job_dir/'outputs'/'summary.json')
    gi=payload.get('group_index',0)
    if type(gi) is not int or gi<0:raise ValueError('数据组序号必须是非负整数')
    try:model_id=payload.get('model_id') or summary['groups'][gi]['recommended_id']
    except (IndexError,KeyError):raise ValueError('不存在可绘图的推荐模型') from None
    spec=dict(kind='origin_plot',source_job_id=source_job_dir.name,group_index=gi,model_id=model_id,
        plot_type=payload.get('plot_type','surface' if summary.get('fitting_mode')=='multivariate2' else 'curve'),
        options=normalise_origin_options(payload.get('options')),source_summary_sha256=sha256(source_job_dir/'outputs'/'summary.json'))
    if not isinstance(spec['plot_type'],str) or spec['plot_type'] not in {'curve','surface'}:raise ValueError('Origin绘图类型必须是curve或surface')
    _snapshot(summary,spec)
    return spec


def freeze_origin(spec,source_job_dir,job_dir):
    source=Path(source_job_dir)/'outputs'/'summary.json'
    raw=source.read_bytes()
    import hashlib
    if hashlib.sha256(raw).hexdigest()!=spec['source_summary_sha256']:raise ValueError('拟合来源在提交后改变，请重新提交')
    data=_snapshot(json.loads(raw.decode('utf-8-sig')),spec)
    target=Path(job_dir)/'inputs'/'origin_snapshot.json';_atomic_json(target,data)
    spec.update(snapshot_path='inputs/origin_snapshot.json',snapshot_sha256=sha256(target))
    _atomic_json(Path(job_dir)/'inputs'/'origin_config.json',spec)


def load_origin_snapshot(job_dir,spec):
    path=Path(job_dir)/'inputs'/'origin_snapshot.json'
    if spec.get('snapshot_path')!='inputs/origin_snapshot.json' or sha256(path)!=spec['snapshot_sha256']:raise ValueError('Origin冻结输入校验失败')
    return _read(path)


@contextmanager
def _origin_lock(runtime):
    """Windows byte lock survives server restarts and is released by the OS."""
    import msvcrt
    with (Path(runtime)/'origin.lock').open('a+b') as handle:
        if handle.tell()==0:handle.write(b'0');handle.flush()
        while True:
            try:handle.seek(0);msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1);break
            except OSError:time.sleep(.2)
        try:yield
        finally:handle.seek(0);msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)


def stop_origin_process(job_dir):
    import psutil
    path=Path(job_dir)/'origin_process.json'
    if not path.exists():
        launch=Path(job_dir)/'origin_launch.json'
        if launch.exists() and _read(launch).get('state') not in {'not_started','closed'}:
            raise ValueError('Origin启动后未完成所属进程握手，无法确认清理；请检查Origin日志')
        return
    record=_read(path)
    try:
        if type(record.get('pid')) is not int or record['pid']<=0 or not isinstance(record.get('create_time'),(int,float)) or not math.isfinite(record['create_time']):raise ValueError('Origin进程身份记录无效')
        p=psutil.Process(record['pid'])
        if abs(p.create_time()-record['create_time'])>.01 or p.name().lower()!='origin64.exe':raise ValueError('Origin进程身份不匹配，拒绝关闭')
        p.kill();p.wait(timeout=10)
    except psutil.NoSuchProcess:pass
    _atomic_json(Path(job_dir)/'origin_launch.json',dict(state='closed'))


def _run_helper(job_dir,mode,project=None,timeout=240):
    job_dir=Path(job_dir);output=job_dir/'outputs';output.mkdir(exist_ok=True)
    args=[sys.executable,'-m','backend.origin_render',mode,str(job_dir)]
    if project:args.append(str(project))
    started=time.monotonic()
    _atomic_json(job_dir/'origin_launch.json',dict(state='starting'))
    with (output/('origin_open.log' if mode=='open' else 'origin.log')).open('ab') as log:
        child=subprocess.Popen(args,cwd=str(Path(__file__).resolve().parents[1]),stdout=log,stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),env=dict(os.environ,PYTHONUTF8='1',PYTHONIOENCODING='utf-8'))
        try:
            while child.poll() is None:
                if time.monotonic()-started>timeout:raise TimeoutError(f'Origin运行超过{timeout}秒，任务已停止，详见origin日志')
                time.sleep(.2)
            if child.returncode:raise RuntimeError('Origin自动绘图失败，请查看任务文件中的origin日志；已生成的文件保留')
        finally:
            if child.poll() is None:child.kill();child.wait(timeout=10)
            if mode!='open' or child.returncode:stop_origin_process(job_dir)


def run_origin(job_dir,spec,update=None):
    job_dir=Path(job_dir);started=time.perf_counter();load_origin_snapshot(job_dir,spec)
    if not origin_capabilities()['available']:raise RuntimeError(origin_capabilities()['note'])
    if update:update(dict(phase='origin_wait',message='等待本机Origin绘图实例',progress=5))
    with _origin_lock(job_dir.parent.parent):
        if update:update(dict(phase='origin_plot',message='Origin正在创建可编辑图形与工程',progress=20))
        _run_helper(job_dir,'render')
    output=job_dir/'outputs';evidence=_read(output/'origin_runtime.json')
    if not evidence.get('project_reopened') or not (output/'origin_project.opju').is_file():raise RuntimeError('Origin工程保存或重开验收失败')
    summary=dict(kind='origin_plot',source_job_id=spec['source_job_id'],plot_type=spec['plot_type'],options=spec['options'],
        model_id=spec['model_id'],group_index=spec['group_index'],source_summary_sha256=spec['source_summary_sha256'],
        snapshot_sha256=spec['snapshot_sha256'],plots=[dict(name='origin_plot.png',label='Origin实际导出图')],
        origin=evidence,timing=dict(elapsed_seconds=time.perf_counter()-started),warnings=evidence.get('warnings',[]))
    _atomic_json(output/'summary.json',summary)
    _atomic_json(output/'origin_config.json',spec)
    _atomic_json(output/'manifest.json',dict(kind='origin_plot',source_summary_sha256=spec['source_summary_sha256'],
        files=[dict(name=p.name,sha256=sha256(p)) for p in sorted(output.iterdir()) if p.is_file() and p.name!='manifest.json']))
    if update:update(dict(phase='origin_complete',message='Origin图形、可编辑工程与数据已保存',progress=100))
    return summary


def open_origin_project(job_dir):
    job_dir=Path(job_dir);project=job_dir/'outputs'/'origin_project.opju'
    if not project.is_file():raise ValueError('该任务没有可编辑的Origin工程')
    if not origin_capabilities()['available']:raise ValueError(origin_capabilities()['note'])
    # Keep completed evidence immutable when a researcher edits and saves.
    editing=job_dir/'editing'/uuid.uuid4().hex[:8];editing.mkdir(parents=True)
    copy=editing/'origin_project.opju';shutil.copy2(project,copy)
    with _origin_lock(job_dir.parent.parent):_run_helper(editing,'open',copy)
    return dict(opened=True,note=f'已在独立Origin窗口打开工程编辑副本：{copy}。请在Origin中保存修改；网页下载保留原始结果。')

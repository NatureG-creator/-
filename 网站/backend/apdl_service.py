"""APDL job-owned sources, explicit coordinate conversion and task orchestration."""
from __future__ import annotations

import copy
import math
import shutil
import time
from pathlib import Path

import numpy as np
from scipy.io import loadmat

from .finite_element_export import _state_from_npz, surface_from_ca_state
from .runner import _atomic_json
from .system_info import sha256, runtime_provenance

MATRIX_EXTENSIONS = {'.mat', '.csv', '.txt', '.tsv'}


def _number(value, label, *, positive=False):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float, np.number)):
        raise ValueError(label+'必须是有限数值')
    value=float(value)
    if not math.isfinite(value) or (positive and value <= 0):
        raise ValueError(label+('必须是正的有限数值' if positive else '必须是有限数值'))
    return value


def _flag(mapping, name):
    value=mapping.get(name, False)
    if not isinstance(value,bool):
        raise ValueError(name+'必须是布尔值')
    return value


def read_face(path: Path, source_kind: str, mapping: dict, inherited_geometry=None):
    """Read positive depth in mm, canonically depth[row_y,column_x]."""
    path=Path(path)
    mapping=dict(mapping or {})
    inherited=dict(inherited_geometry or {})
    variable=mapping.get('variable') or None
    if source_kind=='simulation':
        if 'space_z_um' not in inherited or 'space_xy_um' not in inherited:
            raise ValueError('模拟来源缺少真实元胞尺寸，不能猜测物理间距')
        raw=surface_from_ca_state(_state_from_npz(path), _number(inherited['space_z_um'],'源Z向尺寸',positive=True))
        default_layout='xy'
        unit='mm'
        value_mode='depth'
    elif source_kind=='measured':
        if path.suffix.lower() not in MATRIX_EXTENSIONS:
            raise ValueError('实测表面仅支持MAT/CSV/TXT/TSV二维矩阵；XYZ点云请先在第一模块处理')
        if path.suffix.lower()=='.mat':
            values=loadmat(path)
            choices=[key for key in ('Z_filled','F_filled') if key in values]
            if variable is None:
                if len(choices)!=1:
                    raise ValueError('MAT需要明确选择唯一表面变量Z_filled或F_filled')
                variable=choices[0]
            if variable not in ('Z_filled','F_filled') or variable not in values:
                raise ValueError('MAT中没有指定的Z_filled/F_filled变量')
            raw=np.asarray(values[variable])
        else:
            delimiter={'.csv':',','.tsv':'\t'}.get(path.suffix.lower())
            try:
                raw=np.loadtxt(path,delimiter=delimiter,encoding='utf-8-sig',ndmin=2)
            except (ValueError,UnicodeError) as exc:
                raise ValueError('表面文件需为无表头的有限数值矩阵，不是三列XYZ点列表：'+str(exc)) from exc
        default_layout=inherited.get('layout','yx')
        unit=mapping.get('unit','mm')
        if not isinstance(unit,str): raise ValueError('单位必须是mm或um')
        unit=unit.replace('μm','um').replace('µm','um')
        value_mode=mapping.get('value_mode','depth')
    else:
        raise ValueError('表面来源类型必须是simulation或measured')
    if np.iscomplexobj(raw) or raw.ndim!=2 or min(raw.shape)<2 or not np.issubdtype(raw.dtype,np.number):
        raise ValueError('表面必须是至少2×2的实数二维矩阵')
    raw=np.asarray(raw,dtype=np.float64)
    original_shape=list(raw.shape)
    if not np.isfinite(raw).all():
        raise ValueError('表面包含非有限数值NaN/Inf')
    crop=mapping.get('center_crop_columns')
    crop_bounds=None
    if crop is not None:
        if source_kind!='measured' or isinstance(crop,bool) or not isinstance(crop,int) or not 2<=crop<=raw.shape[1]:
            raise ValueError('显式中心裁剪列数必须是2至原始列数之间的整数，仅适用于实测矩阵')
        start=(raw.shape[1]-crop)//2
        crop_bounds=[start,start+crop]
        raw=raw[:,start:start+crop]
    if unit not in {'mm','um'} or value_mode not in {'depth','height'}:
        raise ValueError('单位仅支持mm/um，数值类型仅支持depth/height')
    layout=mapping.get('layout','auto')
    if layout=='auto': layout=default_layout
    if layout not in {'xy','yx'}:
        raise ValueError('矩阵行列约定必须是auto、xy或yx')
    scale=.001 if unit=='um' else 1.
    reference_mode=mapping.get('reference_mode','manual')
    if reference_mode not in {'manual','maximum'}: raise ValueError('参考面模式必须是manual或maximum')
    reference=float(raw.max()) if reference_mode=='maximum' else _number(mapping.get('reference_height',0),'参考高度')
    sign=_number(mapping.get('height_sign',1),'高度方向')
    if sign not in (-1.,1.):
        raise ValueError('高度方向只能是1或-1')
    depth=raw*scale if value_mode=='depth' else (reference-raw)*sign*scale
    if np.any(depth<0):
        raise ValueError('正腐蚀深度不能为负；若输入是表面高度，请明确参考面与高度方向')
    inherited_spacing=inherited.get('space_xy_um')
    defaults={axis:inherited.get(axis, None if inherited_spacing is None else float(inherited_spacing)/1000)
              for axis in ('dx_mm','dy_mm')}
    spacing=[]
    for axis in ('dx_mm','dy_mm'):
        value=mapping.get(axis,defaults[axis])
        if value is None:
            raise ValueError('上传/未知来源矩阵必须明确给出X/Y物理间距')
        number=_number(value,axis+'间距',positive=True)
        if source_kind=='simulation' and not math.isclose(number,defaults[axis],rel_tol=0,abs_tol=1e-12):
            raise ValueError('模拟来源必须继承真实XY间距，不能重新解释元胞尺寸')
        spacing.append(number)
    dx,dy=spacing
    if layout=='xy':
        depth=depth.T
    transposed=_flag(mapping,'transpose')
    flipped_x=_flag(mapping,'flip_x')
    flipped_y=_flag(mapping,'flip_y')
    if transposed:
        depth=depth.T
        dx,dy=dy,dx
    if flipped_x: depth=depth[:,::-1]
    if flipped_y: depth=depth[::-1,:]
    depth=np.array(depth,dtype=np.float64,copy=True)
    metadata=dict(variable=variable,input_unit=unit,value_mode=value_mode,input_layout=layout,
                  shape=list(depth.shape),original_shape=original_shape,dx_mm=dx,dy_mm=dy,
                  origin_x_mm=_number(mapping.get('origin_x_mm',inherited.get('origin_x_mm',0)),'X原点'),
                  origin_y_mm=_number(mapping.get('origin_y_mm',inherited.get('origin_y_mm',0)),'Y原点'),
                  reference_height=reference,reference_mode=reference_mode,crop_columns_zero_based=crop_bounds,
                  height_sign=sign,transpose=transposed,flip_x=flipped_x,flip_y=flipped_y,
                  min_depth_mm=float(depth.min()),max_depth_mm=float(depth.max()),
                  coordinate_note='局部表面坐标；双面独立数据仍需确认同一XY位置配准。')
    return depth,metadata


def _resolve_source(service, descriptor, label):
    if not isinstance(descriptor,dict):
        raise ValueError(label+'面需要选择来源')
    descriptor=copy.deepcopy(descriptor)
    mapping=descriptor.get('mapping') or {}
    if not isinstance(mapping,dict): raise ValueError('mapping必须是对象')
    kind=descriptor.get('source_kind','measured')
    inherited={}
    job_id=descriptor.get('source_job_id')
    upload_id=descriptor.get('upload_id')
    if bool(job_id)==bool(upload_id):
        raise ValueError(label+'面必须在源任务与上传文件中选一种')
    if upload_id:
        if kind!='measured': raise ValueError('上传只接受实测二维矩阵，模拟NPZ请选择已完成任务')
        record,path=service.get_upload(upload_id)
        metadata=dict(upload_id=upload_id,name=record['name'],sha256=record['sha256'])
        if path.suffix.lower() not in MATRIX_EXTENSIONS: raise ValueError('APDL上传表面仅支持MAT/CSV/TXT/TSV矩阵')
    else:
        service.validate_id(job_id)
        state=service.get_job(job_id)
        if state['state']!='completed': raise ValueError('APDL来源必须是已完成的任务')
        root=(service.runtime/'jobs'/job_id/'outputs').resolve()
        stage=descriptor.get('source_stage')
        if kind=='simulation':
            if state.get('kind')!='simulation': raise ValueError('模拟表面必须选择已完成CA–GA任务')
            if stage is not None and (isinstance(stage,bool) or not isinstance(stage,int) or not 1<=stage<=100000):
                raise ValueError('来源阶段必须是有效整数')
            path=root/(f'stage_{stage:03d}.npz' if stage is not None else 'simulation.npz')
            inherited=state.get('spec',{}).get('config',{}).get('GEOMETRY_CONFIG',{})
        elif kind=='measured':
            if state.get('kind') not in {'pointcloud','finite_element'}: raise ValueError('实测表面请选择点云或表面导出任务')
            requested=descriptor.get('source_file')
            if requested:
                if not isinstance(requested,str) or Path(requested).is_absolute() or '..' in Path(requested).parts:
                    raise ValueError('来源文件必须来自所选任务输出目录')
                path=(root/requested).resolve()
                if not path.is_relative_to(root): raise ValueError('来源文件路径越界')
            else:
                candidates=[p for p in root.rglob('*.mat') if p.resolve().is_relative_to(root)]
                if len(candidates)!=1: raise ValueError('源任务存在零个或多个MAT，请明确选择表面文件与变量')
                path=candidates[0]
            if path.suffix.lower() not in MATRIX_EXTENSIONS: raise ValueError('来源文件需为MAT/CSV/TXT/TSV矩阵')
            cfg=state.get('spec',{}).get('pointcloud_config',{})
            spacing=cfg.get('preprocessing',{}).get('grid_resolution_mm')
            if state.get('kind')=='finite_element':
                legacy=state.get('spec',{}).get('options',{})
                spacing=legacy.get('grid_spacing_mm',spacing)
                inherited.update(layout='xy',origin_x_mm=legacy.get('origin_x_mm',0),
                                 origin_y_mm=legacy.get('origin_y_mm',0))
            if spacing is not None: inherited.update(dx_mm=spacing,dy_mm=spacing)
        else: raise ValueError('表面来源类型无效')
        if not path.is_file(): raise ValueError('源任务缺少所选表面或阶段文件')
        metadata=dict(source_job_id=job_id,source_stage=stage,name=path.name,sha256=sha256(path))
    if sha256(path)!=metadata['sha256']: raise ValueError('来源文件已变化，请重新上传或选择')
    depth,converted=read_face(path,kind,mapping,inherited)
    if sha256(path)!=metadata['sha256']: raise ValueError('读取期间来源文件变化，拒绝冻结')
    metadata.update(source_kind=kind,**converted)
    input_path=f'inputs/{label}{path.suffix.lower()}'
    face=dict(source_kind=kind,mapping=mapping,inherited_geometry=inherited,input_path=input_path,metadata=metadata)
    record=dict(label=label,path=path,sha256=metadata['sha256'],input_path=input_path)
    return face,record,depth


def _prepare(service,payload):
    from .apdl_geometry import normalise_options,build_geometry
    if not isinstance(payload,dict): raise ValueError('APDL任务必须是对象')
    started=time.perf_counter()
    options=normalise_options(payload.get('options') or {})
    run_mode=payload.get('run_mode','build')
    if run_mode not in {'build','solve'}: raise ValueError('run_mode只能是build或solve')
    mode=options['corrosion_mode']
    labels=[] if mode=='flat' else ['bottom'] if mode=='single_bottom' else ['top','bottom'] if mode=='double_independent' else ['top']
    faces,records,depths={},{},{}
    for label in labels:
        faces[label],records[label],depths[label]=_resolve_source(service,payload.get(label+'_source'),label)
    if mode=='double_independent':
        if payload.get('registration_confirmed') is not True:
            raise ValueError('双面独立形貌需明确确认已配准到同一物理XY位置')
        a,b=faces['top']['metadata'],faces['bottom']['metadata']
        if a['shape']!=b['shape'] or any(not math.isclose(a[key],b[key],rel_tol=0,abs_tol=1e-10) for key in ('dx_mm','dy_mm','origin_x_mm','origin_y_mm')):
            raise ValueError('双面行列、间距或原点不匹配；不进行隐式重采样')
    if faces:
        first=next(iter(faces.values()))['metadata']
        options.update({key:first[key] for key in ('dx_mm','dy_mm','origin_x_mm','origin_y_mm')})
    geometry=build_geometry(depths.get('top'),depths.get('bottom'),options)
    preset_id=payload.get('preset_id')
    preset_provenance=None
    if preset_id:
        from .apdl_presets import get_presets
        preset=next((p for p in get_presets() if p['id']==preset_id),None)
        if preset is None: raise ValueError('未知APDL预设')
        preset_provenance=preset.get('provenance')
    spec=dict(kind='apdl_tension',run_mode=run_mode,options=geometry['options'],faces=faces,preset_id=preset_id,preset_provenance=preset_provenance,
              registration_confirmed=payload.get('registration_confirmed') is True,
              precheck=geometry['stats'],reading_seconds=time.perf_counter()-started,
              case_name=str(payload.get('case_name',''))[:100])
    return spec,list(records.values()),geometry


def prepare_apdl(service,payload):
    spec,records,_=_prepare(service,payload)
    if spec['run_mode']=='solve':
        from .apdl_solver import mapdl_capabilities
        if not mapdl_capabilities().get('available'):
            raise ValueError('尚未配置可用MAPDL可执行文件；请设置MAPDL_BIN，或先选择仅生成模型')
    return spec,records


def precheck_apdl(service,payload):
    spec,_,geometry=_prepare(service,payload)
    preview={}
    for name in ('top_depth','bottom_depth','remaining'):
        array=geometry[name]
        preview[name]=array[::max(1,math.ceil(array.shape[0]/80)),::max(1,math.ceil(array.shape[1]/80))].tolist()
    return dict(options=spec['options'],stats=geometry['stats'],warnings=geometry.get('warnings',[]),
                faces={key:face['metadata'] for key,face in spec['faces'].items()},preview=preview,
                units='N-mm-MPa',run_mode=spec['run_mode'],registration_confirmed=spec['registration_confirmed'],
                reading_seconds=spec['reading_seconds'])


def freeze_apdl_sources(records,job_dir):
    for record in records:
        target=Path(job_dir)/record['input_path']
        if not target.resolve().is_relative_to((Path(job_dir)/'inputs').resolve()): raise ValueError('冻结输出路径越界')
        shutil.copy2(record['path'],target)
        if sha256(target)!=record['sha256']: raise ValueError('APDL来源冻结失败，源文件可能已变化')


def run_apdl_job(spec,job_dir,progress=None):
    from .apdl_geometry import build_geometry
    from .apdl_deck import create_tension_bundle
    job_dir=Path(job_dir); output=job_dir/'outputs'; output.mkdir(exist_ok=True)
    total=time.perf_counter(); tick=time.perf_counter()
    if progress: progress({'phase':'apdl_read'})
    depths={}
    for label,face in spec['faces'].items():
        path=(job_dir/face['input_path']).resolve()
        if not path.is_relative_to((job_dir/'inputs').resolve()) or sha256(path)!=face['metadata']['sha256']:
            raise ValueError('APDL冻结来源已变化或路径越界')
        depths[label],_=read_face(path,face['source_kind'],face['mapping'],face['inherited_geometry'])
    timing=dict(reading_seconds=time.perf_counter()-tick)
    tick=time.perf_counter()
    geometry=build_geometry(depths.get('top'),depths.get('bottom'),spec['options'])
    timing['geometry_seconds']=time.perf_counter()-tick
    if progress: progress({'phase':'apdl_build'})
    tick=time.perf_counter()
    provenance=dict(faces={key:face['metadata'] for key,face in spec['faces'].items()},runtime=runtime_provenance(),
                    preset_id=spec.get('preset_id'),preset=spec.get('preset_provenance'))
    result=create_tension_bundle(geometry,output,provenance)
    timing['build_export_seconds']=time.perf_counter()-tick
    result.update(kind='apdl_tension',run_mode=spec['run_mode'],build_state='built',solve_state='not_requested',timing=timing)
    _atomic_json(output/'summary.json',result)
    if spec['run_mode']=='solve':
        from .apdl_solver import run_mapdl,read_tension_results
        try:
            if progress: progress({'phase':'apdl_solve'})
            tick=time.perf_counter()
            execution=run_mapdl(output,spec['options'],progress=progress)
            timing['solver_seconds']=time.perf_counter()-tick
            result.update(solver=execution,solve_state='postprocessing')
            _atomic_json(output/'summary.json',result)
            if progress: progress({'phase':'apdl_post'})
            tick=time.perf_counter()
            result['results']=read_tension_results(output,geometry['stats'],spec['options'])
            timing['postprocess_seconds']=time.perf_counter()-tick
            result['solve_state']='solved'
        except Exception as exc:
            timing['total_seconds']=time.perf_counter()-total
            result.update(solve_state='failed',error=str(exc))
            _atomic_json(output/'timing.json',timing)
            _atomic_json(output/'summary.json',result)
            raise
    timing['total_seconds']=time.perf_counter()-total
    _atomic_json(output/'timing.json',timing)
    _atomic_json(output/'summary.json',result)
    return result

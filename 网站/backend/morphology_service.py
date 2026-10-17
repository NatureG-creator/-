"""Independent, frozen-input morphology analysis; never runs CA/GA."""
import copy
import json
import shutil
import time
from pathlib import Path
import numpy as np
from .config import default_simulation_config
from .apdl_npz import inspect_npz, read_npz_state, resolve_geometry
from .system_info import sha256


def prepare_morphology(service, payload):
    started=time.perf_counter()
    mode=payload.get('analysis_mode','ga')
    if mode not in {'ga','detail'}: raise ValueError('analysis_mode 只能为 ga 或 detail')
    if bool(payload.get('upload_id'))==bool(payload.get('source_job_id')):
        raise ValueError('请选择一个上传 NPZ 或一个已完成模拟任务')
    config=default_simulation_config()
    physical_layers=None
    provenance='当前配置复算；外部 NPZ 未冻结完整后处理配置，不能认定原优化过程完全重放'
    if payload.get('upload_id'):
        record,path=service.get_upload(payload['upload_id'])
        name=record['name'];expected=record['sha256']
    else:
        source_id=service.validate_id(payload['source_job_id'])
        source_state=service.get_job(source_id)
        if source_state.get('kind')!='simulation' or source_state.get('state')!='completed':
            raise ValueError('来源必须为已完成模拟任务')
        folder=service.runtime/'jobs'/source_id
        spec=json.loads((folder/'spec.json').read_text(encoding='utf-8'))
        config=copy.deepcopy(spec['config'])
        path=folder/'outputs/simulation.npz';name=f'{source_id}/simulation.npz'
        physical_layers=int(config['GEOMETRY_CONFIG']['grid_n'])
        provenance='使用源模拟任务 spec.json 冻结配置；对最终阶段重新提取'
        expected=sha256(path)
    if path.is_symlink() or sha256(path)!=expected: raise ValueError('来源文件已改变，请重新选择')
    info=inspect_npz(path)
    geometry=resolve_geometry(info,payload.get('cell_geometry') or
        ({k:config['GEOMETRY_CONFIG'][k] for k in ('space_xy_um','space_z_um')} if physical_layers else None))
    selected=next(v for v in info['variables'] if v['name']==info['default_variable'])
    shape=selected['state_shape']
    if physical_layers is not None and tuple(shape[:2]) != tuple(int(config['GEOMETRY_CONFIG'][k]) for k in ('grid_w','grid_l')):
        raise ValueError('状态XY维与原任务 grid_w/grid_l 不匹配')
    if physical_layers is not None and shape[2] not in {physical_layers,physical_layers+1}:
        raise ValueError('状态Z维与原任务 grid_n 不匹配')
    spec=dict(kind='morphology_analysis',case_name=payload.get('case_name') or f'{name} · {"GA同口径验收" if mode=="ga" else "精细形貌分析"}',
        analysis_mode=mode,config=config,geometry=geometry,physical_layers=physical_layers,
        source_name=name,source_sha256=expected,configuration_provenance=provenance,
        npz_variable=info['default_variable'],npz_stage=selected['stage_count'],
        reading_seconds=time.perf_counter()-started)
    return spec,path


def freeze_morphology(spec,source,job_dir):
    dest=job_dir/'inputs/source.npz';shutil.copy2(source,dest)
    if sha256(dest)!=spec['source_sha256']:raise ValueError('NPZ 冻结副本校验失败')


def run_morphology(spec,job_dir,progress=None):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from .strict_ga import scientific_settings
    from morphology_analysis import analyze_surface,export_analysis
    from .runner import _atomic_json
    path=job_dir/'inputs/source.npz'
    if sha256(path)!=spec['source_sha256']: raise ValueError('冻结 NPZ 已改变')
    started=time.perf_counter()
    if progress:progress({'phase':'reading'})
    state,_=read_npz_state(path,spec['npz_variable'],spec['npz_stage'])
    read_seconds=time.perf_counter()-started
    if progress:progress({'phase':'compute'})
    compute_started=time.perf_counter()
    with scientific_settings(spec['config']):
        result=analyze_surface(state,mode=spec['analysis_mode'],physical_layers=spec['physical_layers'],**spec['geometry'])
    m=result['metadata']
    m.update(source_sha256=spec['source_sha256'],configuration_provenance=spec['configuration_provenance'])
    compute_seconds=time.perf_counter()-compute_started
    plot_started=time.perf_counter()
    if progress:progress({'phase':'plot'})
    plt.rcParams['font.sans-serif']=['Microsoft YaHei','SimHei','DejaVu Sans']
    plt.rcParams['axes.unicode_minus']=False
    figures=export_analysis(result,job_dir/'outputs',source_name=spec['source_name'])
    for fig in figures:plt.close(fig)
    report=result['report']
    n=result['metadata']['physical_layers'];w,l=state.shape[:2];z=spec['geometry']['space_z_um']
    report['six_metrics']=[float((w*l*n-np.count_nonzero(state==1))/(w*l)*z),
        float(np.mean(result['depth_map']-result['depth_map'].min())*z),
        report['log_ratio']['mean'],report['log_depth']['mean'],
        report['log_ratio']['std'] if report['log_ratio']['count']>1 else None,
        report['log_depth']['std'] if report['valid_count']>1 else None]
    report['warnings']=[spec['configuration_provenance'],m['layer_rule'],report['objective_note'],
        '正态参考曲线不代表正态检验通过；原算法空边界回退样本数见报告。']
    report['timing']=dict(reading_seconds=spec['reading_seconds']+read_seconds,
        compute_seconds=compute_seconds,plot_seconds=time.perf_counter()-plot_started)
    _atomic_json(job_dir/'outputs/analysis_report.json',report)
    _atomic_json(job_dir/'outputs/summary.json',report)
    return report

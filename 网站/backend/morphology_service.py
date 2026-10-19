"""Independent, frozen-input morphology analysis; never runs CA/GA."""
import copy
import json
import re
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
    if mode not in {'ga','detail','both'}: raise ValueError('analysis_mode 只能为 ga、detail 或 both')
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
    stage=selected['stage_count']
    stages=None
    requested=payload.get('source_stages')
    if payload.get('upload_id') and requested is not None:
        if requested == 'all':
            stages=list(range(1,selected['stage_count']+1))
        elif isinstance(requested,list) and requested:
            if any(isinstance(item,bool) or not isinstance(item,int) for item in requested):
                raise ValueError('NPZ 批量阶段必须为整数列表')
            stages=sorted(set(requested))
        else:
            raise ValueError('NPZ 批量阶段必须为 all 或非空整数列表')
        if any(item<1 or item>selected['stage_count'] for item in stages):
            raise ValueError(f"NPZ 阶段必须是 1 至 {selected['stage_count']} 的整数（按存储顺序编号）")
        if len(stages)>1:
            stage=None
        else:
            stage=stages[0]
    if payload.get('upload_id') and payload.get('source_stage') is not None:
        value=payload['source_stage']
        if isinstance(value,bool) or not isinstance(value,int) or not 1<=value<=selected['stage_count']:
            raise ValueError(f"NPZ 阶段必须是 1 至 {selected['stage_count']} 的整数（按存储顺序编号）")
        stage=value
    shape=selected['state_shape']
    if physical_layers is not None and tuple(shape[:2]) != tuple(int(config['GEOMETRY_CONFIG'][k]) for k in ('grid_w','grid_l')):
        raise ValueError('状态XY维与原任务 grid_w/grid_l 不匹配')
    if physical_layers is not None and shape[2] not in {physical_layers,physical_layers+1}:
        raise ValueError('状态Z维与原任务 grid_n 不匹配')
    mode_label={'ga':'GA同口径验收','detail':'精细形貌分析','both':'双模式对照'}[mode]
    spec=dict(kind='morphology_analysis',case_name=payload.get('case_name') or f'{name} · {mode_label}',
        analysis_mode=mode,config=config,geometry=geometry,physical_layers=physical_layers,
        source_name=name,source_sha256=expected,configuration_provenance=provenance,
        npz_variable=info['default_variable'],npz_stage=stage,
        reading_seconds=time.perf_counter()-started)
    if stages and len(stages)>1:
        spec['npz_stages']=stages
        spec['case_name']=payload.get('case_name') or f'{name} · {mode_label} · {len(stages)}阶段批量'
    return spec,path


def freeze_morphology(spec,source,job_dir):
    dest=job_dir/'inputs/source.npz';shutil.copy2(source,dest)
    if sha256(dest)!=spec['source_sha256']:raise ValueError('NPZ 冻结副本校验失败')


def run_morphology(spec,job_dir,progress=None, *, state=None, output=None):
    if spec.get('npz_stages'):
        return run_morphology_batch(spec,job_dir,progress)
    if spec['analysis_mode']=='both':
        reports=run_morphology_pair(spec,job_dir,progress)
        from .runner import _atomic_json
        summary={'modes':reports}
        _atomic_json(job_dir/'outputs/summary.json',summary)
        write_morphology_archive(job_dir)
        return summary
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
    if state is None:
        state,_=read_npz_state(path,spec['npz_variable'],spec['npz_stage'])
    output=output or job_dir/'outputs'
    read_seconds=time.perf_counter()-started
    if progress:progress({'phase':'compute'})
    compute_started=time.perf_counter()
    with scientific_settings(spec['config']):
        result=analyze_surface(state,mode=spec['analysis_mode'],physical_layers=spec['physical_layers'],**spec['geometry'])
    m=result['metadata']
    m.update(source_sha256=spec['source_sha256'],configuration_provenance=spec['configuration_provenance'],
             npz_variable=spec['npz_variable'],npz_stage=spec['npz_stage'])
    compute_seconds=time.perf_counter()-compute_started
    plot_started=time.perf_counter()
    if progress:progress({'phase':'plot'})
    plt.rcParams['font.sans-serif']=['Microsoft YaHei','SimHei','DejaVu Sans']
    plt.rcParams['axes.unicode_minus']=False
    figures=export_analysis(result,output,source_name=spec['source_name'],formats=('png',))
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
    _atomic_json(output/'analysis_report.json',report)
    _atomic_json(output/'summary.json',report)
    if output==job_dir/'outputs':write_morphology_archive(job_dir)
    return report


def run_morphology_pair(spec, job_dir, progress=None, *, state=None, output=None):
    path=job_dir/'inputs/source.npz'
    if sha256(path)!=spec['source_sha256']:raise ValueError('冻结 NPZ 已改变')
    started=time.perf_counter()
    if progress:progress({'phase':'reading'})
    if state is None:
        state,_=read_npz_state(path,spec['npz_variable'],spec['npz_stage'])
    settings=dict(spec,reading_seconds=spec['reading_seconds']+time.perf_counter()-started)
    return {mode:run_morphology(dict(settings,analysis_mode=mode),job_dir,progress,
                state=state,output=(output or job_dir/'outputs')/mode) for mode in ('ga','detail')}


def run_morphology_batch(spec, job_dir, progress=None):
    """Analyze selected stages from one frozen NPZ and retain each stage separately."""
    path=job_dir/'inputs/source.npz'
    if sha256(path)!=spec['source_sha256']:raise ValueError('冻结 NPZ 已改变')
    reports=[]
    for stage in spec['npz_stages']:
        if progress:progress({'phase':'reading','stage':stage})
        state,_=read_npz_state(path,spec['npz_variable'],stage)
        stage_dir=job_dir/'outputs'/f'stage_{stage:03d}'
        if spec['analysis_mode']=='both':
            modes=run_morphology_pair(dict(spec,npz_stage=stage,npz_stages=None),job_dir,progress,
                                      state=state,output=stage_dir)
            reports.append({'stage':stage,'modes':modes})
        else:
            report=run_morphology(dict(spec,npz_stage=stage,npz_stages=None),job_dir,progress,state=state,output=stage_dir)
            reports.append({'stage':stage,'report':report})
    from .runner import _atomic_json
    summary={'stages':reports,'npz_variable':spec['npz_variable'],'npz_stages':spec['npz_stages'],
             'source_name':spec['source_name'],'source_sha256':spec['source_sha256']}
    _atomic_json(job_dir/'outputs/summary.json',summary)
    write_morphology_archive(job_dir)
    return summary


def write_morphology_archive(job_dir):
    import zipfile
    output=job_dir/'outputs';output.mkdir(exist_ok=True)
    archive=output/'morphology_bundle.zip'
    temporary=output/'morphology_bundle.zip.tmp'
    spec_path=job_dir/'spec.json'
    try:
        source_spec=json.loads(spec_path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        source_spec={}
    origin_spec={}
    if source_spec.get('kind')=='morphology_export':
        try:origin_spec=json.loads((job_dir/'inputs/source_spec.json').read_text(encoding='utf-8'))
        except (OSError,json.JSONDecodeError):pass
    metadata={**origin_spec,**source_spec}
    source_name=str(metadata.get('source_name') or 'source.npz').replace('\\','/').rsplit('/',1)[-1]
    source_name=re.sub(r'[\x00-\x1f<>:"/\\|?*]+','_',source_name).strip(' .') or 'source.npz'
    source_stem=Path(source_name).stem or 'source'
    source_stem=re.sub(r'[^\w.-]+','_',source_stem,flags=re.UNICODE).strip(' ._') or 'source'
    source_hash=re.sub(r'[^a-fA-F0-9]','',str(metadata.get('source_sha256') or ''))[:10]
    source_folder=source_stem+('_'+source_hash if source_hash else '')
    stage=metadata.get('npz_stage')
    stages=metadata.get('npz_stages')
    if isinstance(stages,list) and stages:
        stage_folder=f"stages_{int(stages[0]):03d}-{int(stages[-1]):03d}"
    else:
        stage_folder=f'stage_{int(stage):03d}' if isinstance(stage,int) and not isinstance(stage,bool) and stage>0 else 'stage_unknown'
    prefix=f'成果/{source_folder}/{stage_folder}'
    source_mode=metadata.get('analysis_mode')
    mode_names={'ga':'GA同口径验收','detail':'精细形貌分析',
                'single':{'ga':'GA同口径验收','detail':'精细形貌分析'}.get(source_mode,'单模式分析')}
    roots=(job_dir/'spec.json',job_dir/'inputs',output)
    paths=[]
    for root in roots:
        paths.extend([root] if root.is_file() else sorted(root.rglob('*')))
    files=[]
    for path in paths:
        if path in (archive,temporary,output/'morphology_manifest.json') or path.suffix=='.tmp':continue
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(job_dir.resolve()):continue
        relative=path.relative_to(job_dir).as_posix()
        category='source' if relative.startswith('inputs/source.') else 'configuration' if relative.startswith('inputs/') else 'analysis'
        mode=None
        parts=relative.split('/')
        if len(parts)>2 and parts[0] in {'inputs','outputs'} and parts[1] in {'ga','detail','single'}:mode=parts[1]
        batch_stage=parts[1] if len(parts)>2 and parts[0] in {'inputs','outputs'} and parts[1].startswith('stage_') else None
        if relative=='spec.json':archive_path=f'{prefix}/配置与溯源/任务配置.json'
        elif relative=='inputs/source_spec.json':archive_path=f'{prefix}/配置与溯源/来源任务配置.json'
        elif relative.startswith('inputs/source.'):
            archive_path=f'{prefix}/来源文件/{source_name}'
        elif len(parts)>2 and parts[0]=='inputs' and parts[1] in {'ga','detail','single'}:
            mode=parts[1];archive_path=f"{prefix}/冻结分析数据/{mode_names[mode]}/{'/'.join(parts[2:])}"
        elif len(parts)>2 and parts[0]=='outputs' and parts[1] in {'ga','detail','single'}:
            mode=parts[1];archive_path=f"{prefix}/分析结果/{mode_names[mode]}/{'/'.join(parts[2:])}"
        elif batch_stage and len(parts)>2 and parts[2] in {'ga','detail','single'}:
            mode=parts[2];category_label='冻结分析数据' if parts[0]=='inputs' else '分析结果'
            archive_path=f"{prefix}/{category_label}/{batch_stage}/{mode_names[mode]}/{'/'.join(parts[3:])}"
        elif batch_stage and len(parts)>2:
            category_label='冻结分析数据' if parts[0]=='inputs' else '分析结果'
            archive_path=f"{prefix}/{category_label}/{batch_stage}/{mode_names['single']}/{'/'.join(parts[2:])}"
        elif relative=='outputs/morphology_manifest.json':archive_path=f'{prefix}/报告/清单.json'
        elif relative=='outputs/summary.json':archive_path=f'{prefix}/报告/汇总.json'
        elif relative.startswith('outputs/'):
            mode_label=mode_names['single'];archive_path=f"{prefix}/分析结果/{mode_label}/{'/'.join(parts[1:])}"
        elif relative.startswith('inputs/'):
            archive_path=f"{prefix}/冻结输入/{'/'.join(parts[1:])}"
        else:continue
        files.append({'path':relative,'archive_path':archive_path,'category':category,
                      'mode':mode_names.get(mode,mode) if mode else None,'bytes':path.stat().st_size,
                      'sha256':sha256(path)})
    manifest={'schema_version':1,'kind':'morphology_bundle','archive_root':prefix,
              'source_name':metadata.get('source_name'),'source_sha256':metadata.get('source_sha256'),
              'analysis_mode':source_mode,'npz_variable':metadata.get('npz_variable'),
              'npz_stage':metadata.get('npz_stage'),'npz_stages':metadata.get('npz_stages'),'files':files,
              'note':'成果包按来源、配置、分析模式和导出结果保存；manifest及ZIP自身不列入自引用哈希。'}
    (output/'morphology_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    manifest_path=output/'morphology_manifest.json'
    paths.append(manifest_path)
    with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED) as bundle:
        for path in dict.fromkeys(paths):
            if path in (archive,temporary) or path.suffix=='.tmp':continue
            if path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(job_dir.resolve()):
                relative=path.relative_to(job_dir).as_posix()
                archive_path=f'{prefix}/报告/清单.json' if relative=='outputs/morphology_manifest.json' else next((item['archive_path'] for item in files if item['path']==relative),None)
                if archive_path:bundle.write(path,archive_path)
    temporary.replace(archive)
    return archive


def prepare_export(service,payload):
    source_id=service.validate_id(payload.get('source_job_id'))
    source=service.get_job(source_id)
    if source.get('kind')!='morphology_analysis' or source.get('state')!='completed':
        raise ValueError('高清导出必须来自已完成的形貌分析任务')
    formats=payload.get('formats',['pdf','svg'])
    if not isinstance(formats,list) or not formats or any(f not in ('png','pdf','svg') for f in formats):
        raise ValueError('导出格式只能为 PNG、PDF 或 SVG')
    folder=service.runtime/'jobs'/source_id
    modes=['ga','detail'] if source['spec']['analysis_mode']=='both' else ['single']
    stages=source['spec'].get('npz_stages')
    if stages:
        modes=[f'stage_{stage:03d}'+('/'+mode if mode!='single' else '') for stage in stages for mode in modes]
    for mode in modes:
        out=folder/'outputs'/(mode if mode!='single' else '')
        for name in ('analysis_arrays.npz','analysis_report.json'):
            if not (out/name).is_file() or (out/name).is_symlink():raise ValueError('来源缺少可复用的分析数组或报告，请重新分析')
        with np.load(out/'analysis_arrays.npz',allow_pickle=False) as data:
            if 'pit_diameter_cells' not in data:raise ValueError('旧任务未保存完整分析数组，请重新分析后导出')
    source_spec=source.get('spec') or {}
    return dict(kind='morphology_export',source_job_id=source_id,modes=modes,
                source_name=source_spec.get('source_name'),source_sha256=source_spec.get('source_sha256'),
                npz_variable=source_spec.get('npz_variable'),npz_stage=source_spec.get('npz_stage'),
                npz_stages=stages,analysis_mode=source_spec.get('analysis_mode'),
                formats=list(dict.fromkeys(formats)),case_name='形貌分析高清导出'),folder


def freeze_export(spec,source,job_dir):
    dest=job_dir/'inputs'
    # Include the frozen source and configuration for a self-contained archive.
    shutil.copy2(source/'inputs/source.npz',dest/'source.npz')
    shutil.copy2(source/'spec.json',dest/'source_spec.json')
    hashes={}
    for mode in spec['modes']:
        out=source/'outputs'/(mode if mode!='single' else '')
        target=dest/mode;target.mkdir(parents=True)
        for name in ('analysis_arrays.npz','analysis_report.json'):
            shutil.copy2(out/name,target/name)
            hashes[f'{mode}/{name}']=sha256(target/name)
    spec['input_hashes']=hashes


def run_export(spec,job_dir,progress=None):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from morphology_analysis import export_analysis
    from depth_distribution_diagnostics import prepare_depth_samples
    from .runner import _atomic_json
    reports={}
    for mode in spec['modes']:
        if progress:progress({'phase':'plot','label':mode})
        root=job_dir/'inputs'/mode
        for name in ('analysis_arrays.npz','analysis_report.json'):
            if sha256(root/name)!=spec['input_hashes'][f'{mode}/{name}']:
                raise ValueError('冻结分析数据已改变，拒绝导出')
        report=json.loads((root/'analysis_report.json').read_text(encoding='utf-8'))
        with np.load(root/'analysis_arrays.npz',allow_pickle=False) as saved:
            result={key:saved[key] for key in ('baseline_um','max_locs','pit_depth_cells','pit_diameter_cells')}
            result['jsb']=saved['log_ratio']
        result.update(metadata=report['metadata'],report=report,
            samples=prepare_depth_samples(result['pit_depth_cells'],report['space_z_um'],report['normalization']))
        output=job_dir/'outputs'/(mode if mode!='single' else '')
        try:
            figures=export_analysis(result,output,source_name=report['metadata']['source_name'],
                                    dpi=300,formats=spec['formats'])
            for figure in figures:plt.close(figure)
        finally:plt.close('all')
        reports[mode]=report
    if spec.get('npz_stages'):
        rows=[]
        for stage in spec['npz_stages']:
            prefix=f'stage_{stage:03d}'
            rows.append({'stage':stage,**({'modes':{mode:reports[prefix+'/'+mode] for mode in ('ga','detail')}}
                        if spec['analysis_mode']=='both' else {'report':reports[prefix]})})
        summary={key:spec.get(key) for key in ('npz_stages','npz_variable','source_name','source_sha256')}
        summary['stages']=rows
    else:
        summary=reports['single'] if 'single' in reports else {'modes':reports}
    _atomic_json(job_dir/'outputs/summary.json',summary)
    write_morphology_archive(job_dir)
    return summary

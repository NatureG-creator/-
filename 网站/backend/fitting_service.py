"""通用拟合任务：读取、冻结、运行及可审计导出。"""
from __future__ import annotations

import json
import shutil
import time
import zipfile
from pathlib import Path

from .fitting_data import load_table, prepare_dataset, MAX_BYTES
from .runner import _atomic_json
from .system_info import sha256


METRIC_HELP=[
    ('cv_rmse','验证 RMSE','默认推荐：原Y单位的验证误差，对大误差较敏感；越小越好。'),
    ('cv_mae','验证 MAE','原Y单位的验证绝对误差；越小越好。'),
    ('aicc','AICc','普通最小二乘、同方差未知方差高斯误差及样本量足够时的相对比较；越小越好。'),
    ('bic','BIC','满足同一似然口径时比较拟合与复杂度；越小越好。'),
    ('rmse','训练 RMSE','训练内误差，容易偏向复杂模型；应结合验证误差。'),
    ('mae','训练 MAE','训练内绝对误差；不能单独证明预测性能。'),
    ('r2','R²','训练内解释程度，越大越好；常量Y不定义。'),
    ('adjusted_r2','调整 R²','考虑参数数目的训练内解释程度；越大越好。'),
]


def fitting_catalog():
    from .fitting_engine import model_catalog, normalise_fit_options
    from .fitting_outputs import normalise_plot_options
    from .fitting_multivariate import multivariate_model_catalog, normalise_multivariate_options
    return dict(models=model_catalog(), multivariate_models=multivariate_model_catalog(), metrics=[dict(id=i,label=l,help=h) for i,l,h in METRIC_HELP],
                defaults=normalise_fit_options({}),plot_defaults=normalise_plot_options({}),
                multivariate_defaults=normalise_multivariate_options({}),
                limits=dict(rows=5000,columns=64,groups=10,bytes=MAX_BYTES),
                origin=dict(state='direct_plotting',note='提供Origin交换文件，并支持从已完成拟合结果创建独立Origin绘图任务；本机安装与依赖见Origin能力检测，实际运行以绘图任务记录为准。'))


def _source_table(service,source):
    if not isinstance(source,dict):raise ValueError('source必须是对象')
    if source.get('upload_id'):
        if source.get('text'):raise ValueError('上传文件与粘贴文本只能选择一种')
        record,path=service.get_upload(source['upload_id'])
        if sha256(path)!=record['sha256']:raise ValueError('上传源文件已经改变，请重新上传')
        table=load_table(path,sheet=source.get('sheet'),variable=source.get('variable'))
        return table,dict(type='upload',name=record['name'],sha256=record['sha256'],sheet=table['sheet'],variable=table['variable']),path
    text=source.get('text')
    table=load_table(text=text)
    import hashlib
    return table,dict(type='text',name='pasted_data.txt',sha256=hashlib.sha256(text.encode('utf-8')).hexdigest()),None


def inspect_fitting(service,source):
    started=time.perf_counter()
    table,info,_=_source_table(service,source)
    return dict(table,rows=table.get('category_rows',table['rows'])[:20],category_rows=table.get('category_rows',[])[:20],preview_rows=min(20,len(table['rows'])),source=info,
                reading_seconds=time.perf_counter()-started)


def _prepare(service,payload):
    from .fitting_engine import normalise_fit_options
    from .fitting_outputs import normalise_plot_options
    started=time.perf_counter()
    table,info,path=_source_table(service,payload.get('source',{}))
    selection=payload.get('selection',{})
    dataset=prepare_dataset(table,selection)
    options=normalise_fit_options(payload.get('options',{}))
    plot=normalise_plot_options(payload.get('plot',{}))
    for key in ('x_label','y_label','x_unit','y_unit'):
        if not payload.get('plot',{}).get(key):plot[key]=dataset[key]
    if options['validation']=='group' and dataset['validation_groups'] is None:
        raise ValueError('按试件验证必须另选验证分组列；它与分类拟合列含义不同')
    if options['validation']=='loo' and len(dataset['x'])>100:raise ValueError('留一验证最多100行，请选择K折或分组验证')
    for axis in ('x','y'):
        if plot.get(axis+'_scale')=='log' and any(value<=0 for value in dataset[axis]):
            raise ValueError(f'{axis.upper()}对数坐标要求保留数据全部严格为正，不会自动删除点')
    warnings=[]
    if options['metric'] in {'rmse','mae','r2','adjusted_r2'}:
        warnings.append('当前按训练内指标排名，不能据此认定预测最佳；请同时检查验证误差。')
    if options['validation']=='kfold':warnings.append('随机K折假定观测独立；时间数据或同一试件重复测量请改选相应验证方式。')
    if any(options.get('prediction_'+bound) is not None and
           (options['prediction_'+bound]<min(dataset['x']) or options['prediction_'+bound]>max(dataset['x']))
           for bound in ('min','max')):warnings.append('预测范围包含观测区间外部；外推可靠性没有因拟合得分较高而得到证明。')
    if dataset['audit']['duplicate_x_count']:warnings.append('存在重复X，已保留；请确认是否为重复测量并设置合适的验证分组。')
    spec=dict(kind='fitting',selection=selection,options=options,plot=plot,source=info,
              reading_seconds=time.perf_counter()-started,warnings=warnings)
    return spec,table,dataset,path


def _prepare_multivariate(service, payload):
    from .fitting_data import prepare_multivariate_dataset
    from .fitting_multivariate import normalise_multivariate_options
    from .fitting_outputs import normalise_plot_options
    started = time.perf_counter()
    table, info, path = _source_table(service, payload.get('source', {}))
    selection = payload.get('selection', {})
    dataset = prepare_multivariate_dataset(table, selection)
    options = normalise_multivariate_options(payload.get('options', {}))
    plot = normalise_plot_options(payload.get('plot', {}))
    warnings = ['双自变量图形默认展示三维响应面、切片和残差；外推区域不代表物理规律。']
    spec = dict(kind='fitting', fitting_mode='multivariate2', selection=selection, options=options, plot=plot, source=info,
                reading_seconds=time.perf_counter() - started, warnings=warnings)
    return spec, table, dataset, path


def precheck_fitting(service,payload):
    if payload.get('mode') == 'multivariate2' or payload.get('selection', {}).get('mode') == 'multivariate2':
        spec, _, dataset, _ = _prepare_multivariate(service, payload)
        from .fitting_multivariate import profile_multivariate_data
        profile = profile_multivariate_data(dataset, [dataset['x1_label'], dataset['x2_label'], dataset['y_label']])
        return dict(mode='multivariate2', dataset=dict(row_count=len(dataset['y']), group_count=len(set(dataset['groups'])),
                    x1_range=[min(dataset['x1']), max(dataset['x1'])], x2_range=[min(dataset['x2']), max(dataset['x2'])],
                    y_range=[min(dataset['y']), max(dataset['y'])], audit=dataset['audit'], x1_label=dataset['x1_label'], x2_label=dataset['x2_label'], y_label=dataset['y_label']),
                    options=spec['options'], plot=spec['plot'], source=spec['source'], warnings=spec['warnings'], reading_seconds=spec['reading_seconds'],
                    recommendation=dict(metric='cv_rmse', reason='双自变量默认使用原Y单位交叉验证RMSE，并优先比较交互项和二次响应面。'), profile=profile)
    spec,_,dataset,_=_prepare(service,payload)
    options=spec['options']
    recommendation=dict(metric='cv_mae' if options['loss']=='soft_l1' else 'cv_rmse',validation=options['validation'],
                        reason='默认用原Y单位的验证RMSE比较预测误差；不以训练R²单独选最佳。')
    if options['loss']=='soft_l1':recommendation['reason']='已选择稳健损失，建议同时优先检查验证MAE，降低少量大误差对评价的支配。'
    if options['validation']=='kfold' and len(dataset['x'])<=20:
        recommendation.update(validation='loo',reason=recommendation['reason']+' 当前样本较少；若观测独立，可比较留一验证。重复测量和时间序列仍应按其结构划分。')
    return dict(dataset=dict(row_count=len(dataset['x']),group_count=len(set(dataset['groups'])),
                    x_range=[min(dataset['x']),max(dataset['x'])],y_range=[min(dataset['y']),max(dataset['y'])],
                    audit=dataset['audit'],x_label=dataset['x_label'],y_label=dataset['y_label']),
                options=spec['options'],plot=spec['plot'],source=spec['source'],warnings=spec['warnings'],
                reading_seconds=spec['reading_seconds'],recommendation=recommendation)


def prepare_fitting(service,payload):
    if payload.get('mode') == 'multivariate2' or payload.get('selection', {}).get('mode') == 'multivariate2':
        spec, table, _, path = _prepare_multivariate(service, payload)
        return spec, table, path, payload.get('source', {}).get('text')
    spec,table,_,path=_prepare(service,payload)
    return spec,table,path,payload.get('source',{}).get('text')


def freeze_fitting(spec,table,path,text,job_dir):
    target=job_dir/'inputs'/'table.json'
    _atomic_json(target,table)
    spec['table_path']='inputs/table.json';spec['table_sha256']=sha256(target)
    original=job_dir/'inputs'/('source'+Path(path).suffix if path else 'pasted_data.txt')
    if path:shutil.copy2(path,original)
    else:original.write_text(text,encoding='utf-8',newline='')
    if sha256(original)!=spec['source']['sha256']:raise ValueError('冻结时原始数据改变，请重新提交')
    spec['source_path']='inputs/'+original.name


def run_fitting(spec,job_dir,progress=None):
    if spec.get('fitting_mode') == 'multivariate2':
        return run_multivariate_fitting(spec, job_dir, progress=progress)
    from .fitting_engine import fit_dataset
    from .fitting_outputs import write_fitting_outputs
    started=time.perf_counter();timing=dict(reading_seconds=spec['reading_seconds'])
    def update(changes):
        if progress:progress(dict(changes,progress=100*changes.get('progress',0)))
    table_path=job_dir/spec['table_path']
    if sha256(table_path)!=spec['table_sha256'] or sha256(job_dir/spec['source_path'])!=spec['source']['sha256']:
        raise ValueError('冻结数据校验失败，拒绝计算')
    dataset=prepare_dataset(json.loads(table_path.read_text(encoding='utf-8')),spec['selection'])
    output=job_dir/'outputs';output.mkdir(exist_ok=True)
    _atomic_json(output/'input_audit.json',dataset['audit'])
    _atomic_json(output/'fitting_config.json',dict(selection=spec['selection'],options=spec['options'],plot=spec['plot'],source=spec['source']))
    fit_started=time.perf_counter()
    result=fit_dataset(dataset,spec['options'],progress=update)
    timing['fitting_seconds']=time.perf_counter()-fit_started
    if progress:progress(dict(phase='plot',message='生成拟合图、诊断图与Origin数据包'))
    plot_started=time.perf_counter()
    outputs=write_fitting_outputs(result,dataset,output,spec['plot'])
    timing['plot_export_seconds']=time.perf_counter()-plot_started
    timing['elapsed_before_archive_seconds']=time.perf_counter()-started
    import platform
    import numpy,scipy,matplotlib
    result.update(outputs)
    result.update(kind='fitting',job_id=job_dir.name,selection=spec['selection'],options=spec['options'],
                  plot=spec['plot'],source=spec['source'],input_audit=dataset['audit'],timing=timing,
                  warnings=spec['warnings']+result.get('warnings',[]),
                  versions=dict(python=platform.python_version(),numpy=numpy.__version__,scipy=scipy.__version__,matplotlib=matplotlib.__version__),
                  scope_note='候选显式函数中的相对比较；不证明全局最佳或外推物理有效。单X单Y，各分类独立拟合；共享参数联合拟合和样条未接入。',
                  origin=dict(state='export_only',note='本拟合任务提供数据和origin_import.py；实际Origin绘图请从结果页创建独立绘图任务，运行状态以该任务记录为准。'))
    # 图形与数值先落盘，打包失败也保留结果。
    _atomic_json(output/'summary.json',result)
    files=[dict(name=p.name,sha256=sha256(p)) for p in sorted(output.iterdir()) if p.is_file() and p.name not in {'manifest.json','fitting_bundle.zip'}]
    files += [dict(name='inputs/'+p.name,sha256=sha256(p)) for p in sorted((job_dir/'inputs').iterdir()) if p.is_file()]
    _atomic_json(output/'manifest.json',dict(schema_version=1,kind='fitting',files=files,note='manifest及ZIP自身不列入自引用哈希；summary记录打包前耗时。'))
    with zipfile.ZipFile(output/'fitting_bundle.zip','w',zipfile.ZIP_DEFLATED) as bundle:
        for p in sorted(output.iterdir()):
            if p.is_file() and p.name!='fitting_bundle.zip':bundle.write(p,p.name)
        for p in sorted((job_dir/'inputs').iterdir()):
            if p.is_file():bundle.write(p,'inputs/'+p.name)
    return result


def run_multivariate_fitting(spec, job_dir, progress=None):
    import platform
    from .fitting_data import prepare_multivariate_dataset
    from .fitting_multivariate import fit_multivariate_dataset
    from .fitting_multivariate_outputs import write_multivariate_outputs
    started = time.perf_counter()
    table_path = job_dir / spec['table_path']
    if sha256(table_path) != spec['table_sha256'] or sha256(job_dir / spec['source_path']) != spec['source']['sha256']:
        raise ValueError('冻结数据校验失败，拒绝计算')
    dataset = prepare_multivariate_dataset(json.loads(table_path.read_text(encoding='utf-8')), spec['selection'])
    output = job_dir / 'outputs'; output.mkdir(exist_ok=True)
    _atomic_json(output / 'input_audit.json', dataset['audit'])
    _atomic_json(output / 'fitting_config.json', dict(mode='multivariate2', selection=spec['selection'], options=spec['options'], plot=spec['plot'], source=spec['source']))
    def update(changes):
        if progress: progress(dict(changes, progress=100 * changes.get('progress', 0)))
    result = fit_multivariate_dataset(dataset, spec['options'], progress=update)
    outputs = write_multivariate_outputs(result, dataset, output, spec['plot'])
    timing = dict(reading_seconds=spec['reading_seconds'], fitting_seconds=time.perf_counter() - started)
    result.update(outputs)
    result.update(kind='fitting', fitting_mode='multivariate2', job_id=job_dir.name, selection=spec['selection'], options=spec['options'], plot=spec['plot'], source=spec['source'], input_audit=dataset['audit'], timing=timing,
                  warnings=spec['warnings'] + result.get('warnings', []), versions=dict(python=platform.python_version()), scope_note='双自变量 Y=f(X1,X2)；支持二元线性、交互项和二次响应面，结果不替代物理模型。')
    _atomic_json(output / 'summary.json', result)
    files = [dict(name=p.name, sha256=sha256(p)) for p in sorted(output.iterdir()) if p.is_file() and p.name not in {'manifest.json', 'fitting_bundle.zip'}]
    _atomic_json(output / 'manifest.json', dict(schema_version=1, kind='fitting', fitting_mode='multivariate2', files=files))
    with zipfile.ZipFile(output / 'fitting_bundle.zip', 'w', zipfile.ZIP_DEFLATED) as bundle:
        for p in sorted(output.iterdir()):
            if p.is_file() and p.name != 'fitting_bundle.zip': bundle.write(p, p.name)
        for p in sorted((job_dir / 'inputs').iterdir()):
            if p.is_file(): bundle.write(p, 'inputs/' + p.name)
    return result

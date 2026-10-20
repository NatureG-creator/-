"""Benchmark physical interpretation using the inherited scientific definitions."""
from pathlib import Path
import numpy as np
from .scientific_outputs import actual_surface_metrics, PARAMETER_NAMES
from .config import source_config  # Registers the copied scientific engine import path.


def _load_selected(path, index=None):
    from corrosion_model.ga_优化版 import combine_objectives
    with np.load(path, allow_pickle=False) as data:
        objv=data['objv']
        if objv.ndim == 2 and objv.shape[1] == 6 and objv.shape[0] > 0:
            if not np.all(np.isfinite(objv)):
                raise ValueError('种群目标值包含非有限值')
            _, weighted=combine_objectives(objv)
            best=int(np.argmin(weighted))
            selected=best if index is None else index
            a_all=data['a']
            if a_all.ndim != 4 or a_all.shape[0] != len(objv) or not 0 <= selected < len(objv):
                raise ValueError('种群状态与目标维度不匹配')
            a=np.array(a_all[selected],copy=True)
            schema='population'
        elif objv.shape == (4,):
            best=selected=None
            a=np.array(data['a'],copy=True)
            if a.ndim != 3:
                raise ValueError('short_ga 状态必须为三维')
            schema='short_ga'
        else:
            raise ValueError('不支持的目标数组shape，期望(N,6)或(4,)')
        if min(a.shape) < 1 or a.shape[2] < 2 or not np.all(np.isfinite(a)):
            raise ValueError('状态为空、深度不足或包含非有限值')
        parameter=np.array(data['perfect_parameter'],copy=True) if 'perfect_parameter' in data else None
    return a,best,selected,schema,parameter


def physical_comparison(reference: Path, candidate: Path, config: dict,
                        plot_path: Path | None = None) -> dict:
    """Compare candidate at the reference's best index, without changing individuals."""
    from corrosion_model.ca_优化版 import first_metal_depth
    a,ref_best,index,schema,ref_parameter=_load_selected(reference)
    b,candidate_best,_,candidate_schema,candidate_parameter=_load_selected(candidate,index)
    if schema != candidate_schema or a.shape != b.shape:
        raise ValueError('参考与候选的工作负载或状态shape不匹配')
    w,l,z=a.shape
    space=float(config['GEOMETRY_CONFIG']['space_z_um'])
    reference_surface=(first_metal_depth(a,w,l,z-1)-1)*space
    candidate_surface=(first_metal_depth(b,w,l,z-1)-1)*space
    difference=candidate_surface-reference_surface
    mismatch=int(np.count_nonzero(difference))
    surface=dict(max_abs_diff_um=float(np.max(np.abs(difference))),
        rmse_um=float(np.sqrt(np.mean(difference*difference))),
        mean_delta_um=float(np.mean(difference)),mismatch_count=mismatch,
        mismatch_fraction=float(mismatch/difference.size),sample_count=int(difference.size),
        reference_min_um=float(reference_surface.min()),reference_max_um=float(reference_surface.max()),
        candidate_min_um=float(candidate_surface.min()),candidate_max_um=float(candidate_surface.max()))
    reference_metrics,reference_notes=actual_surface_metrics(a,config)
    candidate_metrics,candidate_notes=actual_surface_metrics(b,config)
    metrics={}
    for key,left in reference_metrics.items():
        right=candidate_metrics[key]
        metrics[key]=dict(reference=left,candidate=right,
            delta=None if left is None or right is None else float(right-left))
    notes=[]
    for label,items in (('reference',reference_notes),('candidate',candidate_notes)):
        notes.extend(dict(source=label,metric=key,reason=value) for key,value in items.items())
    result=dict(workload=schema,reference_best_index=ref_best,candidate_best_index=candidate_best,
        comparison_index=index,surface_depth=surface,metrics=metrics,notes=notes,
        surface_definition='(原 first_metal_depth - 1) × space_z_um',plot_file=None)
    if ref_parameter is not None and candidate_parameter is not None:
        if ref_parameter.shape == candidate_parameter.shape and ref_parameter.shape == (len(PARAMETER_NAMES),):
            result['parameters']={name:dict(reference=float(left),candidate=float(right),delta=float(right-left))
                for name,left,right in zip(PARAMETER_NAMES,ref_parameter,candidate_parameter)}
        else:
            notes.append(dict(source='comparison',metric='parameters',reason='参数shape不一致或不是原10参数格式，未比较。'))
    if plot_path is not None:
        _plot_surfaces(reference_surface,candidate_surface,difference,config,Path(plot_path))
        result['plot_file']=Path(plot_path).name
    return result


def _plot_surfaces(reference,candidate,difference,config,path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    # Downsample display only; all numerical comparisons above use the complete maps.
    w,l=reference.shape
    step=max(1,int(np.ceil(max(w,l)/600)))
    xy=float(config['GEOMETRY_CONFIG']['space_xy_um'])/1000
    extent=(0,l*xy,w*xy,0)
    lo=min(float(reference.min()),float(candidate.min()))
    hi=max(float(reference.max()),float(candidate.max()))
    span=max(float(np.max(np.abs(difference))),1e-12)
    figure,axes=plt.subplots(1,3,figsize=(12,3.8),constrained_layout=True)
    try:
        for axis,array,title,limits,cmap in zip(axes,(reference,candidate,difference),
                ('Reference','Candidate','Candidate - Reference'),((lo,hi),(lo,hi),(-span,span)),('viridis','viridis','coolwarm')):
            artist=axis.imshow(array[::step,::step],extent=extent,vmin=limits[0],vmax=limits[1],cmap=cmap)
            axis.set(title=title,xlabel='X (mm)',ylabel='Y (mm)')
            figure.colorbar(artist,ax=axis,label='Depth (um)')
        path.parent.mkdir(parents=True,exist_ok=True)
        figure.savefig(path,dpi=130)
    finally:
        plt.close(figure)

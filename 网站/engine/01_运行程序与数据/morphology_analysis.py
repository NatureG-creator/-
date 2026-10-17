"""Two explicit postprocess modes; CA updates and GA objectives are unchanged."""
from pathlib import Path
import csv
import importlib.util
import json
import numpy as np
from corrosion_model.analysis import moving_avg_3d, expand_matrix, jixiantiqu_3d
from unified_config import POSTPROCESS_CONFIG, MATLAB_CA_COMPARISON_CONFIG, matlab_ca_postprocess_settings
from depth_distribution_diagnostics import (prepare_depth_samples, make_report, summarize_values,
    export_diagnostics, plot_single_depth_distribution, plot_single_ratio_distribution)

MODE_LABELS = {'ga':'GA 同口径验收','detail':'精细形貌分析'}


def analyze_surface(state, *, mode='ga', space_xy_um, space_z_um, physical_layers=None, postprocess=None):
    if mode not in MODE_LABELS:
        raise ValueError('analysis_mode 只能为 ga 或 detail')
    a=np.asarray(state)
    if a.ndim!=3 or min(a.shape)<2 or not np.isfinite(a).all():
        raise ValueError('状态必须为有限三维数值数组，各维至少为2')
    for value in (space_xy_um,space_z_um):
        if not np.isfinite(value) or value<=0: raise ValueError('元胞尺寸必须为正数')
    inferred=physical_layers is None
    n=a.shape[2]-1 if inferred else physical_layers
    if isinstance(n,bool) or not isinstance(n,(int,np.integer)) or not 1<=n<=a.shape[2]:
        raise ValueError('物理Z层数与三维状态不符')
    pp=dict(POSTPROCESS_CONFIG if postprocess is None else postprocess)
    mc=MATLAB_CA_COMPARISON_CONFIG
    window=int(pp['auto_plot_window_size'] if mode=='ga' else pp['interactive_window_size'])
    factor=1 if mode=='ga' else int(pp['expand_factor'])
    if window<1 or window%2!=1 or factor<1:
        raise ValueError('平滑窗口必须为正奇数，放大倍数至少为1')
    baseline,_,_,depth_map=moving_avg_3d(a,window,*a.shape[:2],n,gaussian_sigma=float(pp['gaussian_sigma']))
    baseline=expand_matrix(baseline,factor)
    if mode=='ga':
        threshold,nh=matlab_ca_postprocess_settings(float(np.ptp(baseline)))
        prominence,distance=mc['min_prominence'],mc['min_distance']
    else:
        threshold,nh=pp['watershed_threshold'],pp['neighborhood']
        prominence,distance=pp['min_prominence'],pp['min_distance']
    depths,ratios,diameters,peaks,_,_,boundaries=jixiantiqu_3d(baseline,n,
        {'MinProminence':prominence,'MinDistance':distance,'Neighborhood':(nh,nh)},threshold)
    samples=prepare_depth_samples(depths,space_z_um,pp['log_normalization'])
    log_ratio=np.full(ratios.shape,np.nan)
    valid=np.isfinite(ratios)&(ratios>0)
    log_ratio[valid]=np.log(1/np.maximum(ratios[valid]/float(mc['sjb_divisor']),1e-12))
    metadata=dict(analysis_mode=mode,mode_label=MODE_LABELS[mode],state_shape=list(a.shape),
        physical_layers=int(n),layer_rule='旧交互脚本口径：末层作为附加层；请核对原模拟 grid_n' if inferred else '使用冻结配置的 grid_n',
        window_size=window,gaussian_sigma=float(pp['gaussian_sigma']),expand_factor=factor,
        min_prominence=float(prominence),min_distance=int(distance),neighborhood=int(nh),threshold=float(threshold),
        sjb_divisor=float(mc['sjb_divisor']),space_xy_um=float(space_xy_um),space_z_um=float(space_z_um),
        log_bin_width=float(mc['hist_bin_width']),boundary_fallback_count=sum(x.size==0 for x in boundaries),
        pit_depth_definition='原算法：(峰值-全局最小基准面+1)*space_z_um；空边界回退1层；不删除边缘坑')
    report=make_report(samples,metadata)
    report['log_ratio']=summarize_values(log_ratio)
    report['objective_note']='原四目标不约束完整分布必须正态；径深比标准差未直接参与，坑深对数均值/标准差误差按0.6/0.4合并。'
    return dict(baseline=baseline,baseline_um=(baseline-baseline.min())*space_z_um,
        depth_map=depth_map,max_locs=peaks,pit_depth_cells=depths,pit_diameter_cells=diameters,
        jsb=log_ratio,samples=samples,metadata=metadata,report=report)


def analysis_caption(report):
    m=report['metadata']
    return (f"{m['mode_label']} | n={report['valid_count']} | window={m['window_size']}, sigma={m['gaussian_sigma']:g}, "
            f"prom={m['min_prominence']:g}, distance={m['min_distance']}, neighborhood={m['neighborhood']}, threshold={m['threshold']:g}\n"
            f"XY/Z={m['space_xy_um']:g}/{m['space_z_um']:g} μm | expand={m['expand_factor']} | ratio divisor={m['sjb_divisor']:g} | "
            f"bins={m['log_bin_width']:g} | boundary fallback={m['boundary_fallback_count']} | {m.get('source_name','')}")


def annotate_analysis_figure(fig, report, distribution=None):
    text=analysis_caption(report)
    if distribution:
        summary=report[distribution]
        p=summary['shapiro_p']
        text+='\n'+summary['normality_note']+(f'；Shapiro p={p:.4g}' if p is not None else '')
        ax=fig.axes[0]
        if ax.lines:
            ax.lines[0].set_label('Normal reference curve')
            ax.legend(loc='upper right')
    fig.text(.5,.015,text,ha='center',va='bottom',fontsize=8,wrap=True)
    fig.tight_layout(rect=(0,.17 if distribution else .13,1,.94))


def export_analysis(result, output_dir, *, source_name, plot_mode='paper', dpi=160, raw_bin_width_um=None):
    """Reuse the original morphology view; write only into a new analysis directory."""
    import matplotlib.pyplot as plt
    from depth_distribution_diagnostics import plot_depth_comparison
    output=Path(output_dir);output.mkdir(parents=True,exist_ok=True)
    result['metadata']['source_name']=source_name
    report=result['report']
    export_diagnostics(result['samples'],report,output)
    with (output/'pit_ratio_samples.csv').open('w',encoding='utf-8-sig',newline='') as handle:
        writer=csv.writer(handle);writer.writerow(['pit_index','log_ratio','diameter_cells'])
        for k,(value,diameter) in enumerate(zip(result['jsb'],result['pit_diameter_cells']),1):
            writer.writerow([k,float(value) if np.isfinite(value) else '',float(diameter)])
    np.savez_compressed(output/'analysis_arrays.npz',baseline_um=result['baseline_um'],
        max_locs=result['max_locs'],pit_depth_cells=result['pit_depth_cells'],log_ratio=result['jsb'])
    figures=[]
    if plot_mode in {'paper','full'}:
        spec=importlib.util.spec_from_file_location('_corrosion_surface_view',Path(__file__).with_name('04_交互查看腐蚀形貌.py'))
        viewer=importlib.util.module_from_spec(spec);spec.loader.exec_module(viewer)
        viewer.configure_matplotlib()
        fig=viewer.plot_surface_and_contour(result['baseline_um'],result['max_locs'],
            result['metadata']['space_xy_um'],source_name,dpi=dpi)
        annotate_analysis_figure(fig,report);figures.append(('surface_and_contour',fig))
    if plot_mode in {'paper','single'}:
        fig=plot_single_depth_distribution(result['samples'],log_bin_width=result['metadata']['log_bin_width'],dpi=dpi)
        annotate_analysis_figure(fig,report,'log_depth');figures.append(('pit_depth_distribution',fig))
    if plot_mode in {'paper','full'}:
        fig=plot_single_ratio_distribution(result['jsb'],bin_width=result['metadata']['log_bin_width'],dpi=dpi)
        annotate_analysis_figure(fig,report,'log_ratio');figures.append(('ratio_distribution',fig))
    if plot_mode in {'comparison','full'}:
        fig=plot_depth_comparison(result['samples'],log_bin_width=result['metadata']['log_bin_width'],raw_bin_width_um=raw_bin_width_um,dpi=dpi)
        annotate_analysis_figure(fig,report)
        for ax,key in zip(fig.axes,('raw_depth_um','log_depth','normalized_log_depth')):
            summary=report[key]
            ax.set_title(ax.get_title()+'\n'+summary['normality_note'],fontsize=9)
            if ax.lines:
                ax.lines[0].set_label('Normal reference curve');ax.legend(loc='upper right',fontsize=8)
        figures.append(('pit_depth_comparison',fig))
    for name,fig in figures:
        for suffix in ('png','pdf','svg'): fig.savefig(output/f'{name}.{suffix}',dpi=dpi)
    (output/'analysis_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    return [fig for _,fig in figures]

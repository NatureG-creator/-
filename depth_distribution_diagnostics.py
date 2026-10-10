"""腐蚀坑深度分布诊断；仅变换和展示提取样本，不修改 CA 或极值算法。"""
from __future__ import annotations

import csv
import json
from pathlib import Path
import numpy as np
from scipy import stats


def prepare_depth_samples(depth_cells, space_z_um, normalization):
    """H 为提取算法输出的元胞层数乘 Z 间距；对数以 1 μm 为参考长度。"""
    space, factor = float(space_z_um), float(normalization)
    if not np.isfinite(space) or space <= 0:
        raise ValueError('Z 元胞尺寸必须为正的有限数值')
    if not np.isfinite(factor) or factor <= 0:
        raise ValueError('对数归一化因子 C 必须为正的有限数值')
    cells = np.asarray(depth_cells,dtype=float).reshape(-1)
    raw = cells * space
    valid = np.isfinite(raw) & (raw > 0)
    # 对零值、负值、NaN 和空数组不制造替代样本；记录并排除无效值。
    logs = np.full(raw.shape,np.nan)
    logs[valid] = np.log(raw[valid])
    return dict(depth_cells=cells,raw_depth_um=raw,valid_mask=valid,
                log_depth=logs,normalized_log_depth=logs/factor,
                normalization=factor,space_z_um=space)


def summarize_values(values):
    values = np.asarray(values,dtype=float)
    values = values[np.isfinite(values)]
    count = int(values.size)
    result = dict(count=count,mean=None,std=None,min=None,max=None,
                  skewness=None,shapiro_p=None,normality_note='样本不足，未检验')
    if count == 0:
        return result
    mean = float(np.mean(values))
    sigma = float(np.std(values,ddof=1)) if count > 1 and np.ptp(values) > 0 else 0.
    result.update(mean=mean,std=sigma,min=float(np.min(values)),max=float(np.max(values)))
    if sigma == 0:
        result['normality_note'] = '常数样本，不拟合正态曲线、不做正态检验'
    elif 3 <= count <= 5000:
        result['skewness'] = float(stats.skew(values,bias=False))
        p_value = float(stats.shapiro(values).pvalue)
        result['shapiro_p'] = p_value
        result['normality_note'] = ('在 5% 水平拒绝正态假设' if p_value < .05
                                    else '在 5% 水平未拒绝正态假设；不等于证明正态')
    elif count > 5000:
        result['skewness'] = float(stats.skew(values,bias=False))
        result['normality_note'] = '样本超过 5000，不使用 Shapiro p 值作判定'
    return result


def make_report(samples,metadata=None):
    valid = samples['valid_mask']
    return dict(metadata=metadata or {},formula='H=depth_cells*space_z_um; L=ln(H/(1 um)); Y=L/C',
                normalization=samples['normalization'],space_z_um=samples['space_z_um'],
                extracted_count=int(valid.size),valid_count=int(np.count_nonzero(valid)),
                invalid_count=int(np.count_nonzero(~valid)),
                raw_depth_um=summarize_values(samples['raw_depth_um'][valid]),
                log_depth=summarize_values(samples['log_depth'][valid]),
                normalized_log_depth=summarize_values(samples['normalized_log_depth'][valid]),
                note='正的常数 C 仅缩放横坐标，不改变偏态或使非正态样本变为正态。')


def export_diagnostics(samples,report,output_dir):
    output = Path(output_dir)
    output.mkdir(parents=True,exist_ok=True)
    csv_path, json_path = output/'pit_depth_samples.csv', output/'depth_distribution_summary.json'
    with csv_path.open('w',encoding='utf-8-sig',newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(['pit_index','depth_cells','depth_um','ln_depth_over_1um','ln_depth_over_1um_div_C','valid'])
        for index in range(samples['depth_cells'].size):
            numbers = [samples[key][index] for key in
                       ('depth_cells','raw_depth_um','log_depth','normalized_log_depth')]
            writer.writerow([index+1,*[float(x) if np.isfinite(x) else '' for x in numbers],
                             bool(samples['valid_mask'][index])])
    json_path.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    return csv_path,json_path


def plot_depth_comparison(samples,*,log_bin_width=.1,raw_bin_width_um=None,figsize=(18.,5.4),dpi=160):
    """同一批坑的原值、自然对数、归一化对数并排比较；曲线只作参考拟合。"""
    import matplotlib.pyplot as plt
    from corrosion_model.distribution import _matlab_bin_edges
    log_width = float(log_bin_width)
    if not np.isfinite(log_width) or log_width <= 0:
        raise ValueError('对数图柱宽必须为正的有限数值')
    if raw_bin_width_um is not None and (not np.isfinite(raw_bin_width_um) or raw_bin_width_um <= 0):
        raise ValueError('原始深度柱宽必须为正数，单位 μm')
    fig,axes = plt.subplots(1,3,figsize=figsize,dpi=dpi)
    valid = samples['valid_mask']
    panels = [
        ('raw_depth_um','原始腐蚀坑深度','H / μm','概率密度 (1/μm)',raw_bin_width_um),
        ('log_depth','腐蚀坑深度的自然对数','ln(H / 1 μm)','概率密度',log_width),
        ('normalized_log_depth',f"归一化对数深度（C={samples['normalization']:g}）",
         'ln(H / 1 μm) / C','概率密度',log_width),
    ]
    for ax,(key,title,xlabel,ylabel,width) in zip(axes,panels):
        values = samples[key][valid]
        summary = summarize_values(values)
        ax.set_title(f"{title}\n有效坑数 n={values.size}",fontsize=11)
        ax.set_xlabel(xlabel); ax.set_ylabel(ylabel)
        if values.size == 0:
            ax.text(.5,.5,'没有有效腐蚀坑样本',ha='center',va='center',transform=ax.transAxes)
            continue
        edges = (np.histogram_bin_edges(values,bins='auto') if width is None
                 else _matlab_bin_edges(values,float(width)))
        ax.hist(values,bins=edges,density=True,color='#9fd0f0',edgecolor='black',label='样本分布')
        if summary['std'] > 0:
            xs = np.linspace(edges[0],edges[-1],300)
            ax.plot(xs,stats.norm.pdf(xs,summary['mean'],summary['std']),color='#cf3030',label='正态拟合（参考）')
        ax.text(.03,.96,f"均值={summary['mean']:.4g}\n标准差={summary['std']:.4g}",
                transform=ax.transAxes,va='top',fontsize=9)
        ax.grid(alpha=.2); ax.legend(loc='best',fontsize=9)
    fig.tight_layout()
    return fig

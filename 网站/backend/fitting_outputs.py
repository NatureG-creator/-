"""通用拟合的可移植数值、科研图形与 Origin 交换输出。"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path
import re
import warnings


def normalise_plot_options(plot=None):
    source = dict(plot or {})
    result = {'title': '', 'x_label': 'X', 'y_label': 'Y', 'x_unit': '', 'y_unit': '',
              'theme': 'journal', 'width_mm': 180., 'height_mm': 140., 'dpi': 300,
              'font_size': 10., 'x_scale': 'linear', 'y_scale': 'linear'}
    result.update({k: v for k, v in source.items() if k in result})
    for key, lo, hi in [('width_mm', 80, 300), ('height_mm', 80, 300), ('dpi', 72, 600), ('font_size', 6, 24)]:
        try:
            value = float(result[key])
        except (TypeError, ValueError) as exc:
            raise ValueError(f'{key} 必须为有效数字') from exc
        if not math.isfinite(value) or not lo <= value <= hi:
            raise ValueError(f'{key} 必须在 {lo}–{hi} 范围内')
        result[key] = int(value) if key == 'dpi' else value
    # RGBA canvas plus render buffers: cap the raster at 30 million pixels.
    if result['width_mm'] * result['height_mm'] * (result['dpi'] / 25.4) ** 2 > 30_000_000:
        raise ValueError('图像尺寸与 DPI 组合超出内存预算')
    if result['theme'] not in ('journal', 'colorblind'):
        raise ValueError('theme 必须为 journal 或 colorblind')
    for axis in ('x', 'y'):
        if result[axis + '_scale'] not in ('linear', 'log'):
            raise ValueError(f'{axis}_scale 必须为 linear 或 log')
    for key in ('title', 'x_label', 'y_label', 'x_unit', 'y_unit'):
        result[key] = str(result[key] or '')[:240]
    return result


def validate_plot_data(dataset, plot=None):
    options = normalise_plot_options(plot)
    for axis in ('x', 'y'):
        if options[axis + '_scale'] == 'log':
            values = dataset.get(axis, [])
            if not values or any(v is None or not math.isfinite(float(v)) or float(v) <= 0 for v in values):
                raise ValueError(f'{axis.upper()} 对数坐标要求全部观测值大于零')
    return options


def _cell(value):
    if value is None:
        return ''
    if isinstance(value, (float, int)):
        return value if math.isfinite(value) else ''
    text = str(value)
    return "'" + text if text.lstrip().startswith(('=', '+', '-', '@', '\t', '\r', '\n')) else text


def _csv(path, columns, rows):
    with path.open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow([_cell(v) for v in columns])
        writer.writerows([_cell(v) for v in row] for row in rows)


def _at(values, index):
    return values[index] if values is not None and index < len(values) else None


def _safe_id(value):
    return re.sub('[^a-zA-Z0-9_-]', '_', str(value))[:60] or 'model'


def write_fitting_outputs(result, dataset, output_dir, plot=None):
    """写文件并返回供任务摘要/归档使用的文件名；不修改拟合结果。"""
    p = validate_plot_data(dataset, plot)
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    notes, files, plots = [], [], []
    n = len(dataset['x'])
    _csv(root / 'data.csv', ['row_id', 'group', 'x', 'y', 'sigma'],
         [(_at(dataset.get('row_ids'), i), _at(dataset.get('groups'), i), dataset['x'][i], dataset['y'][i], _at(dataset.get('sigma'), i)) for i in range(n)])
    files.append('data.csv')
    metric = result.get('metric', result.get('options', {}).get('metric', 'cv_rmse'))
    ranking = []
    curve_files = []
    for gi, group in enumerate(result.get('groups', []), 1):
        prefix = f'g{gi:03d}'
        for ci, c in enumerate(group.get('candidates', []), 1):
            base = f'{prefix}_{_safe_id(c.get("id", ci))}'
            # Duplicate IDs from external callers cannot overwrite one another.
            if base + '_curve.csv' in files:
                base += f'_{ci:03d}'
            ranking.append([group.get('label'), c.get('id'), c.get('label'), c.get('status'), c.get('id') == group.get('recommended_id'), c.get('formula'), c.get('metrics', {}).get(metric), c.get('error'), c.get('interval_reason'),
                            json.dumps(c.get('metric_reasons') or {}, ensure_ascii=False, allow_nan=False),
                            json.dumps(c.get('cv_valid'), ensure_ascii=False, allow_nan=False),
                            json.dumps(c.get('warnings') or [], ensure_ascii=False, allow_nan=False)])
            if c.get('status') not in ('success', 'ok'):
                continue
            curve = c.get('curve', {})
            keys = ['x', 'y', 'confidence_lower', 'confidence_upper', 'prediction_lower', 'prediction_upper']
            name = base + '_curve.csv'
            _csv(root / name, keys, [[_at(curve.get(k), i) for k in keys] for i in range(len(curve.get('x', [])))])
            files.append(name)
            curve_files.append(name)
            name = base + '_residuals.csv'
            keys = ['row_id', 'x', 'observed', 'fitted', 'residual', 'cv_prediction']
            gx = group.get('x', [])
            _csv(root / name, keys, [[_at(group.get('row_ids'), i), x, _at(group.get('y'), i), _at(c.get('y_fitted'), i), _at(c.get('residuals'), i), _at(c.get('cv_predictions'), i)] for i, x in enumerate(gx)])
            files.append(name)
            name = base + '_parameters.csv'
            _csv(root / name, ['parameter', 'value'], list(c.get('parameters', {}).items()))
            files.append(name)
    _csv(root / 'model_ranking.csv', ['group', 'model_id', 'model', 'status', 'recommended', 'formula', metric, 'error', 'interval_reason', 'metric_reasons', 'cv_valid', 'warnings'], ranking)
    files.append('model_ranking.csv')
    try:
        _render_figures(result, dataset, root, p, plots, files, notes, metric)
    except Exception as exc:
        notes.append(f'图形输出失败，数值 CSV 已保留：{type(exc).__name__}: {exc}')
    script = '''"""在安装 Origin 与 originpro 的外部 Python 中运行。"""
from pathlib import Path
import csv
try:
    import originpro as op
except ImportError:
    raise SystemExit("未安装 originpro；请在已配置 Origin 的 Python 中运行，不会自动安装软件。")
root = Path(__file__).resolve().parent
if not op.oext:
    raise SystemExit("请从 Origin 外部 Python 环境执行本脚本。")
try:
    op.set_show(True)
    op.new()
    for path in sorted(root.glob("*.csv")):
        sheet = op.new_sheet('w', lname=path.stem)
        sheet.from_file(str(path))
        if path.name.endswith('_curve.csv'):
            graph = op.new_graph(template='line')
            graph[0].add_plot(sheet, coly=1, colx=0, type='l')
        elif path.name == 'data.csv':
            graph = op.new_graph(template='scatter')
            graph[0].add_plot(sheet, coly=3, colx=2, type='s')
    op.save(str(root / 'fitting_results.opju'))
except Exception as exc:
    raise SystemExit('Origin 导入失败：' + str(exc))
'''
    (root / 'origin_import.py').write_text(script, encoding='utf-8')
    files.append('origin_import.py')
    readme = '''# 拟合结果与 Origin 交换包

data.csv 保留参与拟合的行号、分组、X、Y、标准差；剔除行审计见任务摘要。
model_ranking.csv 包含失败模型及失败原因；metric_reasons、cv_valid、warnings 三列为 JSON 单元格，保留指标无效与交叉验证不足的解释。每个成功模型另有参数、曲线/区间、残差与交叉验证预测 CSV。
诊断图依次为观测与拟合、残差散点、正态 QQ、实测与拟合预测对比。图中误差棒表示输入 sigma。
置信带（若可计算）表示均值拟合不确定性，预测带表示新观测不确定性；缺失区间不可解释为零不确定性。
观测 X 范围内曲线为实线，范围外为虚线；外推不保证可靠。推荐仅针对所选候选与验证规则。
PDF/SVG 为矢量图，PNG/TIFF 为所选 DPI 的位图；样式、尺寸、字体遵循任务绘图设置。
CSV 采用 UTF-8 BOM；文本以公式符号开头时添加单引号，防止表格软件执行公式。

## Origin 导入
将整个包解压到同一目录，在已安装 Origin、配置 originpro 的外部 Python 中运行 origin_import.py。
脚本相对自身路径导入全部 CSV、创建数据簿和散点/曲线图，并保存 fitting_results.opju。
本包不代表已通过本机 Origin 连接验证；缺少依赖时脚本明确退出，不会自动安装。
'''
    if notes:
        readme += '\n## 输出说明\n' + '\n'.join('- ' + note for note in notes) + '\n'
    (root / 'README.md').write_text(readme, encoding='utf-8')
    files.append('README.md')
    return {'plots': plots, 'files': files, 'warnings': notes, 'plot_options': p}


def _render_figures(result, dataset, root, p, plots, files, notes, metric):
    import numpy as np
    import matplotlib
    matplotlib.use('Agg')
    from matplotlib import font_manager
    from matplotlib.figure import Figure
    from scipy import stats

    available = {f.name for f in font_manager.fontManager.ttflist}
    font = next((f for f in ['Microsoft YaHei', 'SimHei', 'Noto Sans CJK SC', 'Source Han Sans SC'] if f in available), None)
    if not font:
        notes.append('系统未发现中文字体，图形使用英文标签；原始中文名称保留在 CSV。')
    def label(text, fallback):
        text = str(text or fallback)
        return text if font or text.isascii() else fallback
    colors = ['#0072B2', '#D55E00', '#009E73', '#CC79A7'] if p['theme'] == 'colorblind' else ['#286090', '#B64642', '#39805F', '#8D6AA8']
    def figure():
        return Figure(figsize=(p['width_mm']/25.4, p['height_mm']/25.4), layout='constrained')
    def save(fig, name, title):
        for ext in ('png', 'pdf', 'svg', 'tiff'):
            filename = name + '.' + ext
            fig.savefig(root / filename, dpi=p['dpi'], format=ext)
            files.append(filename)
        plots.append({'name': name + '.png', 'label': title})
        fig.clear()
    def axes_labels(ax):
        ax.set_xlabel(label(p['x_label'], 'X') + (f" ({label(p['x_unit'], '')})" if p['x_unit'] else ''))
        ax.set_ylabel(label(p['y_label'], 'Y') + (f" ({label(p['y_unit'], '')})" if p['y_unit'] else ''))
        ax.set_xscale(p['x_scale'])
        ax.set_yscale(p['y_scale'])
    def curve_plot(ax, c, gx, color, name):
        cv = c.get('curve', {})
        x = np.asarray(cv.get('x', []), dtype=float)
        y = np.asarray(cv.get('y', []), dtype=float)
        if not len(x) or len(y) != len(x):
            return
        valid = np.isfinite(x) & np.isfinite(y)
        if p['x_scale'] == 'log': valid &= x > 0
        if p['y_scale'] == 'log': valid &= y > 0
        order = np.argsort(x)
        x, y, valid = x[order], y[order], valid[order]
        lo, hi = min(gx), max(gx)
        # Draw consecutive segments so extrapolation connects at the boundary.
        for inside, style in [(True, '-'), (False, '--')]:
            for i in range(len(x)-1):
                midpoint = (x[i] + x[i+1]) / 2
                if valid[i:i+2].all() and (lo <= midpoint <= hi) == inside:
                    ax.plot(x[i:i+2], y[i:i+2], style, color=color, linewidth=1.4)
        ax.plot([], [], color=color, label=name)
        for low_key, high_key, alpha, caption in [('prediction_lower', 'prediction_upper', .08, '95% prediction'), ('confidence_lower', 'confidence_upper', .2, '95% mean CI')]:
            if cv.get(low_key) is None or cv.get(high_key) is None:
                continue
            lower, upper = np.asarray(cv[low_key], dtype=float), np.asarray(cv[high_key], dtype=float)
            if lower.shape != x.shape or upper.shape != x.shape:
                continue
            lower, upper = lower[order], upper[order]
            good = valid & np.isfinite(lower) & np.isfinite(upper) & (lower <= upper)
            if p['y_scale'] == 'log': good &= lower > 0
            ax.fill_between(x, lower, upper, where=good, color=color, alpha=alpha, label=caption)
    rc = {'font.family': font or 'DejaVu Sans', 'font.size': p['font_size'], 'axes.spines.top': False, 'axes.spines.right': False, 'svg.fonttype': 'path', 'pdf.fonttype': 42}
    recommendations = []
    with matplotlib.rc_context(rc):
        for gi, group in enumerate(result.get('groups', []), 1):
            prefix = f'g{gi:03d}'
            display = label(group.get('label'), f'Group {gi}')
            candidates = group.get('candidates', [])
            selected = next((c for c in candidates if c.get('id') == group.get('recommended_id') and c.get('status') in ('ok', 'success')), None)
            gx, gy = group.get('x', []), group.get('y', [])
            if selected is None:
                notes.append(f'{group.get("label", gi)}：没有可推荐模型，未生成推荐诊断图。')
            elif gx:
                recommendations.append((group, selected, display))
                fig = figure()
                fit, resid, qq, parity = fig.subplots(2, 2).flat
                ids = group.get('row_ids', [])
                sigma_by_id = dict(zip(dataset.get('row_ids', []), dataset.get('sigma') or []))
                sigma = [sigma_by_id.get(rid) for rid in ids]
                if len(sigma) == len(gx) and all(v is not None and math.isfinite(float(v)) and v > 0 for v in sigma):
                    fit.errorbar(gx, gy, yerr=sigma, fmt='o', markersize=3, color=colors[0], capsize=2, label='Observed ± sigma')
                else:
                    fit.scatter(gx, gy, s=14, color=colors[0], label='Observed')
                curve_plot(fit, selected, gx, colors[1], label(selected.get('label'), 'Fit'))
                axes_labels(fit)
                fit.legend(fontsize=max(6, p['font_size']-3))
                fit.set_title('Fit and uncertainty')
                residual = np.asarray(selected.get('residuals', []), dtype=float)
                fitted = np.asarray(selected.get('y_fitted', []), dtype=float)
                if len(residual) == len(gx):
                    resid.scatter(gx, residual, s=12, color=colors[0])
                    finite_resid = residual[np.isfinite(residual)]
                    if len(finite_resid) >= 2:
                        (theory, ordered), (slope, intercept, _) = stats.probplot(finite_resid)
                        qq.scatter(theory, ordered, s=12, color=colors[0])
                        qq.plot(theory, intercept + slope * theory, color=colors[1])
                resid.axhline(0, color='0.4', linewidth=.7)
                resid.set(xlabel=label(p['x_label'], 'X'), ylabel='Residual', title='Residuals')
                resid.set_xscale(p['x_scale'])
                qq.set(xlabel='Theoretical normal quantiles', ylabel='Ordered residuals', title='Normal Q-Q')
                if len(fitted) == len(gy):
                    parity.scatter(gy, fitted, s=14, color=colors[0], label='In-sample')
                    cv = np.asarray(selected.get('cv_predictions') or [], dtype=float)
                    if len(cv) == len(gy):
                        valid = np.isfinite(cv)
                        parity.scatter(np.asarray(gy)[valid], cv[valid], marker='x', s=16, color=colors[2], label='Cross-validation')
                    lower, upper = min(gy), max(gy)
                    parity.plot([lower, upper], [lower, upper], '--', color='0.4')
                parity.set(xlabel='Observed Y', ylabel='Predicted Y', title='Observed vs predicted')
                parity.set_xscale(p['y_scale'])
                parity.set_yscale(p['y_scale'])
                parity.legend(fontsize=max(6, p['font_size']-3))
                fig.suptitle(label(p['title'], display))
                save(fig, prefix + '_diagnostics', display + ' diagnostics')
            valid_candidates = [(c, c.get('metrics', {}).get(metric)) for c in candidates]
            valid_candidates = [(c, v) for c, v in valid_candidates if isinstance(v, (int, float)) and math.isfinite(v)]
            if valid_candidates:
                fig = figure()
                ax = fig.subplots()
                ax.barh([label(c.get('label'), str(c.get('id'))) for c, v in valid_candidates], [v for c, v in valid_candidates], color=colors[0])
                ax.set(xlabel=metric, title=f'{display}: model comparison')
                save(fig, prefix + '_models', display + ' model comparison')
        if len(recommendations) > 1:
            fig = figure()
            ax = fig.subplots()
            for index, (group, candidate, display) in enumerate(recommendations):
                curve_plot(ax, candidate, group['x'], colors[index % len(colors)], display)
            axes_labels(ax)
            ax.legend(fontsize=max(6, p['font_size']-2))
            ax.set_title('Recommended fits by group')
            save(fig, 'group_comparison', 'Group comparison')

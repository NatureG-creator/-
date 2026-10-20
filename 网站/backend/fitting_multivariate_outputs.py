"""Scientific outputs for two-predictor response surfaces."""
from __future__ import annotations

import csv
import json
from pathlib import Path


def _csv(path, columns, rows):
    with Path(path).open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        writer.writerows(rows)


def write_multivariate_outputs(result, dataset, output_dir, plot=None):
    root = Path(output_dir); root.mkdir(parents=True, exist_ok=True)
    files = []; plots = []; notes = []
    rows = list(zip(dataset['row_ids'], dataset['x1'], dataset['x2'], dataset['y'], dataset.get('groups', [])))
    _csv(root / 'data_xyz.csv', ['row_id', 'X1', 'X2', 'Y', 'Group'], rows); files.append('data_xyz.csv')
    ranking = []
    for group_index, group in enumerate(result.get('groups', []), 1):
        for candidate in group.get('candidates', []):
            ranking.append([group.get('label'), candidate.get('id'), candidate.get('label'), candidate.get('status'), candidate.get('id') == group.get('recommended_id'), candidate.get('formula'), candidate.get('metrics', {}).get(result.get('metric')), candidate.get('error'), candidate.get('condition_number'), json.dumps(candidate.get('warnings') or [], ensure_ascii=False)])
        selected = next((c for c in group.get('candidates', []) if c.get('id') == group.get('recommended_id') and c.get('status') == 'ok'), None)
        if selected:
            prefix = f'g{group_index:03d}_{selected["id"]}'
            gx1, gx2, gy = group['x1'], group['x2'], group['y']
            pred = selected.get('y_fitted', [])
            _csv(root / f'{prefix}_residuals.csv', ['X1', 'X2', 'Observed_Y', 'Fitted_Y', 'Residual'], zip(gx1, gx2, gy, pred, selected.get('residuals', [])))
            files.append(f'{prefix}_residuals.csv')
            _write_surface(root, prefix, gx1, gx2, selected, files, plots, notes, plot or {})
    _csv(root / 'model_ranking.csv', ['group', 'model_id', 'model', 'status', 'recommended', 'formula', result.get('metric', 'cv_rmse'), 'error', 'condition_number', 'warnings'], ranking); files.append('model_ranking.csv')
    (root / 'origin_xyz_readme.txt').write_text('在 Origin 中将 data_xyz.csv 导入为 XYZ 工作表；X1、X2 为坐标列，Y 为响应列。曲面网格和切片 CSV 可直接导入绘图。\n', encoding='utf-8')
    files.append('origin_xyz_readme.txt')
    script = '''"""在安装 Origin 和 originpro 的外部 Python 中运行。"""
from pathlib import Path
try:
    import originpro as op
except ImportError:
    raise SystemExit("未安装 originpro；请在已安装 Origin 的 Python 环境中运行。")
root = Path(__file__).resolve().parent
if not op.oext:
    raise SystemExit("请从 Origin 外部 Python 环境执行此脚本。")
op.set_show(True)
op.new()
for path in sorted(root.glob("*.csv")):
    sheet = op.new_sheet("w", lname=path.stem)
    sheet.from_file(str(path))
op.save(str(root / "multivariate_results.opju"))
'''
    (root / 'origin_import_multivariate.py').write_text(script, encoding='utf-8'); files.append('origin_import_multivariate.py')
    return {'files': files, 'plots': plots, 'warnings': notes, 'multivariate_outputs': True}


def _write_surface(root, prefix, x1, x2, candidate, files, plots, notes, plot):
    import numpy as np
    try:
        import matplotlib
        matplotlib.use('Agg')
        from matplotlib import pyplot as plt
        from mpl_toolkits.mplot3d import Axes3D  # noqa: F401
        grid_count = min(45, max(15, int(plot.get('surface_points', 30))))
        a = np.linspace(min(x1), max(x1), grid_count); b = np.linspace(min(x2), max(x2), grid_count)
        aa, bb = np.meshgrid(a, b)
        # response surfaces are reconstructed from stored coefficients for built-in models.
        p = candidate.get('parameters', {})
        model_id = candidate.get('id')
        if model_id == 'linear2': zz = p['a'] * aa + p['b'] * bb + p['c']
        elif model_id == 'interaction2': zz = p['a'] * aa + p['b'] * bb + p['c'] * aa * bb + p['d']
        elif model_id == 'quadratic2': zz = p['a']*aa**2 + p['b']*bb**2 + p['c']*aa*bb + p['d']*aa + p['e']*bb + p['f']
        else:
            notes.append(f'{candidate.get("label", model_id)}：自定义公式暂不生成网格曲面，已保留数值结果。'); return
        grid_rows = zip(aa.ravel(), bb.ravel(), zz.ravel())
        grid_name = f'{prefix}_surface_grid.csv'; _csv(root / grid_name, ['X1', 'X2', 'Fitted_Y'], grid_rows); files.append(grid_name)
        fig = plt.figure(figsize=(7.2, 5.4)); ax = fig.add_subplot(111, projection='3d')
        ax.scatter(x1, x2, candidate.get('y_fitted', []), s=12, color='#286090', label='Observed fit')
        ax.plot_surface(aa, bb, zz, cmap='viridis', alpha=.55, linewidth=0)
        ax.set_xlabel('X1'); ax.set_ylabel('X2'); ax.set_zlabel('Y'); ax.set_title(f'{candidate.get("label", model_id)} response surface')
        for ext in ('png', 'svg', 'pdf'):
            name = f'{prefix}_surface.{ext}'; fig.savefig(root / name, dpi=int(plot.get('dpi', 300)), bbox_inches='tight'); files.append(name)
        plots.append({'name': f'{prefix}_surface.png', 'label': f'{candidate.get("label", model_id)} 三维响应面'})
        plt.close(fig)
        fig, ax = plt.subplots(figsize=(6.4, 5.0), constrained_layout=True)
        filled = ax.contourf(aa, bb, zz, levels=16, cmap='viridis')
        ax.scatter(x1, x2, s=12, c='#D55E00', edgecolors='white', linewidths=.3)
        ax.set_xlabel('X1'); ax.set_ylabel('X2'); ax.set_title(f'{candidate.get("label", model_id)} contour')
        fig.colorbar(filled, ax=ax, label='Fitted Y')
        name = f'{prefix}_contour.png'; fig.savefig(root / name, dpi=int(plot.get('dpi', 300)), bbox_inches='tight'); files.append(name); plots.append({'name': name, 'label': '双自变量等高线图'}); plt.close(fig)
        fig, axes = plt.subplots(1, 2, figsize=(9, 3.8), constrained_layout=True)
        axes[0].scatter(x1, candidate.get('y_fitted', []), s=12); axes[0].set_xlabel('X1'); axes[0].set_ylabel('Fitted Y')
        axes[1].scatter(x2, candidate.get('y_fitted', []), s=12, color='#D55E00'); axes[1].set_xlabel('X2'); axes[1].set_ylabel('Fitted Y')
        name = f'{prefix}_slices.png'; fig.savefig(root / name, dpi=int(plot.get('dpi', 300)), bbox_inches='tight'); files.append(name); plots.append({'name': name, 'label': '双自变量切片图'}); plt.close(fig)
    except Exception as exc:
        notes.append(f'双自变量图形输出失败，数值 CSV 已保留：{type(exc).__name__}: {exc}')

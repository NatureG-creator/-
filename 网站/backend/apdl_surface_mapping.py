"""Explicit double-face mapping in physical millimetres; never extrapolate."""
from __future__ import annotations

import math

import numpy as np
from scipy.interpolate import RegularGridInterpolator

MAPPING_WARNING = '共同XY映射使用双线性插值，粗网格可能遗漏窄坑峰值；仅保留共同覆盖区内的完整网格间隔，不外推。请核对深度范围及网格收敛，不能视为原始形貌等价。'


def _axes(metadata):
    ny, nx = metadata['shape']
    axes = [metadata[f'origin_{axis}_mm'] + np.arange(count)*metadata[spacing]
            for axis, count, spacing in (('y', ny, 'dy_mm'), ('x', nx, 'dx_mm'))]
    if any(not np.isfinite(a).all() or np.any(np.diff(a) <= 0) for a in axes):
        raise ValueError('表面坐标非有限或间距退化，无法映射')
    return axes


def common_grid(metadata, options):
    """Freeze a regular target lattice entirely inside the shared coverage."""
    from .apdl_geometry import _counts
    axes = {label: _axes(face) for label, face in metadata.items()}
    result = dict(mode='common_xy', method='bilinear', extrapolation=False,
                  spacing_policy='automatic_coarser_or_manual', sources={})
    counts = []
    for index, axis, spacing in ((0, 'y', 'dy_mm'), (1, 'x', 'dx_mm')):
        start = max(a[index][0] for a in axes.values())
        end = min(a[index][-1] for a in axes.values())
        if end <= start:
            raise ValueError('正反面没有二维共同覆盖区域，请检查物理原点、间距和配准')
        step = options.get('mapping_'+spacing) or max(m[spacing] for m in metadata.values())
        ratio = (end-start)/step
        if not math.isfinite(ratio):
            raise ValueError('共同网格目标间距过小')
        count = int(math.floor(ratio)) + 1
        if count < 2:
            raise ValueError('共同覆盖区域不足一个目标网格间隔，请减小目标间距')
        # Resolve floating-point boundary roundoff inward, never extrapolate.
        while count > 1 and start+(count-1)*step > end:
            count -= 1
        if count < 2:
            raise ValueError('共同覆盖区域不足一个目标网格间隔，请减小目标间距')
        result.update({f'origin_{axis}_mm': float(start), spacing: float(step),
                       f'{axis}_count': count,
                       f'overlap_{axis}_range_mm': [float(start), float(end)],
                       f'target_{axis}_range_mm': [float(start), float(start+(count-1)*step)]})
        counts.append(count)
    _counts(counts[1], counts[0], options['layers'], options['mesh_type'])
    for label, m in metadata.items():
        y, x = axes[label]
        result['sources'][label] = dict(shape=list(m['shape']), dx_mm=m['dx_mm'], dy_mm=m['dy_mm'],
            x_range_mm=[float(x[0]), float(x[-1])], y_range_mm=[float(y[0]), float(y[-1])],
            cropped=any(result[f'target_{axis}_range_mm'] != [float(a[0]), float(a[-1])]
                        for axis, a in (('x', x), ('y', y))))
    return result


def map_surfaces(depths, metadata, mapping):
    """Use exactly the frozen target lattice for precheck and worker execution."""
    x = mapping['origin_x_mm'] + np.arange(mapping['x_count'])*mapping['dx_mm']
    y = mapping['origin_y_mm'] + np.arange(mapping['y_count'])*mapping['dy_mm']
    xx, yy = np.meshgrid(x, y)
    points = np.column_stack((yy.ravel(), xx.ravel()))
    mapped = {}
    for label, depth in depths.items():
        axes = _axes(metadata[label])
        if list(depth.shape) != metadata[label]['shape']:
            raise ValueError('冻结表面尺寸与映射记录不一致')
        if any(target[0] < source[0] or target[-1] > source[-1]
               for target, source in zip((y, x), axes)):
            raise ValueError('目标网格超出来源覆盖范围，禁止外推')
        mapped[label] = RegularGridInterpolator(axes, depth, method='linear', bounds_error=True)(
            points).reshape(len(y), len(x))
        if not np.isfinite(mapped[label]).all() or np.any(mapped[label] < 0):
            raise ValueError('映射后的腐蚀深度无效')
    return mapped


def mapping_report(mapping, depths, mapped):
    """Add a depth audit without modifying original input metadata or arrays."""
    for label in depths:
        mapping['sources'][label].update(
            original_min_depth_mm=float(depths[label].min()),
            original_max_depth_mm=float(depths[label].max()),
            mapped_min_depth_mm=float(mapped[label].min()),
            mapped_max_depth_mm=float(mapped[label].max()))
    return mapping

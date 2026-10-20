"""Conforming solid mesh from positive depth[y, x] arrays, in millimetres.

This adapter never interpolates, rescales, clips, or modifies the corrosion model.
"""
from __future__ import annotations

import math
import numbers

import numpy as np

from .apdl_diagnostics import normalise_output_options
from .apdl_tetra import build_tetra_mesh


DEFAULTS = {
    'corrosion_mode': 'single_top', 'thickness_mm': 6., 'length_mm': 100.,
    'width_mm': 20., 'nx': 11, 'ny': 5, 'dx_mm': .05, 'dy_mm': .05,
    'origin_x_mm': 0., 'origin_y_mm': 0., 'layers': 3, 'E_MPa': 206000.,
    'poisson_ratio': .3, 'material_model': 'elastic', 'yield_MPa': 235.,
    'tangent_MPa': 1000., 'target_displacement_mm': .1, 'substeps': 10,
    'large_deflection': False, 'boundary_mode': 'poisson_free',
    'tensile_direction': 'X',
    'export_full_field': True, 'cores': 2, 'timeout_seconds': 3600,
    'restart_frequency': 1,
    'plastic_curve': None, 'allow_negative_slope': False,
    'max_substeps': 450, 'min_substeps': 1,
    'mesh_type': 'solid185_hex',
    'grip_length_fixed_mm': 0.,
    'grip_length_loaded_mm': 0.,
    'surface_grid_mode': 'strict',
    'mapping_dx_mm': None, 'mapping_dy_mm': None,
    'local_corrosion': False, 'patch_offset_x_mm': None, 'patch_offset_y_mm': None,
    'patch_rotation_deg': 0, 'patch_flip_x': False, 'patch_flip_y': False,
}
MODES = {'flat', 'single_top', 'single_bottom', 'double_independent', 'double_symmetric'}
MESH_TYPES = {'solid185_hex', 'solid187_tetra', 'solid285_tetra'}
MAX_NODES = 1_000_000
MAX_ELEMENTS = 750_000
TETRA_MAX_NODES = 1_200_000
TETRA_MAX_ELEMENTS = 1_000_000


def normalise_options(options: dict) -> dict:
    if not isinstance(options, dict):
        raise ValueError('APDL options 必须是对象。')
    result = {key: options.get(key, value) for key, value in DEFAULTS.items()}
    for key in ('thickness_mm', 'length_mm', 'width_mm', 'dx_mm', 'dy_mm',
                'E_MPa', 'yield_MPa', 'target_displacement_mm'):
        value = result[key]
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, numbers.Real) or not math.isfinite(value) or value <= 0:
            raise ValueError(f'{key} 必须是正的有限数值。')
        result[key] = float(value)
    for key in ('origin_x_mm', 'origin_y_mm', 'poisson_ratio', 'tangent_MPa'):
        value = result[key]
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, numbers.Real) or not math.isfinite(value):
            raise ValueError(f'{key} 必须是有限数值。')
        result[key] = float(value)
    for key, minimum, maximum in (('nx', 2, None), ('ny', 2, None), ('layers', 1, None),
                                  ('substeps', 1, 100000), ('max_substeps', 1, 100000),
                                  ('min_substeps', 1, 100000), ('cores', 1, 1024),
                                  ('timeout_seconds', 1, 86400), ('restart_frequency', 0, 100000)):
        value = result[key]
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, numbers.Real) or not math.isfinite(value) or int(value) != value or value < minimum or (maximum is not None and value > maximum):
            raise ValueError(f'{key} 必须是范围内的整数（最小 {minimum}）。')
        result[key] = int(value)
    for key in ('large_deflection', 'export_full_field', 'allow_negative_slope', 'local_corrosion'):
        if not isinstance(result[key], bool):
            raise ValueError(f'{key} 必须是布尔值。')
    for key in ('patch_offset_x_mm', 'patch_offset_y_mm'):
        value = result[key]
        if value is not None:
            if isinstance(value, (bool, np.bool_)) or not isinstance(value, numbers.Real) or not math.isfinite(value) or value < 0:
                raise ValueError(f'{key} 必须是有限且不小于 0 的数值或留空居中。')
            result[key] = float(value)
    rotation = result['patch_rotation_deg']
    if isinstance(rotation, (bool, np.bool_)) or not isinstance(rotation, numbers.Integral) or rotation not in (0, 90, 180, 270):
        raise ValueError('patch_rotation_deg 必须是 0、90、180 或 270 度。')
    result['patch_rotation_deg'] = int(rotation)
    for key in ('patch_flip_x', 'patch_flip_y'):
        if not isinstance(result[key], bool):
            raise ValueError(f'{key} 必须是布尔值。')
    if not isinstance(result['corrosion_mode'], str) or result['corrosion_mode'] not in MODES:
        raise ValueError('corrosion_mode 无效。')
    if result['surface_grid_mode'] not in ('strict', 'common_xy'):
        raise ValueError('双面网格模式必须为 strict 或 common_xy。')
    for key in ('mapping_dx_mm', 'mapping_dy_mm'):
        value = result[key]
        if value is not None:
            if isinstance(value, (bool, np.bool_)) or not isinstance(value, numbers.Real) or not math.isfinite(value) or value <= 0:
                raise ValueError(f'{key} 必须是正的有限数值或留空自动。')
            result[key] = float(value)
    if not isinstance(result['material_model'], str) or result['material_model'] not in {'elastic', 'bilinear_iso', 'multilinear_iso'}:
        raise ValueError('material_model 只支持 elastic、bilinear_iso 或 multilinear_iso。')
    if not isinstance(result['boundary_mode'], str) or result['boundary_mode'] not in {'poisson_free', 'clamped_grips', 'legacy_recommended'}:
        raise ValueError('boundary_mode 无效。')
    if not isinstance(result['tensile_direction'], str) or result['tensile_direction'] not in {'X', 'Y'}:
        raise ValueError('tensile_direction 只支持 X 或 Y。')
    if not isinstance(result['mesh_type'], str) or result['mesh_type'] not in MESH_TYPES:
        raise ValueError('mesh_type 只支持 solid185_hex、solid187_tetra 或 solid285_tetra。')
    for key in ('grip_length_fixed_mm', 'grip_length_loaded_mm'):
        value = result[key]
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, numbers.Real) or not math.isfinite(value) or value < 0:
            raise ValueError(f'{key} 必须是有限且不小于 0 的数值。')
        result[key] = float(value)
    if not -1 < result['poisson_ratio'] < .5:
        raise ValueError('poisson_ratio 必须满足 -1 < nu < 0.5。')
    if not 0 <= result['tangent_MPa'] < result['E_MPa']:
        raise ValueError('tangent_MPa 必须满足 0 <= Et < E。')
    if not result['min_substeps'] <= result['substeps'] <= result['max_substeps']:
        raise ValueError('子步设置必须满足 min_substeps <= substeps <= max_substeps。')
    curve = result['plastic_curve']
    if result['material_model'] == 'multilinear_iso' or curve is not None:
        if not isinstance(curve, list) or not 2 <= len(curve) <= 100:
            raise ValueError('plastic_curve 必须是 2 至 100 个 [塑性应变, 应力MPa] 点。')
        cleaned = []
        for point in curve:
            if not isinstance(point, (list, tuple)) or len(point) != 2 or any(
                    isinstance(v, (bool, np.bool_)) or not isinstance(v, numbers.Real) or not math.isfinite(v) for v in point):
                raise ValueError('plastic_curve 的每个点必须是两个有限实数，不能是布尔值。')
            strain, stress = map(float, point)
            if strain < 0 or stress <= 0 or (cleaned and strain <= cleaned[-1][0]):
                raise ValueError('塑性应变必须非负严格递增，且应力必须大于 0。')
            if cleaned and stress < cleaned[-1][1] and not result['allow_negative_slope']:
                raise ValueError('材料曲线含负斜率下降段，必须明确启用 allow_negative_slope 才能保留原曲线。')
            cleaned.append([strain, stress])
        if cleaned[0][0] != 0:
            raise ValueError('plastic_curve 首点塑性应变必须为 0。')
        result['plastic_curve'] = cleaned
    result.update(normalise_output_options(options))
    return result


def _depth(value: object, name: str) -> np.ndarray:
    array = np.asarray(value)
    if array.ndim != 2 or min(array.shape) < 2 or array.dtype.kind not in 'fiu':
        raise ValueError(f'{name} 必须是至少 2×2 的实数矩阵。')
    if not np.isfinite(array).all() or np.any(array < 0):
        raise ValueError(f'{name} 必须是有限且非负的向内腐蚀深度，不能包含 NaN/Inf。')
    return np.asarray(array, dtype=np.float64)


def _counts(nx: int, ny: int, layers: int, mesh_type: str = 'solid185_hex') -> tuple[int, int]:
    hex_count = (nx-1) * (ny-1) * layers
    if mesh_type in {'solid187_tetra', 'solid285_tetra'}:
        nodes = nx * ny * (layers + 1)
        elements = 6 * hex_count
        if mesh_type == 'solid187_tetra':
            nodes += ((nx-1)*ny*(layers+1) + nx*(ny-1)*(layers+1) + nx*ny*layers
                + (nx-1)*(ny-1)*(layers+1) + (nx-1)*ny*layers
                + nx*(ny-1)*layers + hex_count)
    else:
        nodes = nx * ny * (layers + 1)
        elements = hex_count
    max_nodes = MAX_NODES if mesh_type == 'solid185_hex' else TETRA_MAX_NODES
    max_elements = MAX_ELEMENTS if mesh_type == 'solid185_hex' else TETRA_MAX_ELEMENTS
    if nodes > max_nodes or elements > max_elements:
        raise ValueError(f'网格超过上限：节点 {nodes} / {max_nodes}，单元 {elements} / {max_elements}；请明确调整来源采样或厚度层数。')
    return nodes, elements


def build_geometry(top_depth: np.ndarray | None, bottom_depth: np.ndarray | None,
                   options: dict) -> dict:
    o = normalise_options(options)
    mode = o['corrosion_mode']
    if o['local_corrosion'] and mode == 'flat':
        raise ValueError('局部腐蚀区域需要选择单面或双面腐蚀模式。')
    if not o['local_corrosion'] and (o['patch_rotation_deg'] or o['patch_flip_x'] or o['patch_flip_y']):
        raise ValueError('腐蚀区域旋转和翻转只适用于局部腐蚀模式。')
    if mode == 'flat':
        nx, ny = o['nx'], o['ny']
        _counts(nx, ny, o['layers'], o['mesh_type'])
        top = np.zeros((ny, nx))
        bottom = np.zeros_like(top)
        o['dx_mm'], o['dy_mm'] = o['length_mm']/(nx-1), o['width_mm']/(ny-1)
    else:
        if mode in {'single_top', 'double_symmetric', 'double_independent'}:
            if top_depth is None:
                raise ValueError('当前腐蚀模式必须选择正面来源。')
            top = _depth(top_depth, '正面')
        if mode in {'single_bottom', 'double_independent'}:
            if bottom_depth is None:
                raise ValueError('当前腐蚀模式必须选择反面来源。')
            bottom = _depth(bottom_depth, '反面')
        if mode == 'single_top':
            bottom = np.zeros_like(top)
        elif mode == 'single_bottom':
            top = np.zeros_like(bottom)
        elif mode == 'double_symmetric':
            bottom = top.copy()
        if top.shape != bottom.shape:
            raise ValueError('正反面行列数不同，不允许静默重采样。')
        if o['local_corrosion']:
            rotation = o['patch_rotation_deg']
            if rotation:
                top = np.rot90(top, k=rotation // 90)
                bottom = np.rot90(bottom, k=rotation // 90)
                o['dx_mm'], o['dy_mm'] = o['dy_mm'], o['dx_mm']
            if o['patch_flip_x']:
                top = np.fliplr(top)
                bottom = np.fliplr(bottom)
            if o['patch_flip_y']:
                top = np.flipud(top)
                bottom = np.flipud(bottom)
            patch_ny, patch_nx = top.shape
            intervals_x = o['length_mm']/o['dx_mm']
            intervals_y = o['width_mm']/o['dy_mm']
            if not math.isfinite(intervals_x) or not math.isfinite(intervals_y):
                raise ValueError('完整平板尺寸与采样间距的比例超出可计算范围。')
            ix, iy = round(intervals_x), round(intervals_y)
            if ix < 1 or iy < 1 or not math.isclose(intervals_x, ix, rel_tol=1e-10, abs_tol=1e-10) or not math.isclose(intervals_y, iy, rel_tol=1e-10, abs_tol=1e-10):
                raise ValueError('完整平板长宽必须分别是 X/Y 网格间距的整数倍；当前结构化网格不支持非均匀边缘单元。')
            nx, ny = ix+1, iy+1
            _counts(nx, ny, o['layers'], o['mesh_type'])
            source_width, source_height = (patch_nx-1)*o['dx_mm'], (patch_ny-1)*o['dy_mm']
            if source_width > o['length_mm']+1e-10 or source_height > o['width_mm']+1e-10:
                raise ValueError('腐蚀区域尺寸大于完整平板，无法放置。')
            offsets = []
            for axis, supplied, span, source_span, spacing in (
                    ('X', o['patch_offset_x_mm'], o['length_mm'], source_width, o['dx_mm']),
                    ('Y', o['patch_offset_y_mm'], o['width_mm'], source_height, o['dy_mm'])):
                raw = (span-source_span)/2 if supplied is None else supplied
                index = round(raw/spacing)
                actual = index*spacing
                if supplied is not None and not math.isclose(raw, actual, rel_tol=1e-10, abs_tol=1e-10):
                    raise ValueError(f'腐蚀区域 {axis} 偏移必须落在完整平板网格线上（间距 {spacing:g} mm）。')
                if index < 0 or index + (patch_nx-1 if axis == 'X' else patch_ny-1) > (ix if axis == 'X' else iy):
                    raise ValueError(f'腐蚀区域超出完整平板 {axis} 范围。')
                offsets.append((index, actual))
            x_index, offset_x = offsets[0]
            y_index, offset_y = offsets[1]
            o.update(patch_offset_x_mm=offset_x, patch_offset_y_mm=offset_y)
            embedded_top = np.zeros((ny, nx), dtype=np.float64)
            embedded_bottom = np.zeros_like(embedded_top)
            embedded_top[y_index:y_index+patch_ny, x_index:x_index+patch_nx] = top
            embedded_bottom[y_index:y_index+patch_ny, x_index:x_index+patch_nx] = bottom
            top, bottom = embedded_top, embedded_bottom
            corrosion_region = {
                'x_range_mm': [o['origin_x_mm']+offset_x, o['origin_x_mm']+offset_x+source_width],
                'y_range_mm': [o['origin_y_mm']+offset_y, o['origin_y_mm']+offset_y+source_height],
                'nx': patch_nx, 'ny': patch_ny, 'offset_x_mm': offset_x, 'offset_y_mm': offset_y,
                'rotation_deg': rotation, 'flip_x': o['patch_flip_x'], 'flip_y': o['patch_flip_y'],
            }
            o.update(nx=nx, ny=ny)
        else:
            ny, nx = top.shape
            _counts(nx, ny, o['layers'], o['mesh_type'])
            o.update(nx=nx, ny=ny, length_mm=(nx-1)*o['dx_mm'], width_mm=(ny-1)*o['dy_mm'])
            corrosion_region = {
                'x_range_mm': [o['origin_x_mm'], o['origin_x_mm']+o['length_mm']],
                'y_range_mm': [o['origin_y_mm'], o['origin_y_mm']+o['width_mm']],
                'nx': nx, 'ny': ny, 'offset_x_mm': 0., 'offset_y_mm': 0.,
            }
    if mode == 'flat':
        corrosion_region = None
    _count_bound, element_count = _counts(nx, ny, o['layers'], o['mesh_type'])
    count = nx * ny * (o['layers'] + 1)
    tensile_direction = o['tensile_direction']
    axial_length = o['length_mm'] if tensile_direction == 'X' else o['width_mm']
    transverse_length = o['width_mm'] if tensile_direction == 'X' else o['length_mm']
    nominal_area = transverse_length*o['thickness_mm']
    original_volume = (o['length_mm']*nominal_area if tensile_direction == 'X'
                       else o['width_mm']*nominal_area)
    if not math.isfinite(nominal_area) or nominal_area <= 0 or not math.isfinite(original_volume) or original_volume <= 0:
        raise ValueError('名义面积或原始体积数值溢出或退化。')
    remaining = o['thickness_mm'] - top - bottom
    if not np.isfinite(remaining).all() or np.any(remaining <= 0):
        raise ValueError('腐蚀表面相交或穿透：剩余厚度必须处处大于 0；禁止自动裁剪修补。')
    x = o['origin_x_mm'] + np.arange(nx, dtype=float)*o['dx_mm']
    y = o['origin_y_mm'] + np.arange(ny, dtype=float)*o['dy_mm']
    if not np.isfinite(x).all() or not np.isfinite(y).all() or np.any(np.diff(x) <= 0) or np.any(np.diff(y) <= 0):
        raise ValueError('坐标数值范围导致非有限或退化间距，请调整原点和间距。')
    xx, yy = np.meshgrid(x, y)
    nodes = np.empty((count, 4), dtype=np.float64)
    nodes[:, 0] = np.arange(1, count+1)
    plane = nx*ny
    for layer in range(o['layers']+1):
        section = slice(layer*plane, (layer+1)*plane)
        nodes[section, 1], nodes[section, 2] = xx.ravel(), yy.ravel()
        nodes[section, 3] = (bottom + layer/o['layers']*remaining).ravel()
    # Counterclockwise lower face viewed from +Z, followed by corresponding upper face.
    base = np.arange(plane).reshape(ny, nx)[:-1, :-1].ravel()+1
    lower = np.column_stack((base, base+1, base+nx+1, base+nx))
    if o['mesh_type'] == 'solid185_hex':
        elements = np.empty((element_count, 9), dtype=np.int64)
        elements[:, 0] = np.arange(1, element_count+1)
        nc = len(base)
        for layer in range(o['layers']):
            section = slice(layer*nc, (layer+1)*nc)
            elements[section, 1:5] = lower+layer*plane
            elements[section, 5:9] = lower+(layer+1)*plane
        tetra_stats = {}
    else:
        nodes, elements, tetra_stats = build_tetra_mesh(
            nodes, nx, ny, o['layers'], o['dx_mm'], o['dy_mm'],
            quadratic=o['mesh_type'] == 'solid187_tetra',
            max_nodes=TETRA_MAX_NODES, max_elements=TETRA_MAX_ELEMENTS)
        element_count = len(elements)
    # Bilinear vertical columns have exact volume = area * mean corner thickness.
    cell_thickness = (remaining[:-1, :-1]+remaining[:-1, 1:]+remaining[1:, :-1]+remaining[1:, 1:])/4
    cell_volume = cell_thickness*o['dx_mm']*o['dy_mm']/o['layers']
    total_volume = float(cell_volume.sum()*o['layers'])
    if tetra_stats:
        tetra_stats['bilinear_reference_volume_mm3'] = total_volume
        tetra_stats['surface_volume_change_mm3'] = tetra_stats['actual_mesh_volume_mm3']-total_volume
        tetra_stats['surface_volume_change_fraction'] = tetra_stats['surface_volume_change_mm3']/total_volume
        total_volume = tetra_stats['actual_mesh_volume_mm3']
    if not math.isfinite(original_volume) or not np.isfinite(cell_volume).all() or np.any(cell_volume <= 0):
        raise ValueError('单元体积数值无效或退化。')
    max_aspect = 1.
    edges = ((0,1),(1,2),(2,3),(3,0),(4,5),(5,6),(6,7),(7,4),(0,4),(1,5),(2,6),(3,7))
    # Chunk evaluation bounds auxiliary memory for near-limit meshes.
    for start in range(0, element_count, 20000):
        corners = elements[start:start+20000, 1:9] if o['mesh_type'] == 'solid185_hex' else elements[start:start+20000, 1:5]
        points = nodes[corners-1, 1:]
        local_edges = edges if o['mesh_type'] == 'solid185_hex' else ((0,1),(1,2),(2,0),(0,3),(1,3),(2,3))
        lengths = np.stack([np.linalg.norm(points[:, b]-points[:, a], axis=1) for a,b in local_edges])
        if not np.isfinite(lengths).all() or np.any(lengths <= 0):
            raise ValueError('单元边长无效或退化。')
        max_aspect = max(max_aspect, float(np.max(lengths.max(axis=0)/lengths.min(axis=0))))
    i, j = np.unravel_index(np.argmin(remaining), remaining.shape)
    stats = {
        'nx': nx, 'ny': ny, 'thickness_layers': o['layers'], 'layers': o['layers'],
        'node_count': len(nodes), 'element_count': len(elements),
        'length_mm': o['length_mm'], 'width_mm': o['width_mm'],
        'min_remaining_thickness_mm': float(remaining.min()),
        'mean_remaining_thickness_mm': total_volume/(o['length_mm']*o['width_mm']),
        'max_remaining_thickness_mm': float(remaining.max()),
        'min_thickness_xy_mm': [float(x[j]), float(y[i])],
        'original_volume_mm3': original_volume, 'remaining_volume_mm3': total_volume,
        'volume_loss_mm3': original_volume-total_volume,
        'volume_loss_fraction': (original_volume-total_volume)/original_volume,
        'max_cell_aspect_ratio': max_aspect, 'min_cell_volume_mm3': tetra_stats.get('min_tetra_volume_mm3', float(cell_volume.min())),
        'nominal_area_mm2': nominal_area, 'mesh_type': o['mesh_type'],
    }
    stats.update(tetra_stats)
    if tetra_stats:
        coordinate = 1 if tensile_direction == 'X' else 2
        grip_axis = x if tensile_direction == 'X' else y
        tolerance = 32*np.finfo(float).eps*max(1., float(np.max(np.abs(nodes[:,coordinate]))))
        stats['grip_tolerance_mm'] = tolerance
        stats['fixed_grip_node_count'] = int(np.count_nonzero(np.abs(nodes[:,coordinate]-grip_axis[0]) <= tolerance))
        stats['loaded_grip_node_count'] = int(np.count_nonzero(np.abs(nodes[:,coordinate]-grip_axis[-1]) <= tolerance))
    if mode == 'flat':
        stats['analytic_stiffness_n_per_mm'] = o['E_MPa']*stats['nominal_area_mm2']/axial_length
        stats['analytic_force_n'] = stats['analytic_stiffness_n_per_mm']*o['target_displacement_mm']
    warnings = [
        ('网格采用原始XY采样及厚度方向结构化六面体；边长比和体积检查不等同于ANSYS单元质量验收。'
         if o['mesh_type'] == 'solid185_hex' else
         '采用全局一致的共形六分四面体，保留原始采样坐标与深度；此模式不自动加密。三角形表面与双线性面的体积差记录于统计报告。')]
    if max_aspect > 20:
        warnings.append(f'最大单元边长比为 {max_aspect:.3g}，建议检查网格收敛与厚度层数。')
    if mode == 'double_symmetric':
        warnings.append('双面对称模式明确复用同一正面深度，反面不另作独立随机生成。')
    if o['local_corrosion']:
        warnings.append('局部腐蚀贴片边缘按原始深度直接接入未腐蚀区域；未添加过渡带，边缘可能形成几何台阶。')
    if abs(tetra_stats.get('surface_volume_change_fraction', 0)) > .01:
        warnings.append('三角形表面与双线性参考面的总体积差超过1%；请复核表面离散及网格收敛性。')
    if mode == 'flat' and (o['boundary_mode'] != 'poisson_free' or o['material_model'] != 'elastic' or o['large_deflection']):
        warnings.append('EA/L、EAδ/L仅是小变形弹性自由泊松伸缩参考，当前约束或材料设置可能不满足其假设。')
    return dict(options=o, top_depth=top.copy(), bottom_depth=bottom.copy(),
                remaining=remaining, x=x, y=y, nodes=nodes, elements=elements,
                stats=stats, warnings=warnings, corrosion_region=corrosion_region)

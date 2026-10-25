"""Exact flat end platforms with explicit transition cells; source relief is preserved."""
from __future__ import annotations

import math
import numpy as np


def add_platforms(top: np.ndarray, bottom: np.ndarray, options: dict, *, reference_calibrations=None) -> dict:
    o = options
    empirical=o.get('platform_reference_mode','manual_mean')=='empirical_190'
    reference_calibrations=reference_calibrations or {}
    if o['local_corrosion']:
        raise ValueError('两侧平台与局部贴片模式不能同时启用；平台模式直接延长来源腐蚀区。')
    if o['mesh_type'] != 'solid185_hex':
        raise ValueError('两侧平台当前使用 SOLID185 结构化六面体，请选择 solid185_hex。')
    direction = o['tensile_direction']
    axis = 1 if direction == 'X' else 0
    spacing = o['dx_mm'] if axis == 1 else o['dy_mm']
    fixed, loaded = o['platform_fixed_mm'], o['platform_loaded_mm']
    if not all(math.isfinite(length / spacing) for length in (fixed, loaded)):
        raise ValueError('平台长度与轴向点距的比例超出可计算范围。')
    counts = [max(1, math.ceil(length / spacing)) for length in (fixed, loaded)]
    # Check counts before allocating extended coordinate or depth arrays.
    nx, ny = top.shape[1], top.shape[0]
    if axis == 1:
        nx += sum(counts) + 2
    else:
        ny += sum(counts) + 2
    from .apdl_geometry import _counts
    _counts(nx, ny, o['layers'], o['mesh_type'])
    active = {'top': o['corrosion_mode'] != 'single_bottom',
              'bottom': o['corrosion_mode'] != 'single_top'}
    calibrated, faces = {}, {}
    for name, depth in (('top', top), ('bottom', bottom)):
        measured = o[f'platform_{name}_mean_depth_mm']
        if active[name] and empirical:
            from .reference_chain import validate_reference
            validate_reference(depth,reference_calibrations.get(name),o)
            measured=None
        if active[name] and measured is None and not empirical:
            raise ValueError(f'请填写{name}面的实测平均腐蚀深度（mm）；不会自动猜测试验值。')
        outward_min = -float(depth.max())
        sample_mean = float(depth.mean())
        outward_mean = -sample_mean
        reference = 0. if empirical else outward_mean + (measured if active[name] else 0.)
        # Translate source samples only; adding platforms must not dilute the measured mean.
        calibrated[name] = depth + reference if active[name] else np.zeros_like(depth)
        faces[name] = dict(active=active[name], measured_mean_depth_mm=measured if active[name] else None,
                           input_sample_mean_depth_mm=sample_mean,
                           normalized_outward_min_height_mm=outward_min,
                           normalized_outward_mean_height_mm=outward_mean,
                           normalized_platform_reference_height_mm=reference if active[name] else 0.,
                           depth_shift_mm=reference if active[name] else 0.,
                           calibrated_min_depth_mm=float(calibrated[name].min()),
                           calibrated_max_depth_mm=float(calibrated[name].max()),
                           calibrated_sample_mean_depth_mm=float(calibrated[name].mean()),
                           mean_calibration_error_mm=float(calibrated[name].mean()-measured) if active[name] and not empirical else None,
                           protrudes_above_platform=bool(np.any(calibrated[name] < 0)))
    source_span = (top.shape[axis] - 1) * spacing
    source_start = fixed + spacing
    source_end = source_start + source_span
    coordinates = np.concatenate((np.linspace(0, fixed, counts[0] + 1),
                                  source_start + np.arange(top.shape[axis]) * spacing,
                                  np.linspace(source_end + spacing, source_end + spacing + loaded, counts[1] + 1)))
    padding = [(0, 0), (0, 0)]
    padding[axis] = (counts[0] + 1, counts[1] + 1)
    top_new = np.pad(calibrated['top'], padding, constant_values=0)
    bottom_new = np.pad(calibrated['bottom'], padding, constant_values=0)
    x = o['origin_x_mm'] + (coordinates if axis == 1 else np.arange(top.shape[1]) * o['dx_mm'])
    y = o['origin_y_mm'] + (coordinates if axis == 0 else np.arange(top.shape[0]) * o['dy_mm'])
    origin = o['origin_x_mm'] if axis == 1 else o['origin_y_mm']
    report = dict(enabled=True, tensile_direction=direction,
                  fixed_flat_length_mm=fixed, loaded_flat_length_mm=loaded,
                  transition_length_each_mm=spacing,
                  fixed_platform_intervals=counts[0], loaded_platform_intervals=counts[1],
                  fixed_platform_spacing_mm=fixed / counts[0], loaded_platform_spacing_mm=loaded / counts[1],
                  source_shape=list(top.shape), source_axial_span_mm=source_span,
                  source_start_index=counts[0]+1, source_stop_index=counts[0]+1+top.shape[axis],
                  source_axial_range_mm=[origin+source_start, origin+source_end],
                  fixed_flat_range_mm=[origin, origin+fixed],
                  loaded_flat_range_mm=[origin+source_end+spacing, origin+coordinates[-1]],
                  platform_bottom_z_mm=0., platform_top_z_mm=o['thickness_mm'],
                  platform_separation_mm=o['thickness_mm'], faces=faces,
                  calibration_method='sample_mean_translation',
                  formula='h=-input_depth; platform_reference=mean(h)+measured_mean_depth; calibrated_depth=input_depth-mean(input_depth)+measured_mean_depth',
                  note='按腐蚀区采样点算术平均值校准，不计新增平台和连接段；校准后采样平均深度在浮点精度内等于实测输入值。正反面分别平移至平台底面0、顶面t0；保留原始起伏与全部采样，不裁剪凸起。两侧各增加一格连接段，不计入平平台长度。')
    if empirical:
        report.update(calibration_method='empirical_reference_preserved',reference_calibrations=reference_calibrations,
            physical_pristine_reference_verified=False,formula='d=H_common-H_flat; preserve source depth without mean translation',
            note='轻微腐蚀区20%经验参考；不做均值二次平移。平台间距取输入原始板厚；未知参考区损失未补偿，反面平整是单面模型假设。')
    return dict(top=top_new, bottom=bottom_new, x=x, y=y, report=report)

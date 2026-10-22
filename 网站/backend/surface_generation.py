"""Independent surface export; no pit analysis, reference scan or CA execution."""
import csv
import math
import shutil
import zipfile
from pathlib import Path

import numpy as np
from scipy.io import savemat
from scipy.interpolate import RegularGridInterpolator

from .morphology_service import _read_surface_matrix
from .runner import _atomic_json
from .system_info import sha256


def number(options, key, default=None, *, positive=False):
    value = options.get(key, default)
    if isinstance(value, bool):
        raise ValueError(f'{key} 必须为有限数值')
    try:
        value = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{key} 必须为有限数值') from exc
    if not math.isfinite(value) or (positive and value <= 0):
        raise ValueError(f'{key} 必须为{"正的" if positive else ""}有限数值')
    return value


def orient_matrix(matrix, options):
    if options.get('unit', 'mm') not in {'mm', 'um'}:
        raise ValueError('输入单位只能为 mm / um')
    if options.get('value_mode', 'height') not in {'height', 'depth'}:
        raise ValueError('请选择高程或腐蚀深度')
    sign = number(options, 'height_sign', 1)
    if sign not in {-1, 1}:
        raise ValueError('Z 符号只能为 1 或 -1')
    matrix = np.asarray(matrix, dtype=np.float64)
    if options.get('transpose', False):
        matrix = matrix.T
    if options.get('flip_x', False):
        matrix = matrix[:, ::-1]
    if options.get('flip_y', False):
        matrix = matrix[::-1, :]
    return matrix * (sign / 1000 if options.get('unit') == 'um' else sign)


def crop_surface(matrix, x, y, options):
    mode = options.get('grid_mode', 'preserve')
    axis = options.get('length_axis', 'X')
    if mode not in {'preserve', 'exact'} or axis not in {'X', 'Y'}:
        raise ValueError('网格模式或长度方向无效')
    length = options.get('length_mm')
    width = options.get('width_mm')
    length = None if length in (None, '') else number(options, 'length_mm', positive=True)
    width = None if width in (None, '') else number(options, 'width_mm', positive=True)
    requested = [length, width] if axis == 'X' else [width, length]
    selections, bounds = [], []
    for values, target, key in zip((x, y), requested, ('offset_x_mm', 'offset_y_mm')):
        span = float(values[-1] - values[0])
        target = span if target is None else target
        tolerance = max(1e-9, span*1e-10)
        if target > span + tolerance:
            raise ValueError(f'{key[7]} 方向来源仅有 {span:.9g} mm，不能生成 {target:.9g} mm；可选择完整来源尺寸')
        offset = options.get(key)
        offset = (span-target)/2 if offset in (None, '') else number(options, key)
        if offset < -tolerance or offset+target > span+tolerance:
            raise ValueError(f'{key} 裁剪范围超出来源，偏移应在 0 至 {max(0, span-target):.9g} mm')
        lo, hi = float(values[0]+max(0, offset)), float(min(values[-1], values[0]+offset+target))
        bounds.append([lo, hi])
        indices = np.flatnonzero((values >= lo-tolerance) & (values <= hi+tolerance))
        if mode == 'preserve' and indices.size < 2:
            raise ValueError('保留网格模式裁剪后每个方向至少需要2个节点，请增大尺寸或改用精确尺寸模式')
        selections.append(indices)
    if mode == 'preserve':
        cols, rows = selections
        out = matrix[np.ix_(rows, cols)]
        xx, yy = x[cols], y[rows]
    else:
        dx = number(options, 'target_dx_mm', float(x[1]-x[0]), positive=True)
        dy = number(options, 'target_dy_mm', float(y[1]-y[0]), positive=True)
        counts = [max(1, math.ceil((hi-lo)/step-1e-10))+1 for (lo, hi), step in zip(bounds, (dx, dy))]
        if math.prod(counts) > 2_000_000:
            raise ValueError('目标网格超过200万点，请增大间距或缩小范围')
        xx, yy = [np.linspace(lo, hi, count) for (lo, hi), count in zip(bounds, counts)]
        gx, gy = np.meshgrid(xx, yy)
        out = RegularGridInterpolator((y, x), matrix, bounds_error=True)(np.column_stack((gy.ravel(), gx.ravel()))).reshape(len(yy), len(xx))
    return out, xx, yy, dict(grid_mode=mode, resampled=mode == 'exact', length_axis=axis,
        requested_length_mm=length, requested_width_mm=width, requested_bounds_xy_mm=bounds,
        actual_length_mm=float((xx if axis == 'X' else yy)[-1]-(xx if axis == 'X' else yy)[0]),
        actual_width_mm=float((yy if axis == 'X' else xx)[-1]-(yy if axis == 'X' else xx)[0]))


def process_face(path, face):
    variable, raw = _read_surface_matrix(path, face.get('variable'))
    o = face['options']
    matrix = orient_matrix(raw, o)
    dx, dy = number(o, 'dx_mm', .3, positive=True), number(o, 'dy_mm', .3, positive=True)
    x = number(o, 'origin_x_mm', 0) + np.arange(matrix.shape[1])*dx
    y = number(o, 'origin_y_mm', 0) + np.arange(matrix.shape[0])*dy
    matrix, x, y, crop = crop_surface(matrix, x, y, o)
    return matrix, x, y, dict(crop, source_variable=variable, value_mode=o.get('value_mode', 'height'),
        input_unit=o.get('unit', 'mm'), input_shape=list(raw.shape), input_dx_mm=dx, input_dy_mm=dy,
        orientation={key: o.get(key, default) for key, default in [('transpose', False), ('flip_x', False), ('flip_y', False), ('height_sign', 1)]})


def prepare_generation(service, payload):
    faces = payload.get('faces')
    if not isinstance(faces, list) or not 1 <= len(faces) <= 2:
        raise ValueError('请选择一个或两个独立表面')
    sources, selected = [], []
    for face in faces:
        side = face.get('side')
        if side not in {'front', 'back'} or side in [s['side'] for s in selected]:
            raise ValueError('正面/反面不能重复')
        record, path = service.get_upload(face.get('upload_id'))
        options = dict(face.get('options') or {})
        frozen = f'inputs/{side}{path.suffix.lower()}'
        item = dict(side=side, source_name=record['name'], source_sha256=record['sha256'],
            variable=face.get('variable'), options=options, frozen_path=frozen)
        matrix, x, y, metadata = process_face(path, item)
        item['preview'] = dict(metadata, matrix_shape=list(matrix.shape), point_count=int(matrix.size),
            size_x_mm=float(x[-1]-x[0]), size_y_mm=float(y[-1]-y[0]),
            dx_mm=float(x[1]-x[0]), dy_mm=float(y[1]-y[0]), z_range_mm=[float(matrix.min()), float(matrix.max())])
        selected.append(item)
        sources.append((path, frozen))
    return dict(kind='surface_generation', case_name=payload.get('case_name') or '独立点云与 MAT', faces=selected), sources


def freeze_generation(spec, sources, job_dir):
    for (path, relative), face in zip(sources, spec['faces']):
        shutil.copy2(path, job_dir / relative)
        if sha256(job_dir / relative) != face['source_sha256']:
            raise ValueError('表面来源冻结失败')


def write_face(output, matrix, x, y, metadata):
    output.mkdir(parents=True, exist_ok=True)
    variable = 'Z_filled' if metadata['side'] == 'front' else 'F_filled'
    savemat(output / f'{variable}.mat', {variable: np.asarray(matrix, dtype=np.float64)}, do_compression=True)
    with (output / 'surface_points.csv').open('w', encoding='utf-8-sig', newline='') as c, \
            (output / 'surface_points.xyz').open('w', encoding='utf-8') as xyz:
        writer = csv.writer(c); writer.writerow(['x_mm', 'y_mm', 'z_mm'])
        for row, yy in enumerate(y):
            for col, xx in enumerate(x):
                values = [format(float(v), '.17g') for v in (xx, yy, matrix[row, col])]
                writer.writerow(values); xyz.write(' '.join(values) + '\n')
    info = dict(metadata, output_variable=variable, matrix_shape=list(matrix.shape),
        point_count=int(matrix.size), unit='mm', layout='rows_y_columns_x',
        dx_mm=float(x[1]-x[0]), dy_mm=float(y[1]-y[0]),
        origin_x_mm=float(x[0]), origin_y_mm=float(y[0]),
        size_x_mm=float(x[-1]-x[0]), size_y_mm=float(y[-1]-y[0]))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    figure = plt.figure(figsize=(11, 4.5))
    ax = figure.add_subplot(121, projection='3d')
    # Preview decimation affects only this image, never saved matrix/point clouds.
    stride = max(1, math.ceil(max(matrix.shape)/220))
    gx, gy = np.meshgrid(x[::stride], y[::stride])
    ax.plot_surface(gx, gy, matrix[::stride, ::stride], cmap='viridis', linewidth=0)
    ax.set(xlabel='X / mm', ylabel='Y / mm', zlabel='Z / mm', title=metadata['side'])
    ax2 = figure.add_subplot(122)
    plot = ax2.imshow(matrix, origin='lower', extent=[x[0], x[-1], y[0], y[-1]], aspect='auto', cmap='viridis')
    ax2.set(xlabel='X / mm', ylabel='Y / mm', title=variable)
    figure.colorbar(plot, ax=ax2, label='Z / mm'); figure.tight_layout()
    figure.savefig(output / 'surface_preview.png', dpi=150); plt.close(figure)
    _atomic_json(output / 'manifest.json', info)
    return info


def run_generation(spec, job_dir, progress=None):
    reports = []
    output = job_dir / 'outputs'; output.mkdir(exist_ok=True)
    for face in spec['faces']:
        path = job_dir / face['frozen_path']
        if sha256(path) != face['source_sha256']:
            raise ValueError('冻结来源文件已改变')
        if progress: progress(dict(phase='compute', label=face['side']))
        matrix, x, y, metadata = process_face(path, face)
        reports.append(write_face(output / face['side'], matrix, x, y,
            dict(metadata, side=face['side'], source_name=face['source_name'], source_sha256=face['source_sha256'])))
    summary = dict(faces=reports, actual_backend='NumPy / SciPy', note='各面独立输出，未自动配准或拼接。')
    _atomic_json(output / 'summary.json', summary)
    _atomic_json(output / 'manifest.json', dict(summary, options=spec['faces']))
    with zipfile.ZipFile(output / 'surface_bundle.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(output.rglob('*')):
            if path.is_file() and path.name != 'surface_bundle.zip':
                archive.write(path, path.relative_to(output).as_posix())
    return summary

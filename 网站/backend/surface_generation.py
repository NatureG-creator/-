"""Independent surface export; no pit analysis, reference scan or CA execution."""
import csv
import math
import shutil
import zipfile
from pathlib import Path

import numpy as np
from scipy.io import savemat, whosmat
from scipy.io.matlab import MatReadError
from scipy.interpolate import RegularGridInterpolator
from scipy.interpolate import griddata
from scipy.ndimage import gaussian_filter, uniform_filter

from .morphology_service import _read_surface_matrix
from .runner import _atomic_json
from .system_info import sha256
from .apdl_npz import inspect_npz, read_npz_state, resolve_geometry
from .finite_element_export import surface_from_ca_state
from .pointcloud_runner import inspect_xyz, POINT_EXTENSIONS


def inspect_surface_mat(path):
    try:
        variables = whosmat(path)
    except (NotImplementedError, ValueError, OSError, MatReadError) as exc:
        raise ValueError('无法读取MAT：文件损坏或版本不支持。本入口仅支持传统MAT（至v7.2）；v7.3/HDF5请在MATLAB中用 save(..., "-v7") 另存后上传') from exc
    return dict(variables=[dict(name=name, shape=list(shape)) for name, shape, kind in variables
        if len(shape) == 2 and kind in {'double', 'single', 'uint8', 'uint16', 'uint32', 'uint64', 'int8', 'int16', 'int32', 'int64'}])


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


def smooth_surface(matrix, options):
    """Apply the same Gaussian-then-moving-average order as baseline export."""
    enabled = bool(options.get('smooth_enabled', False))
    window = options.get('smooth_window_size', 1)
    sigma = options.get('smooth_gaussian_sigma', 0)
    if window in (None, ''):
        window = 1
    if sigma in (None, ''):
        sigma = 0
    if isinstance(window, bool):
        raise ValueError('平滑窗口必须为1至101的奇数')
    try:
        numeric_window = float(window)
        window = int(numeric_window)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError('平滑窗口必须为1至101的奇数') from exc
    if window != numeric_window or window < 1 or window > 101 or window % 2 != 1:
        raise ValueError('平滑窗口必须为1至101的奇数')
    sigma = number({'smooth_gaussian_sigma': sigma}, 'smooth_gaussian_sigma')
    if sigma < 0 or sigma > 100:
        raise ValueError('高斯 sigma 必须为0至100')
    result = np.asarray(matrix, dtype=np.float64)
    if enabled and sigma > 0:
        result = gaussian_filter(result, sigma=sigma, radius=math.ceil(2*sigma), mode='nearest')
    if enabled and window > 1:
        result = uniform_filter(result, size=window, mode='reflect')
    return result, dict(smooth_enabled=enabled, smooth_window_size=window,
        smooth_gaussian_sigma=sigma, smoothing_order='Gaussian → 对称均值窗口' if enabled else '未启用')


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


def load_xyz(path, options):
    inspect_xyz(path)
    points = []
    with path.open(encoding='utf-8-sig') as stream:
        for line in stream:
            if not line.strip():
                continue
            cells = next(csv.reader([line])) if ',' in line else line.split()
            try:
                points.append([float(v) for v in cells[:3]])
            except ValueError:
                continue  # inspect_xyz already permits only one textual header.
    points = np.asarray(points)
    factor = .001 if options.get('unit') == 'um' else 1
    xy = points[:, :2]*factor
    unique, inverse, counts = np.unique(xy, axis=0, return_inverse=True, return_counts=True)
    values = np.bincount(inverse, weights=points[:, 2])/counts
    dx, dy = number(options, 'dx_mm', .3, positive=True), number(options, 'dy_mm', .3, positive=True)
    lo, hi = unique.min(axis=0), unique.max(axis=0)
    dims = np.floor((hi-lo)/[dx, dy]+1e-9).astype(int)+1
    if min(dims) < 2 or math.prod(dims) > 2_000_000:
        raise ValueError('XYZ网格每轴至少2点、总数不超过200万，请检查尺寸与间距')
    x, y = lo[0]+np.arange(dims[0])*dx, lo[1]+np.arange(dims[1])*dy
    gx, gy = np.meshgrid(x, y)
    try:
        matrix = griddata(unique, values, (gx, gy), method='linear')
    except Exception as exc:
        raise ValueError('XYZ无法形成二维表面，请检查XY是否共线、方向或重复采样') from exc
    missing = ~np.isfinite(matrix); missing_count = int(missing.sum())
    if missing_count:
        if not options.get('fill_missing', False):
            raise ValueError(f'XYZ有{missing_count}个未覆盖网格点；裁剪来源或明确启用最近邻填补后重试')
        matrix[missing] = griddata(unique, values, (gx[missing], gy[missing]), method='nearest')
    return matrix, x, y, dict(input_point_count=len(points), duplicate_xy_count=len(points)-len(unique),
        source_resampled=True, missing_filled_count=missing_count, interpolation='linear', missing_fill='nearest' if missing_count else 'none',
        point_cloud_note='由散乱XYZ线性网格化；最近邻填补数量单列报告，非原始散乱点序列。')


def process_face(path, face, *, apply_smoothing=True):
    o = face['options']
    extra = {}
    if path.suffix.lower() == '.mat':
        inspect_surface_mat(path)
        variable, raw = _read_surface_matrix(path, face.get('variable'))
        dx, dy = number(o, 'dx_mm', .3, positive=True), number(o, 'dy_mm', .3, positive=True)
        ox, oy = number(o, 'origin_x_mm', 0), number(o, 'origin_y_mm', 0)
        matrix = orient_matrix(raw, o)
        if o.get('transpose', False):
            dx, dy = dy, dx
            ox, oy = oy, ox
        x = ox + np.arange(matrix.shape[1])*dx
        y = oy + np.arange(matrix.shape[0])*dy
    elif path.suffix.lower() == '.npz':
        info = inspect_npz(path)
        supplied = face.get('source_geometry') or {}
        if not supplied:
            for key, option in [('space_xy_um', 'cell_xy_um'), ('space_z_um', 'cell_z_um')]:
                if o.get(option) not in (None, ''):
                    supplied[key] = number(o, option, positive=True)
        geometry = resolve_geometry(info, supplied)
        state, extra = read_npz_state(path, face.get('variable'), face.get('stage'))
        raw = surface_from_ca_state(state, geometry['space_z_um']).T
        variable = extra['npz_variable']
        matrix = orient_matrix(raw, dict(o, unit='mm', value_mode='depth'))
        dx = dy = geometry['space_xy_um']/1000
        x, y = np.arange(matrix.shape[1])*dx, np.arange(matrix.shape[0])*dy
        extra.update(cell_geometry=geometry, value_mode='depth', input_unit='mm',
            npz_selection='最终阶段快照（perfect_a内部仅1帧）' if variable == 'perfect_a' else f'历史数组第{extra["npz_stage"]}阶段',
            npz_rule=info['rule'], point_cloud_note='由CA状态提取的模拟表面，不是实测扫描。')
    else:
        variable = 'XYZ'
        raw, x, y, extra = load_xyz(path, o)
        matrix = orient_matrix(raw, o)
        if o.get('transpose', False):
            x, y = y, x
        dx, dy = float(x[1]-x[0]), float(y[1]-y[0])
    source_size = [float(x[-1]-x[0]), float(y[-1]-y[0])]
    matrix, x, y, crop = crop_surface(matrix, x, y, o)
    smoothing = dict(smooth_enabled=False, smooth_window_size=1,
        smooth_gaussian_sigma=0, smoothing_order='未启用')
    if apply_smoothing:
        matrix, smoothing = smooth_surface(matrix, o)
    metadata = dict(crop, source_variable=variable, value_mode=o.get('value_mode', 'height'),
        input_unit=o.get('unit', 'mm'), input_shape=list(raw.shape),
        input_dx_mm=dy if o.get('transpose', False) else dx, input_dy_mm=dx if o.get('transpose', False) else dy,
        source_size_xy_mm=source_size,
        orientation={key: o.get(key, default) for key, default in [('transpose', False), ('flip_x', False), ('flip_y', False), ('height_sign', 1)]})
    metadata.update(extra)
    metadata['resampled'] = crop['resampled'] or extra.get('source_resampled', False)
    metadata.update(smoothing)
    return matrix, x, y, metadata


def prepare_generation(service, payload):
    faces = payload.get('faces')
    if not isinstance(faces, list) or not 1 <= len(faces) <= 2:
        raise ValueError('请选择一个或两个独立表面')
    sources, selected = [], []
    for face in faces:
        if not isinstance(face, dict):
            raise ValueError('每面设置必须为对象')
        side = face.get('side')
        if side not in {'front', 'back'} or side in [s['side'] for s in selected]:
            raise ValueError('正面/反面不能重复')
        if bool(face.get('upload_id')) == bool(face.get('source_job_id')):
            raise ValueError('每面请选择一个上传文件或一个已完成模拟')
        source_geometry = {}
        variable = face.get('variable')
        if face.get('upload_id'):
            record, path = service.get_upload(face['upload_id'])
        else:
            job_id = service.validate_id(face['source_job_id'])
            source_job = service.get_job(job_id)
            if source_job['kind'] != 'simulation' or source_job['state'] != 'completed':
                raise ValueError('任务来源必须为已完成模拟')
            import json
            folder = service.runtime / 'jobs' / job_id
            source_spec = json.loads((folder / 'spec.json').read_text(encoding='utf-8'))
            source_geometry = {key: source_spec['config']['GEOMETRY_CONFIG'][key] for key in ('space_xy_um', 'space_z_um')}
            path = folder / 'outputs/simulation.npz'
            # perfect_a is final-only; chronological selections must use a_sd.
            variable = 'a_sd' if face.get('stage') is not None else 'perfect_a'
            if variable == 'a_sd' and not any(v['name'] == 'a_sd' and v['supported'] for v in inspect_npz(path)['variables']):
                raise ValueError('该模拟只有最终快照，没有可读取的阶段历史；请将阶段留空')
            record = dict(name=f'{job_id}/simulation.npz', sha256=sha256(path))
        if path.suffix.lower() not in {'.mat', '.npz'} | POINT_EXTENSIONS:
            raise ValueError('仅接受 MAT、NPZ、TXT/CSV/TSV/XYZ 表面来源')
        if sha256(path) != record['sha256']:
            raise ValueError('来源文件已改变，请重新选择')
        options = dict(face.get('options') or {})
        frozen = f'inputs/{side}{path.suffix.lower()}'
        item = dict(side=side, source_name=record['name'], source_sha256=record['sha256'],
            variable=variable, stage=face.get('stage'), source_geometry=source_geometry,
            source_job_id=face.get('source_job_id'), options=options, frozen_path=frozen)
        matrix, x, y, metadata = process_face(path, item, apply_smoothing=False)
        if options.get('smooth_enabled'):
            _, smoothing = smooth_surface(matrix, options)
            item['smoothing_preview'] = smoothing
        item['preview'] = dict(metadata, side=side, source_name=record['name'], matrix_shape=list(matrix.shape), point_count=int(matrix.size),
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


def write_face(output, matrix, x, y, metadata, *, variant='raw'):
    output.mkdir(parents=True, exist_ok=True)
    variable = 'Z_filled' if metadata['side'] == 'front' else 'F_filled'
    suffix = '' if variant == 'raw' else '_smoothed'
    savemat(output / f'{variable}{suffix}.mat', {variable: np.asarray(matrix, dtype=np.float64)}, do_compression=True)
    with (output / f'surface_points{suffix}.csv').open('w', encoding='utf-8-sig', newline='') as c, \
            (output / f'surface_points{suffix}.xyz').open('w', encoding='utf-8') as xyz:
        writer = csv.writer(c); writer.writerow(['x_mm', 'y_mm', 'z_mm'])
        for row, yy in enumerate(y):
            for col, xx in enumerate(x):
                values = [format(float(v), '.17g') for v in (xx, yy, matrix[row, col])]
                writer.writerow(values); xyz.write(' '.join(values) + '\n')
    info = dict(metadata, output_variable=variable, output_variant=variant, matrix_shape=list(matrix.shape),
        point_count=int(matrix.size), unit='mm', layout='rows_y_columns_x',
        dx_mm=float(x[1]-x[0]), dy_mm=float(y[1]-y[0]),
        origin_x_mm=float(x[0]), origin_y_mm=float(y[0]),
        size_x_mm=float(x[-1]-x[0]), size_y_mm=float(y[-1]-y[0]))
    info['z_range_mm'] = [float(matrix.min()), float(matrix.max())]
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
    figure.savefig(output / f'surface_preview{suffix}.png', dpi=150); plt.close(figure)
    _atomic_json(output / f'manifest{suffix}.json', info)
    return info


def run_generation(spec, job_dir, progress=None):
    reports = []
    smoothed_reports = []
    output = job_dir / 'outputs'; output.mkdir(exist_ok=True)
    for face in spec['faces']:
        path = job_dir / face['frozen_path']
        if sha256(path) != face['source_sha256']:
            raise ValueError('冻结来源文件已改变')
        if progress: progress(dict(phase='compute', label=face['side']))
        raw_face = dict(face, options=dict(face['options'], smooth_enabled=False))
        matrix, x, y, metadata = process_face(path, raw_face, apply_smoothing=False)
        base_metadata = dict(metadata, side=face['side'], source_name=face['source_name'], source_sha256=face['source_sha256'])
        reports.append(write_face(output / face['side'], matrix, x, y, base_metadata, variant='raw'))
        if face['options'].get('smooth_enabled'):
            smoothed, smoothing = smooth_surface(matrix, face['options'])
            smoothed_metadata = dict(base_metadata, **smoothing)
            smoothed_reports.append(write_face(output / face['side'], smoothed, x, y, smoothed_metadata, variant='smoothed'))
    summary = dict(faces=reports, smoothed_faces=smoothed_reports, actual_backend='NumPy / SciPy', note='各面独立输出，未自动配准或拼接。')
    _atomic_json(output / 'summary.json', summary)
    _atomic_json(output / 'manifest.json', dict(summary, options=spec['faces']))
    with zipfile.ZipFile(output / 'surface_bundle.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(output.rglob('*')):
            if path.is_file() and path.name != 'surface_bundle.zip':
                archive.write(path, path.relative_to(output).as_posix())
    return summary

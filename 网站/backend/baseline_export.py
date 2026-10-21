"""Export MATLAB-compatible baseline layers without changing CA/GA results."""
import hashlib
import json
import math
import zipfile
from pathlib import Path

import numpy as np
from scipy.io import savemat

from .apdl_npz import inspect_npz, read_npz_state, resolve_geometry
from .system_info import sha256


def inspect_baseline(service, payload):
    if bool(payload.get('upload_id')) == bool(payload.get('source_job_id')):
        raise ValueError('请选择一个 NPZ 文件或一个已完成的模拟任务')
    config = payload.get('source_config') or {}
    if not isinstance(config, dict):
        raise ValueError('原模拟配置必须是 JSON 对象')
    if payload.get('upload_id'):
        record, path = service.get_upload(payload['upload_id'])
        expected, name = record['sha256'], record['name']
        config = config.get('config', config)
        provenance = '配套导入的原模拟配置' if config else '外部 NPZ'
    else:
        job_id = service.validate_id(payload['source_job_id'])
        job = service.get_job(job_id)
        if job.get('kind') != 'simulation' or job.get('state') != 'completed':
            raise ValueError('请选择已完成的 CA–GA 模拟任务')
        if config:
            raise ValueError('已有任务使用冻结配置，不能替换其原模拟配置')
        config = job.get('spec', {}).get('config', {})
        path = service.runtime / 'jobs' / job_id / 'outputs' / 'simulation.npz'
        expected, name = sha256(path), job.get('display_name') or job_id
        provenance = '源模拟任务的冻结配置'
    if not isinstance(config, dict):
        raise ValueError('原模拟配置必须包含 config 对象或配置组')
    if any(not isinstance(config.get(group, {}), dict) for group in ('GEOMETRY_CONFIG', 'POSTPROCESS_CONFIG')):
        raise ValueError('原配置中的几何及后处理参数必须是对象')
    if sha256(path) != expected:
        raise ValueError('源文件已经变化，请重新选择')
    info = inspect_npz(path)
    geometry = {k: config.get('GEOMETRY_CONFIG', {}).get(k)
                for k in ('space_xy_um', 'space_z_um')}
    for key, value in info['geometry'].items():
        if geometry[key] is not None and geometry[key] != value:
            raise ValueError('NPZ 与配套配置中的元胞尺寸不一致')
        geometry[key] = value
    selected = next((v for v in info['variables'] if v['name'] ==
                     (payload.get('npz_variable') or info['default_variable']) and v['supported']), None)
    if selected is None:
        raise ValueError('请选择受支持的 perfect_a / a_sd 状态')
    shape = selected['state_shape']
    if min(shape) < 2:
        raise ValueError('有限元表面要求状态每个维度至少为 2')
    grid = config.get('GEOMETRY_CONFIG', {})
    for axis, key in enumerate(('grid_w', 'grid_l')):
        if key in grid and grid[key] != shape[axis]:
            raise ValueError('状态 XY 尺寸与原模拟配置不匹配')
    layers = grid.get('grid_n', shape[2] - 1)
    if isinstance(layers, bool) or not isinstance(layers, int) or layers < 1 or shape[2] not in (layers, layers + 1):
        raise ValueError('物理 Z 层数与原模拟状态不匹配')
    pp = config.get('POSTPROCESS_CONFIG', {})
    if sha256(path) != expected:
        raise ValueError('读取期间源文件变化，请重新选择')
    return dict(name=name, source_path=str(path), source_hash=expected,
                variables=info['variables'], npz_variable=selected['name'], state_shape=shape,
                stage_count=selected['stage_count'], geometry=geometry, physical_layers=layers,
                layer_provenance='原模拟 grid_n' if 'grid_n' in grid else '按旧 MATLAB 口径，末层视为附加层',
                window_size=pp.get('auto_plot_window_size'), gaussian_sigma=pp.get('gaussian_sigma'),
                configuration_provenance=provenance,
                configuration_sha256=hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest())


def prepare_baseline(service, payload):
    info = inspect_baseline(service, payload)
    supplied = dict(payload.get('options') or {})
    stage = payload.get('npz_stage', info['stage_count'])
    if isinstance(stage, bool) or not isinstance(stage, int) or not 1 <= stage <= info['stage_count']:
        raise ValueError('阶段超出所选 NPZ 状态的范围')
    if supplied.get('matrix_only') is True:
        return dict(kind='finite_element', source_kind='simulation', source_path=info['source_path'],
                    source_hash=info['source_hash'], source_file=info['name'],
                    source_job_id=payload.get('source_job_id'),
                    case_name=payload.get('case_name') or info['name'] + ' · baseline 矩阵转换',
                    options=dict(output_variable='baseline', matrix_only=True,
                                 physical_layers=info['physical_layers'], layer_provenance=info['layer_provenance'],
                                 npz_variable=info['npz_variable'], npz_stage=stage))
    geometry = resolve_geometry({'geometry': {k: v for k, v in info['geometry'].items() if v is not None}},
                                {k: supplied[k] for k in ('space_xy_um', 'space_z_um') if k in supplied})
    window = supplied.get('window_size', info['window_size'])
    sigma = supplied.get('gaussian_sigma', info['gaussian_sigma'])
    if isinstance(window, bool) or not isinstance(window, int) or not 1 <= window <= 101 or window % 2 != 1:
        raise ValueError('平滑窗口必须为 1～101 的奇数，请按原后处理参数填写')
    if isinstance(sigma, bool) or not isinstance(sigma, (int, float)) or not math.isfinite(sigma) or not 0 <= sigma <= 100:
        raise ValueError('高斯 sigma 必须为 0～100 的有限数值，请按原参数填写')
    options = dict(output_variable='baseline', **geometry, grid_spacing_mm=geometry['space_xy_um'] / 1000,
                   origin_x_mm=0, origin_y_mm=0, precision='%.9f', window_size=window,
                   gaussian_sigma=float(sigma), physical_layers=info['physical_layers'],
                   npz_variable=info['npz_variable'], npz_stage=stage,
                   configuration_provenance=info['configuration_provenance'],
                   configuration_sha256=info['configuration_sha256'],
                   layer_provenance=info['layer_provenance'])
    return dict(kind='finite_element', source_kind='simulation', source_path=info['source_path'],
                source_hash=info['source_hash'], source_file=info['name'],
                source_job_id=payload.get('source_job_id'),
                case_name=payload.get('case_name') or info['name'] + ' · baseline 表面转换', options=options)


def baseline_depth(values, metadata):
    """Match MATLAB height=-baseline*dz, then max(height)-height."""
    baseline = np.asarray(values, dtype=float)
    return (baseline - float(metadata['reference_baseline_cells'])) * float(metadata['space_z_um']) / 1000


def create_baseline_bundle(source, output, options):
    from .config import ENGINE_DIR  # ensures the original engine is on sys.path
    from corrosion_model.analysis import moving_avg_3d
    from .finite_element_export import _write_coordinates, _write_surface_csv, _write_preview
    state, selection = read_npz_state(source, options['npz_variable'], options['npz_stage'])
    if options.get('matrix_only'):
        from corrosion_model.ca import first_metal_depth
        baseline = first_metal_depth(state, *state.shape[:2], options['physical_layers'])
        output = Path(output)
        output.mkdir(parents=True, exist_ok=True)
        savemat(output / 'baseline.mat', {'baseline': baseline}, do_compression=True)
        return dict(output_variable='baseline', matrix_only=True, shape=list(baseline.shape),
                    value_range_cells=[float(baseline.min()), float(baseline.max())],
                    source=dict(kind='simulation', sha256=sha256(source)), options=options,
                    rules='MATLAB 1-based first metal layer at each XY; no smoothing, scaling or transpose.',
                    files=['baseline.mat'])
    baseline, _, _, _ = moving_avg_3d(state, options['window_size'], *state.shape[:2],
                                    options['physical_layers'], gaussian_sigma=options['gaussian_sigma'])
    metadata = dict(schema_version=1, layout='xy', value_unit='cell_layer_index',
                    space_xy_um=options['space_xy_um'], space_z_um=options['space_z_um'],
                    physical_layers=options['physical_layers'], window_size=options['window_size'],
                    gaussian_sigma=options['gaussian_sigma'], expand_factor=1,
                    reference_baseline_cells=float(baseline.min()),
                    depth_rule='(baseline - reference_baseline_cells) * space_z_um / 1000',
                    source_sha256=sha256(source), **selection)
    depth = baseline_depth(baseline, metadata)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    savemat(output / 'baseline.mat', {'baseline': baseline, 'surface_metadata': metadata}, do_compression=True)
    _write_surface_csv(output / 'surface.csv', depth)
    _write_coordinates(output / 'coordinates.csv', depth, spacing=options['grid_spacing_mm'],
                       origin_x=0, origin_y=0, precision=options['precision'])
    _write_preview(output / 'surface_preview.png', depth, 'baseline')
    shape = list(baseline.shape)
    manifest = dict(schema_version=1, output_variable='baseline', shape=shape,
                    value_range_cells=[float(baseline.min()), float(baseline.max())],
                    value_range_mm=[float(depth.min()), float(depth.max())],
                    span_mm=[(shape[0]-1)*options['grid_spacing_mm'], (shape[1]-1)*options['grid_spacing_mm']],
                    source=dict(kind='simulation', sha256=sha256(source)), options=options,
                    surface_metadata=metadata, rules='MATLAB 1-based first metal; Gaussian + symmetric moving average; no resize. '
                    'MAT stores layer indices; CSV/preview store depth in mm relative to the highest surface point.')
    files = [output / n for n in ('baseline.mat', 'surface.csv', 'coordinates.csv', 'surface_preview.png') if (output / n).is_file()]
    manifest['files'] = [dict(name=p.name, bytes=p.stat().st_size, sha256=sha256(p)) for p in files]
    manifest_path = output / 'finite_element_manifest.json'
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    with zipfile.ZipFile(output / 'finite_element_input_bundle.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in [*files, manifest_path]:
            archive.write(path, path.name)
    return dict(manifest, files=[p.name for p in files] + [manifest_path.name, 'finite_element_input_bundle.zip'])

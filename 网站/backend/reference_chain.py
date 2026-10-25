"""Empirical 190/local scan chain; numerical verification is not pristine-face verification."""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import uuid


def completed_sources(runtime):
    from .system_info import json_record
    rows=[]
    for folder in (Path(runtime)/'jobs').iterdir():
        state=json_record(folder/'status.json',{})
        if state.get('state')!='completed' or state.get('kind') not in {'pointcloud','simulation','finite_element'}:
            continue
        task_io=json_record(folder/'task_io.json',{})
        rows.append(dict(id=folder.name,kind=state['kind'],state='completed',
            case_name=state.get('case_name') or folder.name,
            display_name=task_io.get('name') or task_io.get('case_name') or task_io.get('display_name') or state.get('case_name') or folder.name,
            created_at=state.get('created_at',0)))
    return sorted(rows,key=lambda value:value['created_at'],reverse=True)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def array_digest(values):
    return hashlib.sha256(values.tobytes(order='C')).hexdigest()


def validate_reference(depth, report, geometry):
    if not isinstance(report, dict) or report.get('algorithm') != 'empirical_common_frame_v1' or report.get('numerical_chain_verified') is not True or report.get('physical_pristine_reference_verified') is not False:
        raise ValueError('缺少已数值验证且明确标识经验基准的来源报告')
    if list(depth.shape) != report.get('shape') or array_digest(depth) != report.get('depth_sha256'):
        raise ValueError('经验参考来源矩阵已改变；禁止二次归零、裁剪或变换')
    for key in ('dx_mm','dy_mm','origin_x_mm','origin_y_mm'):
        if not math.isclose(geometry[key],report[key],rel_tol=0,abs_tol=1e-10):
            raise ValueError('经验参考来源坐标与映射不一致：'+key)
    if 'thickness_mm' in geometry and not math.isclose(geometry['thickness_mm'],report['original_thickness_mm'],rel_tol=0,abs_tol=1e-10):
        raise ValueError('原始板厚与参考链路核验值不一致')


def shared_surface(full, detail, stored, config, thickness):
    import numpy as np
    from scipy.interpolate import griddata
    from scipy.spatial import cKDTree

    if not math.isfinite(thickness) or thickness <= 0:
        raise ValueError('原始实测板厚必须为正数（mm）')
    for cloud in (full, detail):
        if cloud.ndim != 2 or cloud.shape[1] != 3 or len(cloud) < 4 or not np.isfinite(cloud).all():
            raise ValueError('完整与局部扫描必须是有限XYZ三列')
    distances, indices = cKDTree(full).query(detail, workers=1)
    if not np.array_equal(full[indices], detail):
        raise ValueError('局部扫描不是完整扫描的同坐标XYZ子集；当前入口不猜测配准')
    settings = config['preprocessing']
    if settings['interpolation_method'] != 'linear':
        raise ValueError('经验参考链当前核验线性插值，不替换其他插值方案')
    ratio = float(config['reference']['flat_height_ratio'])
    if ratio != .2:
        raise ValueError('此经验参考模式固定采用min(H)+0.2*(max(H)-min(H))')
    count = int(config['reference']['flat_column_count'])
    if stored.ndim != 2 or not np.isfinite(stored).all() or not 1 <= count <= stored.shape[1]:
        raise ValueError('完整扫描参考矩阵或参考区列数无效')
    points = full.copy()
    if settings['invert_z_on_load']:
        points[:, 2] *= -1
    coefficients = np.linalg.lstsq(np.column_stack((points[:, :2], np.ones(len(points)))), points[:, 2], rcond=None)[0]
    normal = np.array([coefficients[0], coefficients[1], -1.])
    normal /= np.linalg.norm(normal)
    axis = np.cross(normal, [0., 0., 1.])
    angle = np.arccos(np.clip(normal[2], -1, 1))
    axis = axis/np.linalg.norm(axis) if np.linalg.norm(axis) > np.finfo(float).eps else np.array([1., 0., 0.])
    a, b, c = axis
    K = np.array([[0., -c, b], [c, 0., -a], [-b, a, 0.]])
    rotation = np.eye(3) + np.sin(angle)*K + (1-np.cos(angle))*(K@K)
    rotated = points@rotation.T
    _, vectors = np.linalg.eigh(np.cov(rotated[:, :2], rowvar=False))
    center = rotated[:, :2].mean(axis=0)
    step = float(settings['grid_resolution_mm'])
    trim = int(settings['trim_edge_rows'])
    tail = trim + int(settings['trim_legacy_asymmetric']) if trim else 0
    candidates = []
    for sign in (1, -1):
        main = vectors[:, -1]*sign
        angle = -np.arctan2(main[1], main[0])
        xy_rotation = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
        xy = (rotated[:, :2]-center)@xy_rotation.T+center
        x = np.arange(xy[:, 0].min(), xy[:, 0].max()+1e-12, step)
        y = np.arange(xy[:, 1].min(), xy[:, 1].max()+1e-12, step)
        x, y = x[trim:len(x)-tail], y[trim:len(y)-tail]
        X, Y = np.meshgrid(x, y)
        height = griddata(xy, rotated[:, 2], (X, Y), method='linear')
        if height.shape != stored.shape or not np.isfinite(height).all():
            continue
        error = float(np.max(np.abs(height-stored)))
        candidates.append((error, xy, x, y, xy_rotation))
    candidates.sort(key=lambda value: value[0])
    if not candidates or candidates[0][0] > 1e-8:
        raise ValueError('复算坐标变换不能重现已保存完整扫描，禁止自动建立参考面')
    if len(candidates) > 1 and candidates[1][0] <= 1e-8:
        raise ValueError('完整扫描轴向存在二义性，需要额外方向依据')
    error, xy, full_x, full_y, xy_rotation = candidates[0]
    local_xy = xy[indices]
    # Use the full scan's grid phase and transform; never level the detail scan independently.
    x = full_x[(full_x >= local_xy[:, 0].min()+trim*step) & (full_x <= local_xy[:, 0].max()-tail*step)]
    y = full_y[(full_y >= local_xy[:, 1].min()+trim*step) & (full_y <= local_xy[:, 1].max()-tail*step)]
    if min(len(x), len(y)) < 2:
        raise ValueError('局部扫描有效共同网格不足2×2')
    X, Y = np.meshgrid(x, y)
    height = griddata(local_xy, rotated[indices, 2], (X, Y), method='linear')
    if not np.isfinite(height).all():
        raise ValueError('局部共同网格超出实测覆盖；禁止补零或外推')
    reference_roi = stored[:, :count]
    reference = float(reference_roi.min()+ratio*(reference_roi.max()-reference_roi.min()))
    depth = np.ascontiguousarray(height-reference, dtype=np.float64)
    if np.any(depth < 0) or np.any(depth >= thickness):
        raise ValueError('经验深度为负或超过板厚；请核对参考区域与高度方向，禁止取绝对值或裁剪')
    report = dict(schema_version=1, algorithm='empirical_common_frame_v1', numerical_chain_verified=True,
        physical_pristine_reference_verified=False, reference_condition='slightly_corroded',
        reference_formula='H_flat=min(H_roi)+0.2*(max(H_roi)-min(H_roi))',
        depth_formula='d=H_common-H_flat; shared full-scan inward-positive height',
        original_thickness_mm=float(thickness), thickness_source='user_supplied_original_thickness',
        reference_height_mm=reference, reference_ratio=ratio, reference_columns_zero_based=[0, count],
        reference_min_height_mm=float(reference_roi.min()), reference_max_height_mm=float(reference_roi.max()),
        exact_raw_subset=True, raw_matching_max_distance_mm=float(distances.max()),
        full_points=len(full), detail_points=len(detail), full_reproduction_max_error_mm=error,
        invert_raw_z=bool(settings['invert_z_on_load']), rotation_3d=rotation.tolist(),
        rotation_xy=xy_rotation.tolist(), rotation_xy_center=center.tolist(),
        interpolation='linear; shared full-scan grid phase; no extrapolation or additional smoothing',
        shape=list(depth.shape), depth_sha256=array_digest(depth), dx_mm=step, dy_mm=step,
        origin_x_mm=float(x[0]-full_x[0]), origin_y_mm=float(y[0]-full_y[0]),
        mean_depth_mm=float(depth.mean()), min_depth_mm=float(depth.min()), max_depth_mm=float(depth.max()),
        opposite_face='not_measured_in_this_single-face_validation',
        note='轻微腐蚀区的20%经验参考；未证明真实零腐蚀面，未知的参考区损失量未补偿。')
    return depth, report


def build_job_surface(job_dir, thickness, output):
    import numpy as np
    from scipy.io import loadmat, savemat
    job_dir, output = Path(job_dir), Path(output)
    spec = json.loads((job_dir/'spec.json').read_text(encoding='utf-8'))
    paths = {name: job_dir/'inputs'/f'{name}.txt' for name in ('reference', 'detail')}
    for name, path in paths.items():
        if digest(path) != spec['input_hashes'][name]:
            raise ValueError('冻结点云来源已变化，拒绝生成参考面')
    stored_path = job_dir/'outputs/pointcloud/reference_surface_190mm.mat'
    stored = loadmat(stored_path)['height_matrix_mm']
    depth, report = shared_surface(np.loadtxt(paths['reference']), np.loadtxt(paths['detail']), stored,
                                  spec['pointcloud_config'], thickness)
    report.update(source_job_id=job_dir.name, source_hashes={name: digest(path) for name, path in paths.items()},
                  complete_surface_sha256=digest(stored_path))
    output.mkdir(parents=True, exist_ok=True)
    temporary = output/('surface_'+uuid.uuid4().hex+'.tmp')
    with temporary.open('wb') as stream:
        savemat(stream, {'Z_filled': depth, 'reference_calibration_json': json.dumps(report, ensure_ascii=True)}, do_compression=True)
    os.replace(temporary, output/'empirical_surface.mat')
    (output/'reference_calibration.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report


def calibrated_descriptor(service, descriptor, thickness):
    if not isinstance(descriptor, dict) or not descriptor.get('source_job_id') or descriptor.get('upload_id'):
        raise ValueError('自动经验参考请选已完成的点云任务，须同时保留完整与局部扫描')
    job_id = descriptor['source_job_id']
    state = service.get_job(job_id)
    if state['state'] != 'completed' or state['kind'] != 'pointcloud':
        raise ValueError('自动经验参考仅支持已完成的点云处理任务')
    job_dir = service.runtime/'jobs'/job_id
    spec = json.loads((job_dir/'spec.json').read_text(encoding='utf-8'))
    for name in ('reference','detail'):
        if digest(job_dir/'inputs'/f'{name}.txt') != spec['input_hashes'][name]:
            raise ValueError('冻结点云来源已变化，拒绝复用经验参考缓存')
    stored = job_dir/'outputs/pointcloud/reference_surface_190mm.mat'
    key = hashlib.sha256(json.dumps(dict(inputs=spec['input_hashes'], config=spec['pointcloud_config'],
        stored_sha256=digest(stored), thickness=thickness, algorithm=1), sort_keys=True).encode()).hexdigest()[:24]
    output = job_dir/'outputs/pointcloud/reference_chain'/key
    report_path = output/'reference_calibration.json'
    if not report_path.is_file() or not (output/'empirical_surface.mat').is_file():
        # Isolate numerical work from the web service and running scientific workers.
        result = subprocess.run([sys.executable, '-m', 'backend.reference_chain', str(job_dir), str(thickness), str(output)],
            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, encoding='utf-8',
            errors='replace', timeout=90, creationflags=(subprocess.CREATE_NO_WINDOW|subprocess.IDLE_PRIORITY_CLASS) if os.name=='nt' else 0)
        if result.returncode:
            raise ValueError('参考链路验证失败：'+result.stderr[-2000:])
    report = json.loads(report_path.read_text(encoding='utf-8'))
    return dict(source_job_id=job_id, source_kind='measured',
        source_file=(output/'empirical_surface.mat').relative_to(job_dir/'outputs').as_posix(),
        mapping=dict(variable='Z_filled', layout='yx', unit='mm', value_mode='depth',
                     dx_mm=report['dx_mm'], dy_mm=report['dy_mm'],
                     origin_x_mm=report['origin_x_mm'], origin_y_mm=report['origin_y_mm']))


if __name__ == '__main__':
    import psutil
    process=psutil.Process()
    if os.name=='nt':process.nice(psutil.IDLE_PRIORITY_CLASS)
    process.cpu_affinity([min(18,psutil.cpu_count()-1)])
    build_job_surface(sys.argv[1],float(sys.argv[2]),sys.argv[3])

"""Independent surface export; no pit analysis, reference scan or CA execution."""
import csv
import shutil
import zipfile
from pathlib import Path

import numpy as np
from scipy.io import savemat

from .morphology_service import _read_surface_matrix
from .runner import _atomic_json
from .system_info import sha256


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
        variable, matrix = _read_surface_matrix(path, face.get('variable'))
        options = dict(face.get('options') or {})
        dx, dy = float(options.get('dx_mm', .3)), float(options.get('dy_mm', .3))
        if not np.isfinite([dx, dy]).all() or min(dx, dy) <= 0:
            raise ValueError('X/Y 间距必须为正数')
        frozen = f'inputs/{side}{path.suffix.lower()}'
        selected.append(dict(side=side, source_name=record['name'], source_sha256=record['sha256'],
            variable=variable, options=options, frozen_path=frozen))
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
    _atomic_json(output / 'manifest.json', info)
    return info


def run_generation(spec, job_dir, progress=None):
    reports = []
    output = job_dir / 'outputs'; output.mkdir(exist_ok=True)
    for face in spec['faces']:
        path = job_dir / face['frozen_path']
        if sha256(path) != face['source_sha256']:
            raise ValueError('冻结来源文件已改变')
        _, matrix = _read_surface_matrix(path, face.get('variable'))
        o = face['options']; dx, dy = o.get('dx_mm', .3), o.get('dy_mm', .3)
        x, y = np.arange(matrix.shape[1])*dx, np.arange(matrix.shape[0])*dy
        reports.append(write_face(output / face['side'], matrix, x, y,
            dict(side=face['side'], source_name=face['source_name'], source_sha256=face['source_sha256'])))
    summary = dict(faces=reports, actual_backend='NumPy / SciPy', note='各面独立输出，未自动配准或拼接。')
    _atomic_json(output / 'summary.json', summary)
    with zipfile.ZipFile(output / 'surface_bundle.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(output.rglob('*')):
            if path.is_file() and path.name != 'surface_bundle.zip':
                archive.write(path, path.relative_to(output).as_posix())
    return summary

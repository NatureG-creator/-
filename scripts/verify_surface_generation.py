"""Live 8560 acceptance using real C17 data and a labelled analytic fixture."""
import io
import json
import time
import urllib.request
import urllib.parse
import urllib.error
import zipfile
from pathlib import Path

import numpy as np
from scipy.io import loadmat, savemat

BASE = 'http://127.0.0.1:8560'
SAMPLE = Path(r'D:\research\files\段师兄腐蚀工作\05基于腐蚀扫面以及对应元胞生成面的APDL网格生成_包括双面装配组合生成腐蚀数据_能够生成apdl腐蚀试件计算所需点云数据\C\C17_100D\190\z.mat')


def request(path, payload=None, raw=None):
    headers = {'Origin': BASE}
    if payload is not None:
        raw = json.dumps(payload).encode(); headers['Content-Type'] = 'application/json'
    elif raw is not None:
        headers['Content-Type'] = 'application/octet-stream'
    with urllib.request.urlopen(urllib.request.Request(BASE+path, data=raw, headers=headers), timeout=90) as response:
        body = response.read()
        return body if '/download/' in path else json.loads(body)


def upload(name, data):
    return request('/api/uploads?name='+urllib.parse.quote(name), raw=data)['id']


def run_case(name, faces):
    payload = dict(kind='surface_generation', case_name=name, faces=faces)
    preview = request('/api/surface-generation/inspect', payload)
    job = request('/api/jobs', payload)
    deadline = time.monotonic()+180
    while time.monotonic() < deadline:
        state = request('/api/jobs/'+job['id'])
        if state['state'] in {'completed', 'failed', 'stopped', 'interrupted'}:
            break
        time.sleep(.5)
    assert state['state'] == 'completed', state
    bundle = request(f"/api/jobs/{job['id']}/download/surface_bundle.zip")
    with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
        for face in faces:
            side = face['side']; variable = 'Z_filled' if side == 'front' else 'F_filled'
            values = loadmat(io.BytesIO(archive.read(f'{side}/{variable}.mat')))
            assert [key for key in values if not key.startswith('__')] == [variable]
            matrix = values[variable]; assert matrix.dtype == np.float64
            manifest = json.loads(archive.read(f'{side}/manifest.json'))
            assert list(matrix.shape) == manifest['matrix_shape']
            points = np.loadtxt(io.BytesIO(archive.read(f'{side}/surface_points.xyz')))
            np.testing.assert_array_equal(points[:, 2].reshape(matrix.shape), matrix)
            assert len(points) == matrix.size
            assert len(archive.read(f'{side}/surface_preview.png')) > 1000
    return dict(job_id=job['id'], preview=preview['faces'], bundle_bytes=len(bundle))


def main():
    assert SAMPLE.is_file(), SAMPLE
    uid = upload('C17_190_z.mat', SAMPLE.read_bytes())
    real = dict(side='front', upload_id=uid, variable='Z_filled')
    records = []
    for length in (50, 60):
        face = dict(real, options=dict(dx_mm=.3, dy_mm=.3, length_mm=length, offset_x_mm=0))
        result = run_case(f'验收_实测C17_{length}mm_保留网格', [face])
        variable = request(f"/api/jobs/{result['job_id']}/download/front/Z_filled.mat")
        output = loadmat(io.BytesIO(variable))['Z_filled']
        np.testing.assert_array_equal(output, loadmat(SAMPLE)['Z_filled'][:, :output.shape[1]])
        records.append(result)
    records.append(run_case('验收_实测C17_50mm_精确插值', [dict(real, options=dict(dx_mm=.3, dy_mm=.3,
        length_mm=50, grid_mode='exact', offset_x_mm=0))]))
    assert abs(records[-1]['preview'][0]['actual_length_mm']-50) < 1e-10
    try:
        request('/api/surface-generation/inspect', dict(faces=[dict(real, options=dict(length_mm=190))]))
    except urllib.error.HTTPError as error:
        assert error.code == 400
        assert '189.3' in json.loads(error.read())['error']
    else:
        raise AssertionError('Insufficient source was not rejected')
    # Analytic fixture verifies 190 mm; never presented as measured corrosion.
    stream = io.BytesIO(); savemat(stream, {'Z_filled': np.arange(5)[:, None]*.01+np.arange(641)[None, :]*.001})
    fixture = upload('ANALYTIC_TEST_ONLY_192mm.mat', stream.getvalue())
    records.append(run_case('验收_解析测试数据_190mm双面', [dict(side=side, upload_id=fixture,
        options=dict(dx_mm=.3, dy_mm=.3, length_mm=190, grid_mode='exact')) for side in ('front', 'back')]))
    assert all(abs(face['actual_length_mm']-190)<1e-10 for face in records[-1]['preview'])
    xyz = '\n'.join(f'{x} {y} {x+2*y}' for y in range(3) for x in range(3))
    cloud = upload('ANALYTIC_TEST_ONLY_plane.xyz', xyz.encode())
    result = run_case('验收_解析测试数据_XYZ网格化标记', [dict(side='front', upload_id=cloud, options={})])
    assert result['preview'][0]['resampled'] and result['preview'][0]['source_resampled']
    assert result['preview'][0]['grid_mode'] == 'preserve'
    records.append(result)
    stages = np.ones((3, 4, 5, 6))
    for i in range(3):
        stages[i, :, :, :i] = 0
    stream = io.BytesIO(); np.savez(stream, a_sd=stages, perfect_a=stages[-1], space_xy_um=300., space_z_um=50.)
    state_id = upload('ANALYTIC_TEST_ONLY_stages.npz', stream.getvalue())
    result = run_case('验收_解析测试数据_NPZ阶段2', [dict(side='front', upload_id=state_id, variable='a_sd', stage=2, options={})])
    np.testing.assert_allclose(result['preview'][0]['z_range_mm'], [.05, .05])
    assert result['preview'][0]['npz_stage'] == 2
    records.append(result)
    print(json.dumps(dict(state='passed', cases=[dict(job_id=r['job_id'], bundle_bytes=r['bundle_bytes'],
        faces=[{key:f.get(key) for key in ('side','matrix_shape','size_x_mm','size_y_mm','resampled','source_resampled','npz_stage')}
               for f in r['preview']]) for r in records]), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

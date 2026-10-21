import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from scipy.io import loadmat, savemat

from backend.apdl_service import read_face
from backend.baseline_export import create_baseline_bundle, prepare_baseline
from backend.server import make_server
from backend.worker import run_job
from backend.tests import test_finite_element_api as fe_api


class BaselineExportTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        self.service = make_server('127.0.0.1', 0, self.root)
        self.layers = np.array([[1, 2, 3], [2, 3, 4], [3, 4, 5], [4, 5, 6]], dtype=float)
        state = np.zeros((4, 3, 6), dtype=np.uint8)
        for i, j in np.ndindex(self.layers.shape):
            state[i, j, int(self.layers[i, j])-1:] = 1
        data = io.BytesIO()
        np.savez(data, perfect_a=state, a_sd=np.stack([np.ones_like(state), state]))
        raw = data.getvalue()
        self.upload = self.service.upload('simulation.npz', io.BytesIO(raw), len(raw))
        self.config = {'GEOMETRY_CONFIG': dict(grid_w=4, grid_l=3, grid_n=5, space_xy_um=25, space_z_um=25),
                       'POSTPROCESS_CONFIG': dict(auto_plot_window_size=3, gaussian_sigma=0)}
        self.payload = dict(upload_id=self.upload['id'], source_config={'config': self.config},
                            options={'output_variable': 'baseline'})

    def tearDown(self):
        self.service.server_close()
        self.folder.cleanup()

    def test_matlab_one_based_smoothing_mat_roundtrip_and_apdl_match(self):
        spec = prepare_baseline(self.service, self.payload)
        output = self.root / 'converted'
        result = create_baseline_bundle(spec['source_path'], output, spec['options'])
        padded = np.pad(self.layers, 1, mode='symmetric')
        expected = np.array([[padded[i:i+3, j:j+3].mean() for j in range(3)] for i in range(4)])
        saved = loadmat(output / 'baseline.mat')
        np.testing.assert_allclose(saved['baseline'], expected, rtol=0, atol=1e-12)
        self.assertEqual(saved['baseline'].shape, (4, 3))
        depth, meta = read_face(output / 'baseline.mat', 'measured', {})
        np.testing.assert_allclose(depth, ((expected-expected.min())*.025).T, atol=1e-12)
        np.testing.assert_allclose(np.loadtxt(output/'surface.csv', delimiter=',', encoding='utf-8-sig'), depth.T)
        self.assertEqual(meta['dx_mm'], .025)
        self.assertEqual(meta['input_layout'], 'xy')
        np.testing.assert_allclose(result['span_mm'], [.075, .05])
        json.dumps(meta)  # APDL precheck must serialize MAT struct metadata.
        manifest = json.loads((output/'finite_element_manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['options']['physical_layers'], 5)
        self.assertEqual(manifest['options']['npz_stage'], 1)
        with self.assertRaisesRegex(ValueError, '真实XY间距'):
            read_face(output/'baseline.mat', 'measured', {'dx_mm': .25, 'dy_mm': .25})

    def test_missing_configuration_requires_explicit_parameters_and_rejects_scale_change(self):
        payload = dict(upload_id=self.upload['id'], options={'output_variable': 'baseline'})
        with self.assertRaisesRegex(ValueError, '元胞尺寸'):
            prepare_baseline(self.service, payload)
        with self.assertRaisesRegex(ValueError, '不一致'):
            prepare_baseline(self.service, dict(self.payload, options={'space_xy_um': 250}))
        for options in ({'window_size': 2}, {'gaussian_sigma': float('nan')}, {'window_size': 1001}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                prepare_baseline(self.service, dict(self.payload, options=options))

    def test_selected_history_stage_changes_surface_and_is_recorded(self):
        payload = dict(self.payload, npz_variable='a_sd', npz_stage=1)
        spec = prepare_baseline(self.service, payload)
        output = self.root/'stage1'
        create_baseline_bundle(spec['source_path'], output, spec['options'])
        np.testing.assert_allclose(loadmat(output/'baseline.mat')['baseline'], 1)
        self.assertEqual(spec['options']['npz_stage'], 1)
        with self.assertRaisesRegex(ValueError, '阶段'):
            prepare_baseline(self.service, dict(payload, npz_stage=3))

    def test_legacy_baseline_needs_explicit_conversion_metadata(self):
        path = self.root/'100d.mat'
        savemat(path, {'baseline': self.layers})
        with self.assertRaisesRegex(ValueError, '缺少尺寸及参考面'):
            read_face(path, 'measured', {'dx_mm': .25, 'dy_mm': .25})


class BaselineApiTests(unittest.TestCase):
    setUp = fe_api.FiniteElementApiTests.setUp
    tearDown = fe_api.FiniteElementApiTests.tearDown
    request = fe_api.FiniteElementApiTests.request
    fake_simulation = fe_api.FiniteElementApiTests.fake_simulation
    def payload(self):
        stream = io.BytesIO()
        state = np.ones((4, 3, 6), dtype=np.uint8)
        state[0, 0, :3] = 0
        np.savez(stream, perfect_a=state)
        data = stream.getvalue()
        record = self.server.upload('simulation.npz', io.BytesIO(data), len(data))
        return dict(upload_id=record['id'], source_config={'GEOMETRY_CONFIG': {'space_xy_um':25, 'space_z_um':25,
                    'grid_w':4, 'grid_l':3, 'grid_n':5}, 'POSTPROCESS_CONFIG': {'auto_plot_window_size':3,'gaussian_sigma':1}},
                    options={'output_variable':'baseline'})

    def test_export_api_worker_download_and_apdl_precheck(self):
        payload = self.payload()
        code, info = self.request('/api/baseline/inspect', payload)
        self.assertEqual(code, 200, info)
        self.assertEqual(info['geometry']['space_xy_um'], 25)
        self.assertEqual(info['window_size'], 3)
        with patch.object(self.server, 'launch'):
            code, job = self.request('/api/finite-element/exports', payload)
        self.assertEqual(code, 201, job)
        job_id = job['id']
        frozen = self.server.runtime/'jobs'/job_id/'inputs/source.npz'
        self.assertTrue(frozen.is_file())
        run_job(job_id, self.server.runtime)
        code, completed = self.request('/api/jobs/'+job_id)
        self.assertEqual(completed['state'], 'completed', completed.get('error'))
        self.assertTrue(any(f['name']=='baseline.mat' for f in completed['files']))
        precheck = dict(options={'corrosion_mode':'single_top','layers':1}, top_source={
            'source_kind':'measured', 'source_job_id':job_id, 'source_file':'baseline.mat', 'mapping':{'variable':'baseline'}})
        code, result = self.request('/api/apdl/precheck', precheck)
        self.assertEqual(code, 200, result)
        self.assertEqual(result['faces']['top']['baseline_processing']['window_size'], 3)
        self.assertAlmostEqual(result['stats']['length_mm'], .075)
        self.assertAlmostEqual(result['stats']['width_mm'], .05)
        from urllib.request import urlopen
        with urlopen(self.base+'/api/jobs/'+job_id+'/download/baseline.mat') as response:
            self.assertIn('baseline', loadmat(io.BytesIO(response.read())))

    def test_task_source_uses_its_frozen_configuration(self):
        source = self.fake_simulation()
        spec_path = source/'spec.json'
        spec = json.loads(spec_path.read_text(encoding='utf-8'))
        spec['config'] = {'GEOMETRY_CONFIG': {'grid_w':2,'grid_l':3,'grid_n':3,'space_xy_um':250,'space_z_um':25},
                          'POSTPROCESS_CONFIG': {'auto_plot_window_size':3,'gaussian_sigma':1}}
        spec_path.write_text(json.dumps(spec), encoding='utf-8')
        with patch.object(self.server,'launch'):
            code, job = self.request('/api/finite-element/exports',dict(source_job_id='a'*16,options={'output_variable':'baseline'}))
        self.assertEqual(code, 201, job)
        frozen = self.server.get_job(job['id'])['spec']
        self.assertEqual(frozen['options']['grid_spacing_mm'], .25)
        self.assertEqual(frozen['options']['window_size'], 3)


if __name__ == '__main__':
    unittest.main()

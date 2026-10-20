"""外部 NPZ：真实上传、阶段提取、物理尺寸及冻结工作流。"""
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from backend.tests import test_finite_element_api as fe_api
from backend.worker import run_job


def states():
    a = np.zeros((2, 3, 5), dtype=np.uint8)
    a[:, :, 1:] = 1
    b = a.copy()
    b[:, :, 1] = 0
    b[0, 1, 1] = 1
    return a, b


class ExternalNpzTests(unittest.TestCase):
    def test_inspection_accepts_numeric_final_without_unpickling_legacy_stages(self):
        from backend.apdl_npz import inspect_npz, read_npz_state
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'legacy.npz'
            a, b = states()
            np.savez_compressed(path, perfect_a=b, a_sd=np.array([a, b], dtype=object),
                                space_xy_um=40., space_z_um=25.)
            info = inspect_npz(path)
            self.assertEqual(info['default_variable'], 'perfect_a')
            self.assertEqual(info['geometry'], {'space_xy_um': 40., 'space_z_um': 25.})
            self.assertTrue(info['warnings'])
            np.testing.assert_array_equal(read_npz_state(path, 'perfect_a')[0], b)
            with self.assertRaisesRegex(ValueError, '对象|pickle'):
                read_npz_state(path, 'a_sd', 1)

    def test_numeric_stage_selection_and_explicit_missing_dimensions(self):
        from backend.apdl_npz import inspect_npz, read_npz_state, resolve_geometry
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'stages.npz'
            a, b = states()
            np.savez(path, a_sd=np.stack([a, b]))
            info = inspect_npz(path)
            self.assertEqual(info['variables'][0]['stage_count'], 2)
            np.testing.assert_array_equal(read_npz_state(path, 'a_sd', 1)[0], a)
            np.testing.assert_array_equal(read_npz_state(path, 'a_sd')[0], b)
            with self.assertRaisesRegex(ValueError, '阶段'):
                read_npz_state(path, 'a_sd', 3)
            with self.assertRaisesRegex(ValueError, '尺寸'):
                resolve_geometry(info, {})
            self.assertEqual(resolve_geometry(info, {'space_xy_um': 40, 'space_z_um': 25}),
                             {'space_xy_um': 40., 'space_z_um': 25.})
            for value in (0, -1, float('nan'), True, '25'):
                with self.assertRaises(ValueError):
                    resolve_geometry(info, {'space_xy_um': 40, 'space_z_um': value})
            info['geometry']['space_xy_um'] = 40.
            with self.assertRaisesRegex(ValueError, '覆盖|一致'):
                resolve_geometry(info, {'space_xy_um': 99, 'space_z_um': 25})

    def test_invalid_states_are_rejected(self):
        from backend.apdl_npz import read_npz_state
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'invalid.npz'
            for data in (np.zeros((2, 3)), np.full((2, 3, 4), np.nan),
                         np.ones((2, 3, 4), dtype=complex), np.zeros((0, 3, 4))):
                np.savez(path, perfect_a=data)
                with self.assertRaises(ValueError):
                    read_npz_state(path)


class ExternalNpzApiTests(unittest.TestCase):
    setUp = fe_api.FiniteElementApiTests.setUp
    tearDown = fe_api.FiniteElementApiTests.tearDown
    request = fe_api.FiniteElementApiTests.request

    def upload(self, **values):
        buf = io.BytesIO()
        np.savez_compressed(buf, **values)
        buf.seek(0)
        return self.server.upload('external.npz', buf, len(buf.getvalue()))

    def test_external_stages_precheck_and_frozen_worker_match_original_rule(self):
        a, b = states()
        record = self.upload(a_sd=np.stack([a, b]), space_xy_um=40., space_z_um=25.)
        code, info = self.request(f"/api/uploads/{record['id']}/inspect?kind=apdl_npz")
        self.assertEqual(code, 200, info)
        self.assertEqual(info['default_variable'], 'a_sd')
        face = {'source_kind': 'simulation', 'upload_id': record['id'],
                'mapping': {'npz_variable': 'a_sd', 'npz_stage': 1}}
        payload = {'options': {'corrosion_mode': 'single_top'}, 'top_source': face}
        code, preview = self.request('/api/apdl/precheck', payload)
        self.assertEqual(code, 200, preview)
        np.testing.assert_allclose(preview['preview']['top_depth'], np.full((3, 2), .025))
        self.assertAlmostEqual(preview['stats']['length_mm'], .04)
        self.assertAlmostEqual(preview['stats']['width_mm'], .08)
        self.assertEqual(preview['faces']['top']['npz_stage'], 1)
        face['mapping']['npz_stage'] = 2
        with patch.object(self.server, 'launch'):
            code, job = self.request('/api/apdl/jobs', payload)
        self.assertEqual(code, 201, job)
        _, source = self.server.get_upload(record['id'])
        source.unlink()  # worker 必须只读已冻结的输入
        run_job(job['id'], self.server.runtime)
        detail = self.server.get_job(job['id'])
        self.assertEqual(detail['state'], 'completed', detail.get('error'))
        root = self.server.runtime / 'jobs' / job['id']
        with np.load(root / 'outputs' / 'surface_inputs.npz', allow_pickle=False) as out:
            expected = np.full((3, 2), .05)
            expected[1, 0] = .025
            np.testing.assert_allclose(out['top_depth'], expected)
        spec = json.loads((root / 'spec.json').read_text(encoding='utf-8'))
        self.assertEqual(spec['faces']['top']['inherited_geometry']['space_xy_um'], 40.)

    def test_missing_geometry_can_be_supplied_but_file_geometry_cannot_be_overridden(self):
        record = self.upload(perfect_a=states()[0])
        face = {'source_kind': 'simulation', 'upload_id': record['id']}
        payload = {'options': {'corrosion_mode': 'single_bottom'}, 'bottom_source': face}
        code, error = self.request('/api/apdl/precheck', payload)
        self.assertEqual(code, 400)
        self.assertIn('尺寸', error['error'])
        face['cell_geometry'] = {'space_xy_um': 40, 'space_z_um': 25}
        self.assertEqual(self.request('/api/apdl/precheck', payload)[0], 200)
        record = self.upload(perfect_a=states()[0], space_xy_um=40, space_z_um=25)
        face['upload_id'] = record['id']
        face['cell_geometry']['space_xy_um'] = 100
        self.assertEqual(self.request('/api/apdl/precheck', payload)[0], 400)

    def test_changed_upload_is_rejected_by_inspection_and_precheck(self):
        record = self.upload(perfect_a=states()[0], space_xy_um=40, space_z_um=25)
        _, source = self.server.get_upload(record['id'])
        np.savez(source, perfect_a=states()[1], space_xy_um=40, space_z_um=25)
        code, error = self.request(f"/api/uploads/{record['id']}/inspect?kind=apdl_npz")
        self.assertEqual(code, 400)
        payload = {'options': {'corrosion_mode': 'single_top'}, 'top_source': {
            'source_kind': 'simulation', 'upload_id': record['id']}}
        self.assertEqual(self.request('/api/apdl/precheck', payload)[0], 400)

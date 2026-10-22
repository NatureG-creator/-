import io
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from scipy.io import savemat, loadmat

from backend.server import make_server
from backend.worker import run_job
from backend.surface_generation import crop_surface, orient_matrix


class SurfaceGenerationTests(unittest.TestCase):
    def test_preserve_50mm_is_an_exact_subset(self):
        matrix = np.arange(5*641, dtype=float).reshape(5, 641)
        x, y = np.arange(641)*.3, np.arange(5)*.3
        out, xx, yy, meta = crop_surface(matrix, x, y, dict(length_mm=50, offset_x_mm=0))
        np.testing.assert_array_equal(out, matrix[:, :167])
        self.assertAlmostEqual(xx[-1]-xx[0], 49.8)
        self.assertFalse(meta['resampled'])
        np.testing.assert_array_equal(yy, y)

    def test_exact_50mm_interpolation_keeps_linear_field(self):
        x, y = np.arange(641)*.3, np.arange(11)*.3
        raw = y[:, None]*3+x[None, :]*2
        out, xx, yy, meta = crop_surface(raw, x, y, dict(length_mm=50, grid_mode='exact'))
        self.assertAlmostEqual(xx[-1]-xx[0], 50)
        np.testing.assert_allclose(out, yy[:, None]*3+xx[None, :]*2)
        self.assertLessEqual(xx[1]-xx[0], .3)
        self.assertTrue(meta['resampled'])

    def test_y_length_and_offsets(self):
        x, y = np.arange(11)*.3, np.arange(641)*.3
        raw = y[:, None]+x[None, :]
        out, xx, yy, meta = crop_surface(raw, x, y, dict(length_axis='Y', length_mm=60, width_mm=.9, offset_x_mm=.6, offset_y_mm=3))
        self.assertAlmostEqual(meta['actual_length_mm'], 60)
        self.assertEqual(out.shape, (201, 4))
        self.assertAlmostEqual(xx[0], .6)
        self.assertAlmostEqual(yy[0], 3)

    def test_reject_insufficient_source_and_invalid_sizes(self):
        matrix = np.ones((5, 632)); x, y = np.arange(632)*.3, np.arange(5)*.3
        for options in [dict(length_mm=190), dict(length_mm=50, offset_x_mm=170), dict(width_mm=-1), dict(length_mm=float('nan'))]:
            with self.assertRaises(ValueError):
                crop_surface(matrix, x, y, options)

    def test_orient_unit_and_sign_are_explicit(self):
        raw = np.arange(12).reshape(3, 4)
        out = orient_matrix(raw, dict(unit='um', transpose=True, flip_x=True, height_sign=-1))
        np.testing.assert_allclose(out, -raw.T[:, ::-1]/1000, rtol=1e-15, atol=0)

    def test_mat_job_spine(self):
        with tempfile.TemporaryDirectory() as tmp:
            server = make_server(port=0, runtime=Path(tmp))
            try:
                matrix = np.arange(30, dtype=float).reshape(5, 6)/100
                stream = io.BytesIO(); savemat(stream, {'F_filled': matrix}); stream.seek(0)
                record = server.upload('face.mat', stream, len(stream.getbuffer()))
                job = server.create_job(dict(kind='surface_generation', faces=[dict(side='back',
                    upload_id=record['id'], variable='F_filled', options=dict(dx_mm=.3, dy_mm=.3))]), launch=False)
                run_job(job['id'], Path(tmp))
                folder = Path(tmp)/'jobs'/job['id']/'outputs'
                self.assertEqual(server.get_job(job['id'])['state'], 'completed')
                values = loadmat(folder/'back/F_filled.mat')
                self.assertEqual([k for k in values if not k.startswith('__')], ['F_filled'])
                np.testing.assert_array_equal(values['F_filled'], matrix)
                self.assertEqual(values['F_filled'].dtype, np.float64)
                self.assertEqual(len((folder/'back/surface_points.xyz').read_text().splitlines()), 30)
                self.assertTrue((folder/'surface_bundle.zip').is_file())
                self.assertEqual(json.loads((folder/'back/manifest.json').read_text())['matrix_shape'], [5, 6])
            finally:
                server.server_close()

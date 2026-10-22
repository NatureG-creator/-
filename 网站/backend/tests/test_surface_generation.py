import io
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from scipy.io import savemat, loadmat

from backend.server import make_server
from backend.worker import run_job


class SurfaceGenerationTests(unittest.TestCase):
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

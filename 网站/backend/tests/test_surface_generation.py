import io
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from scipy.io import savemat, loadmat

from backend.server import make_server
from backend.worker import run_job
from backend.surface_generation import crop_surface, orient_matrix, process_face, prepare_generation, load_xyz, inspect_surface_mat, smooth_surface


class SurfaceGenerationTests(unittest.TestCase):
    def test_mat_inspection_and_generation_choose_unique_surface(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'face.mat'
            savemat(path, dict(auxiliary=np.ones((3, 4)), Z_filled=np.full((3, 4), 7.)))
            self.assertEqual([v['name'] for v in inspect_surface_mat(path)['variables']], ['auxiliary', 'Z_filled'])
            out, _, _, meta = process_face(path, dict(options={}))
            np.testing.assert_array_equal(out, 7)
            self.assertEqual(meta['source_variable'], 'Z_filled')
            path.write_bytes(b'unsupported MAT')
            with self.assertRaisesRegex(ValueError, '另存'):
                process_face(path, dict(options={}))

    def test_smoothing_is_optional_and_matches_gaussian_then_window(self):
        raw = np.arange(25., dtype=float).reshape(5, 5)
        unchanged, metadata = smooth_surface(raw, {'smooth_enabled': False})
        np.testing.assert_array_equal(unchanged, raw)
        self.assertEqual(metadata['smooth_window_size'], 1)
        empty_values, _ = smooth_surface(raw, {'smooth_enabled': True,
                                                'smooth_window_size': None,
                                                'smooth_gaussian_sigma': None})
        np.testing.assert_array_equal(empty_values, raw)
        smoothed, metadata = smooth_surface(raw, {'smooth_enabled': True,
                                                   'smooth_window_size': 3,
                                                   'smooth_gaussian_sigma': 1})
        from scipy.ndimage import gaussian_filter, uniform_filter
        expected = uniform_filter(gaussian_filter(raw, sigma=1, radius=2, mode='nearest'), size=3, mode='reflect')
        np.testing.assert_allclose(smoothed, expected)
        self.assertEqual(metadata['smoothing_order'], 'Gaussian → 对称均值窗口')
        for value in (3.5, True, 0, 2, 103, float('inf')):
            with self.assertRaises(ValueError):
                smooth_surface(raw, {'smooth_enabled': True, 'smooth_window_size': value})

    def test_transpose_preserves_anisotropic_mat_geometry(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'face.mat'
            raw = np.arange(6.).reshape(2, 3)
            savemat(path, dict(Z_filled=raw))
            out, x, y, meta = process_face(path, dict(options=dict(dx_mm=1, dy_mm=2, origin_x_mm=10, origin_y_mm=20, transpose=True)))
            np.testing.assert_array_equal(out, raw.T)
            self.assertEqual([x[0], y[0], x[-1], y[-1]], [20, 10, 22, 12])
            self.assertEqual([meta['input_dx_mm'], meta['input_dy_mm']], [1, 2])

    def test_npz_axes_geometry_and_stage(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'sim.npz'
            state = np.ones((2, 4, 7, 5)); state[1, 1:3, 2:4, :2] = 0
            np.savez(path, a_sd=state, space_xy_um=300., space_z_um=50.)
            out, x, y, meta = process_face(path, dict(variable='a_sd', stage=2, options={}))
            self.assertEqual(out.shape, (7, 4))
            self.assertAlmostEqual(out[2, 1], .1)
            self.assertAlmostEqual(x[-1], .9)
            self.assertEqual(meta['value_mode'], 'depth')
            with self.assertRaises(ValueError):
                process_face(path, dict(options=dict(cell_xy_um=999)))

    def test_xyz_plane_units_and_duplicate_average(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'plane.xyz'
            x, y = np.meshgrid(np.arange(5)*300, np.arange(4)*300)
            points = np.column_stack((x.ravel(), y.ravel(), (x+2*y).ravel()))
            np.savetxt(path, np.vstack((points, points[0])))
            out, xx, yy, meta = process_face(path, dict(options=dict(unit='um', dx_mm=.3, dy_mm=.3)))
            np.testing.assert_allclose(out, yy[:, None]*2+xx[None, :])
            self.assertEqual(meta['duplicate_xy_count'], 1)
            self.assertEqual(meta['missing_filled_count'], 0)
            self.assertTrue(meta['source_resampled'])
            self.assertTrue(meta['resampled'])
            self.assertEqual(meta['grid_mode'], 'preserve')

    def test_xyz_missing_grid_requires_explicit_fill(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'tri.xyz'
            np.savetxt(path, [[0, 0, 0], [3, 0, 1], [0, 3, 2]])
            with self.assertRaisesRegex(ValueError, '未覆盖'):
                load_xyz(path, dict(dx_mm=1, dy_mm=1))
            matrix, x, y, meta = load_xyz(path, dict(dx_mm=1, dy_mm=1, fill_missing=True))
            self.assertTrue(np.isfinite(matrix).all())
            self.assertGreater(meta['missing_filled_count'], 0)

    def test_dual_faces_freeze_and_export_independently(self):
        with tempfile.TemporaryDirectory() as tmp:
            server = make_server(port=0, runtime=Path(tmp))
            try:
                faces = []
                for side, value in [('front', 2.), ('back', 7.)]:
                    stream = io.BytesIO(); savemat(stream, {'surface': np.full((4, 8), value)}); stream.seek(0)
                    upload = server.upload(side+'.mat', stream, len(stream.getbuffer()))
                    faces.append(dict(side=side, upload_id=upload['id'], options={}))
                spec, _ = prepare_generation(server, dict(faces=faces))
                self.assertEqual(len(spec['faces']), 2)
                with self.assertRaises(ValueError):
                    prepare_generation(server, dict(faces=[faces[0], faces[0]]))
                job = server.create_job(dict(kind='surface_generation', faces=faces), launch=False)
                run_job(job['id'], Path(tmp))
                output = Path(tmp)/'jobs'/job['id']/'outputs'
                self.assertEqual(server.get_job(job['id'])['state'], 'completed')
                np.testing.assert_array_equal(loadmat(output/'front/Z_filled.mat')['Z_filled'], 2)
                np.testing.assert_array_equal(loadmat(output/'back/F_filled.mat')['F_filled'], 7)
                self.assertTrue((output/'front/surface_preview.png').is_file())
                import zipfile
                with zipfile.ZipFile(output/'surface_bundle.zip') as archive:
                    self.assertIn('back/manifest.json', archive.namelist())
            finally:
                server.server_close()

    def test_smoothing_keeps_raw_and_writes_smoothed_mat(self):
        with tempfile.TemporaryDirectory() as tmp:
            server = make_server(port=0, runtime=Path(tmp))
            try:
                matrix = np.arange(30, dtype=float).reshape(5, 6)/100
                stream = io.BytesIO(); savemat(stream, {'Z_filled': matrix}); stream.seek(0)
                record = server.upload('face.mat', stream, len(stream.getbuffer()))
                job = server.create_job(dict(kind='surface_generation', faces=[dict(side='front',
                    upload_id=record['id'], variable='Z_filled', options={
                        'smooth_enabled': True, 'smooth_window_size': 3,
                        'smooth_gaussian_sigma': 1})]), launch=False)
                run_job(job['id'], Path(tmp))
                output = Path(tmp)/'jobs'/job['id']/'outputs'/'front'
                raw = loadmat(output/'Z_filled.mat')['Z_filled']
                smoothed = loadmat(output/'Z_filled_smoothed.mat')['Z_filled']
                np.testing.assert_array_equal(raw, matrix)
                self.assertEqual(raw.dtype, np.float64)
                self.assertEqual(smoothed.shape, raw.shape)
                self.assertEqual(smoothed.dtype, np.float64)
                self.assertEqual([key for key in loadmat(output/'Z_filled_smoothed.mat')
                                  if not key.startswith('__')], ['Z_filled'])
                self.assertFalse(np.array_equal(smoothed, raw))
                expected, _ = smooth_surface(matrix, dict(smooth_enabled=True,
                    smooth_window_size=3, smooth_gaussian_sigma=1))
                np.testing.assert_array_equal(smoothed, expected)
                points = np.loadtxt(output/'surface_points_smoothed.xyz')
                np.testing.assert_array_equal(points[:, 2].reshape(matrix.shape), smoothed)
                csv_points = np.loadtxt(output/'surface_points_smoothed.csv', delimiter=',', skiprows=1, encoding='utf-8-sig')
                np.testing.assert_array_equal(csv_points, points)
                manifest = json.loads((output/'manifest_smoothed.json').read_text(encoding='utf-8'))
                self.assertEqual(manifest['output_variant'], 'smoothed')
                self.assertTrue((output/'surface_points_smoothed.xyz').is_file())
            finally:
                server.server_close()

    def test_completed_simulation_uses_frozen_geometry(self):
        with tempfile.TemporaryDirectory() as tmp:
            server = make_server(port=0, runtime=Path(tmp))
            try:
                folder = Path(tmp)/'jobs'/('a'*16); (folder/'outputs').mkdir(parents=True)
                (folder/'status.json').write_text(json.dumps(dict(id='a'*16, kind='simulation', state='completed')))
                (folder/'spec.json').write_text(json.dumps(dict(kind='simulation', config=dict(GEOMETRY_CONFIG=dict(space_xy_um=100., space_z_um=20.)))))
                np.savez(folder/'outputs/simulation.npz', perfect_a=np.ones((3, 6, 4)))
                spec, _ = prepare_generation(server, dict(faces=[dict(side='front', source_job_id='a'*16, options={})]))
                preview = spec['faces'][0]['preview']
                self.assertEqual(preview['matrix_shape'], [6, 3])
                self.assertAlmostEqual(preview['dx_mm'], .1)
                face = dict(side='front', source_job_id='a'*16, options={}, stage=1)
                with self.assertRaisesRegex(ValueError, '最终快照'):
                    prepare_generation(server, dict(faces=[face]))
                stages = np.ones((3, 3, 6, 4))
                for i in range(3):
                    stages[i, :, :, :i] = 0
                np.savez(folder/'outputs/simulation.npz', perfect_a=stages[-1], a_sd=stages)
                for i in range(3):
                    face['stage'] = i+1
                    spec, _ = prepare_generation(server, dict(faces=[face]))
                    preview = spec['faces'][0]['preview']
                    self.assertEqual(preview['source_variable'], 'a_sd')
                    self.assertEqual(preview['npz_stage'], i+1)
                    np.testing.assert_allclose(preview['z_range_mm'], [i*.02, i*.02])
            finally:
                server.server_close()

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
                self.assertEqual(json.loads((folder/'back/manifest.json').read_text(encoding='utf-8'))['matrix_shape'], [5, 6])
            finally:
                server.server_close()

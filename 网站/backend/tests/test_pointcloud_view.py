import hashlib
import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from scipy.io import savemat

from backend.pointcloud_view import saved_preview


class PointcloudViewTests(unittest.TestCase):
    def common_fixture(self, root):
        job=root/'jobs/aaaaaaaaaaaaaaaa';(job/'inputs').mkdir(parents=True);(job/'outputs/pointcloud').mkdir(parents=True)
        (job/'status.json').write_text('{"state":"completed"}')
        for name in ('reference','detail'):(job/'inputs'/(name+'.txt')).write_text('0 0 0\n1 0 .1\n0 1 .2\n')
        hashes={name:hashlib.sha256((job/'inputs'/(name+'.txt')).read_bytes()).hexdigest() for name in ('reference','detail')}
        config=dict(reference=dict(flat_column_count=200,flat_height_ratio=.2))
        (job/'spec.json').write_text(json.dumps(dict(kind='pointcloud',input_hashes=hashes,pointcloud_config=config)))
        x=np.arange(205)*.3;y=np.arange(2)*.3;h=np.tile(np.arange(205)*.001,(2,1))
        full=job/'outputs/pointcloud/reference_surface_190mm.mat';savemat(full,dict(height_matrix_mm=h,x_coordinates_mm=x,y_coordinates_mm=y))
        full_hash=hashlib.sha256(full.read_bytes()).hexdigest();flat=float(h[:,:200].min()+.2*(h[:,:200].max()-h[:,:200].min()))
        depth=np.ascontiguousarray(h[:,201:203]-flat)
        report=dict(algorithm='empirical_common_frame_v1',numerical_chain_verified=True,physical_pristine_reference_verified=False,
            source_job_id=job.name,source_hashes=hashes,complete_surface_sha256=full_hash,original_thickness_mm=6.,
            shape=list(depth.shape),depth_sha256=hashlib.sha256(depth.tobytes()).hexdigest(),dx_mm=.3,dy_mm=.3,
            origin_x_mm=float(x[201]),origin_y_mm=0.,reference_columns_zero_based=[0,200],reference_ratio=.2,reference_height_mm=flat,
            mean_depth_mm=float(depth.mean()),min_depth_mm=float(depth.min()),max_depth_mm=float(depth.max()),full_reproduction_max_error_mm=0.)
        key=hashlib.sha256(json.dumps(dict(inputs=hashes,config=config,stored_sha256=full_hash,thickness=6.,algorithm=1),sort_keys=True).encode()).hexdigest()[:24]
        cache=job/'outputs/pointcloud/reference_chain'/key;cache.mkdir(parents=True)
        (cache/'reference_calibration.json').write_text(json.dumps(report))
        savemat(cache/'empirical_surface.mat',dict(Z_filled=depth,reference_calibration_json=json.dumps(report)))
        return job,cache,report,depth

    def test_common_view_reuses_cache_preserves_formula_and_does_not_recalculate(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);job,cache,report,depth=self.common_fixture(root)
            before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}
            service=SimpleNamespace(runtime=root,validate_id=lambda x:None)
            with patch('backend.reference_chain.shared_surface',side_effect=AssertionError('must not recompute')) as fit:
                result=saved_preview(service,dict(source_job_id=job.name,view='common_reference'));fit.assert_not_called()
            common=result['common_reference'];self.assertEqual(common['reference_columns_one_based'],[1,200])
            self.assertEqual(common['reference_x_range_mm'],[0.,59.699999999999996])
            self.assertEqual(common['reference_height_mm'],report['reference_height_mm'])
            values=np.asarray(common['local_surface']['points'])
            np.testing.assert_allclose(values[:,2]-report['reference_height_mm'],depth.ravel(),rtol=0,atol=1e-16)
            self.assertTrue(result['inward_positive']);self.assertFalse(common['physical_pristine_reference_verified'])
            self.assertEqual(before,{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()})

    def test_common_view_rejects_changed_depth_and_changed_raw_scan_without_restarting_chain(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);job,cache,report,depth=self.common_fixture(root)
            service=SimpleNamespace(runtime=root,validate_id=lambda x:None)
            savemat(cache/'empirical_surface.mat',dict(Z_filled=depth+.01,reference_calibration_json=json.dumps(report)))
            with self.assertRaisesRegex(ValueError,'矩阵已改变'):
                saved_preview(service,dict(source_job_id=job.name,view='common_reference'))
            (job/'inputs/detail.txt').write_text('changed')
            with self.assertRaisesRegex(ValueError,'原始扫描已变化'):
                saved_preview(service,dict(source_job_id=job.name,view='common_reference'))

    def test_saved_surface_preview_keeps_existing_coordinates_and_heights_without_writes(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);job=root/'jobs/aaaaaaaaaaaaaaaa';(job/'outputs/pointcloud').mkdir(parents=True)
            (job/'status.json').write_text('{"state":"completed"}')
            (job/'spec.json').write_text('{"kind":"pointcloud","reference_extension":".txt"}')
            height=np.array([[.2,.1],[-.1,-.3]])
            path=job/'outputs/pointcloud/measured_surface_smoothed.mat'
            savemat(path,dict(height_matrix_mm=height,x_coordinates_mm=[10,12],y_coordinates_mm=[5,7]))
            digest=hashlib.sha256(path.read_bytes()).hexdigest()
            files={p.relative_to(root) for p in root.rglob('*') if p.is_file()}
            service=SimpleNamespace(runtime=root,validate_id=lambda x:None)
            result=saved_preview(service,dict(source_job_id=job.name,view='detail_processed'))
            self.assertEqual(result['points'],[[10.,5.,.2],[12.,5.,.1],[10.,7.,-.1],[12.,7.,-.3]])
            self.assertFalse(result['physical_pristine_reference_verified'])
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),digest)
            self.assertEqual(files,{p.relative_to(root) for p in root.rglob('*') if p.is_file()})
            (job/'status.json').write_text('{"state":"running"}')
            with self.assertRaisesRegex(ValueError,'已完成'):
                saved_preview(service,dict(source_job_id=job.name))

    def test_raw_scan_stays_scattered_and_cannot_escape_fixed_input_path(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);job=root/'jobs/aaaaaaaaaaaaaaaa';(job/'inputs').mkdir(parents=True)
            (job/'status.json').write_text('{"state":"completed"}')
            spec=job/'spec.json';spec.write_text('{"kind":"pointcloud","reference_extension":".txt"}')
            (job/'inputs/reference.txt').write_text('10 5 -0.3\n12 7 0.2\n11 6 0.1\n')
            service=SimpleNamespace(runtime=root,validate_id=lambda x:None)
            result=saved_preview(service,dict(source_job_id=job.name,view='reference_raw'))
            self.assertFalse(result['grid']);self.assertEqual(result['points'],[[10.,5.,-.3],[12.,7.,.2],[11.,6.,.1]])
            with self.assertRaisesRegex(ValueError,'类型'):
                saved_preview(service,dict(source_job_id=job.name,view='../../spec'))
            spec.write_text(json.dumps(dict(kind='pointcloud',reference_extension='/../../outside.txt')))
            with self.assertRaisesRegex(ValueError,'扩展名'):
                saved_preview(service,dict(source_job_id=job.name,view='reference_raw'))

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from scipy.io import loadmat, savemat

from backend.pointcloud_regions import export_region
from backend.pointcloud_view import _common_preview
from backend.tests.test_pointcloud_view import PointcloudViewTests


class CommonCropTests(unittest.TestCase):
    def fixture(self, folder):
        job, cache, report, depth = PointcloudViewTests().common_fixture(Path(folder))
        spec = json.loads((job/'spec.json').read_text())
        c = _common_preview(job, spec)['common_reference']
        data = loadmat(job/'outputs/pointcloud/reference_surface_190mm.mat')
        x, y = data['x_coordinates_mm'].ravel(), data['y_coordinates_mm'].ravel()
        requested = dict(x=[26.7, 33.3], y=[0., .3])
        ix = np.flatnonzero((x >= requested['x'][0]) & (x <= requested['x'][1]))
        iy = np.flatnonzero((y >= requested['y'][0]) & (y <= requested['y'][1]))
        reference = {key:c[key] for key in ('cache_key','complete_surface_sha256','depth_sha256',
            'reference_height_mm','reference_column_count','reference_ratio','original_thickness_mm',
            'physical_pristine_reference_verified')}
        confirmation = dict(reference=reference,requested_bounds_mm=requested,
            actual_bounds_mm=dict(x=[float(x[ix[0]]),float(x[ix[-1]])],y=[float(y[iy[0]]),float(y[iy[-1]])]),
            shape=[len(iy),len(ix)],point_count=len(ix)*len(iy))
        args = dict(source_kind='common_reference',width_mm=.3,center_x_mm=30.,center_y_mm=.15,confirmation=confirmation)
        return job,args,data['height_matrix_mm'][np.ix_(iy,ix)]

    def test_confirmed_export_preserves_original_nodes_and_fixed_reference_without_recalibration(self):
        with tempfile.TemporaryDirectory() as folder:
            job,args,expected=self.fixture(folder)
            before={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in job.rglob('*') if p.is_file()}
            with patch('backend.reference_chain.shared_surface',side_effect=AssertionError('must not recalculate')):
                result=export_region(job,'X',6.6,**args)
            actual=loadmat(job/'outputs'/result['files'][0])
            np.testing.assert_array_equal(actual['height_matrix_mm'],expected)
            self.assertEqual(actual['corrosion_depth_matrix_mm'].size,0)
            self.assertEqual(json.loads(str(actual['empirical_reference_json'].ravel()[0])),args['confirmation']['reference'])
            metadata=json.loads((job/'outputs'/result['files'][-1]).read_text())
            self.assertEqual(metadata['empirical_reference']['reference_ratio'],.2)
            self.assertEqual(metadata['empirical_reference']['reference_column_count'],200)
            self.assertEqual(before,{p:hashlib.sha256(p.read_bytes()).hexdigest() for p in before})

    def test_missing_confirmation_and_stale_parameter_reject_before_writing(self):
        with tempfile.TemporaryDirectory() as folder:
            job,args,_=self.fixture(folder)
            with self.assertRaisesRegex(ValueError,'先确认'):
                export_region(job,'X',6.6,**{**args,'confirmation':None})
            with self.assertRaisesRegex(ValueError,'确认时不一致'):
                export_region(job,'X',6.,**args)
            self.assertFalse((job/'outputs/pointcloud/regions').exists())

    def test_changed_reference_or_node_confirmation_rejects_before_writing(self):
        with tempfile.TemporaryDirectory() as folder:
            job,args,_=self.fixture(folder)
            confirmation=args['confirmation'];confirmation['reference']['reference_ratio']=.25
            with self.assertRaisesRegex(ValueError,'参考链已变化'):
                export_region(job,'X',6.6,**args)
            confirmation['reference']['reference_ratio']=.2;confirmation['point_count']+=1
            with self.assertRaisesRegex(ValueError,'确认时不一致'):
                export_region(job,'X',6.6,**args)
            self.assertFalse((job/'outputs/pointcloud/regions').exists())

    def test_changed_saved_source_and_running_job_cannot_export(self):
        with tempfile.TemporaryDirectory() as folder:
            job,args,_=self.fixture(folder)
            source=job/'outputs/pointcloud/reference_surface_190mm.mat';data=loadmat(source)
            savemat(source,{k:v for k,v in data.items() if not k.startswith('_')},do_compression=True)
            with self.assertRaisesRegex(ValueError,'已验证共同坐标缓存'):
                export_region(job,'X',6.6,**args)
            (job/'status.json').write_text('{"state":"running"}')
            with self.assertRaisesRegex(ValueError,'已完成'):
                export_region(job,'X',6.6,**args)
            self.assertFalse((job/'outputs/pointcloud/regions').exists())

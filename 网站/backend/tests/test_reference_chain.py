import unittest
import json
import tempfile
from pathlib import Path

import numpy as np

from backend.apdl_geometry import build_geometry
from backend.reference_chain import array_digest, shared_surface, validate_reference, completed_sources


class ReferenceChainTests(unittest.TestCase):
    def test_source_list_uses_only_small_records_and_excludes_running_and_other_jobs(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for name,state,kind in (('a','completed','pointcloud'),('b','running','simulation'),('c','completed','apdl_tension')):
                folder=root/'jobs'/name;folder.mkdir(parents=True)
                (folder/'status.json').write_text(json.dumps(dict(state=state,kind=kind,created_at=1)),encoding='utf-8')
                (folder/'spec.json').write_text('invalid, must not be read',encoding='utf-8')
            self.assertEqual([row['id'] for row in completed_sources(root)],['a'])

    def setUp(self):
        self.depth=np.array([[.1,.2,.3],[.4,.5,.6]])
        self.report=dict(algorithm='empirical_common_frame_v1',numerical_chain_verified=True,
            physical_pristine_reference_verified=False,original_thickness_mm=6.,shape=[2,3],
            depth_sha256=array_digest(self.depth),dx_mm=.3,dy_mm=.3,origin_x_mm=0.,origin_y_mm=0.)
        self.options=dict(corrosion_mode='single_top',platform_enabled=True,
            platform_reference_mode='empirical_190',thickness_mm=6.,dx_mm=.3,dy_mm=.3,layers=3)

    def test_platform_preserves_source_depth_without_a_manual_mean(self):
        geometry=build_geometry(self.depth,None,{**self.options,'platform_top_mean_depth_mm':.8},reference_calibrations={'top':self.report})
        p=geometry['platforms'];a,b=p['source_start_index'],p['source_stop_index']
        np.testing.assert_array_equal(geometry['top_depth'][:,a:b],self.depth)
        np.testing.assert_array_equal(geometry['remaining'][:,a:b],6-self.depth)
        self.assertEqual(p['platform_separation_mm'],6.)
        self.assertEqual(p['calibration_method'],'empirical_reference_preserved')
        self.assertIsNone(p['faces']['top']['measured_mean_depth_mm'])
        self.assertIsNone(geometry['options']['platform_top_mean_depth_mm'])
        self.assertFalse(p['physical_pristine_reference_verified'])

    def test_tampered_matrix_mapping_and_thickness_are_rejected(self):
        for key,value in (('depth_sha256','wrong'),('dx_mm',.1),('origin_x_mm',1.),('original_thickness_mm',5.)):
            with self.subTest(key=key),self.assertRaises(ValueError):
                report={**self.report,key:value}
                build_geometry(self.depth,None,self.options,reference_calibrations={'top':report})
        with self.assertRaisesRegex(ValueError,'来源报告'):
            build_geometry(self.depth,None,self.options)

    def test_empirical_source_never_claims_a_verified_pristine_reference(self):
        report={**self.report,'physical_pristine_reference_verified':True}
        with self.assertRaisesRegex(ValueError,'经验基准'):
            validate_reference(self.depth,report,{**self.options,'origin_x_mm':0.,'origin_y_mm':0.})
        with self.assertRaisesRegex(ValueError,'反面'):
            build_geometry(self.depth,self.depth,{**self.options,'corrosion_mode':'double_independent'})

    def test_unregistered_detail_is_rejected_before_any_frame_or_interpolation(self):
        full=np.array([[0.,0.,0.],[1.,0.,.1],[0.,1.,.2],[1.,1.,.3]])
        detail=full.copy();detail[0,0]+=.01
        with self.assertRaisesRegex(ValueError,'同坐标XYZ子集'):
            shared_surface(full,detail,np.zeros((2,2)),{},6.)

    def test_manual_mean_remains_available_and_is_the_default(self):
        options={**self.options,'platform_reference_mode':'manual_mean','platform_top_mean_depth_mm':.8}
        geometry=build_geometry(self.depth,None,options)
        p=geometry['platforms'];a,b=p['source_start_index'],p['source_stop_index']
        self.assertAlmostEqual(geometry['top_depth'][:,a:b].mean(),.8)
        self.assertEqual(p['calibration_method'],'sample_mean_translation')

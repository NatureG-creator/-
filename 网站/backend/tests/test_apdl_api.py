import io
import json
import unittest
from pathlib import Path
import numpy as np
from scipy.io import savemat
from backend.runner import _atomic_json
from unittest.mock import patch
from backend.tests import test_finite_element_api as fe_api
from backend.worker import run_job


class ApdlApiTests(unittest.TestCase):
    setUp=fe_api.FiniteElementApiTests.setUp
    tearDown=fe_api.FiniteElementApiTests.tearDown
    request=fe_api.FiniteElementApiTests.request
    def test_apdl_flat_precheck_and_real_worker_build(self):
        payload={'options':{'corrosion_mode':'flat'}}
        code,preview=self.request('/api/apdl/precheck',payload)
        self.assertEqual(code,200)
        self.assertEqual(preview['stats']['node_count'],220)
        with patch.object(self.server,'launch'):
            code,job=self.request('/api/apdl/jobs',payload)
        self.assertEqual(code,201)
        run_job(job['id'],self.server.runtime)
        detail=self.server.get_job(job['id'])
        self.assertEqual(detail['state'],'completed',detail.get('error'))
        root=self.server.runtime/'jobs'/job['id']/'outputs'
        result=json.loads((root/'summary.json').read_text(encoding='utf-8'))
        self.assertEqual(result['solve_state'],'not_requested')
        self.assertTrue((root/'main.inp').is_file())
        self.assertFalse((root/'force_displacement.csv').exists())

    def test_double_faces_need_registration_and_match_and_freeze(self):
        buf=io.BytesIO(b'0,0.1,0.2\n0.3,0.4,0.5\n')
        uploaded=self.server.upload('face.csv',buf,len(buf.getvalue()))
        face={'upload_id':uploaded['id'],'mapping':{'dx_mm':.3,'dy_mm':.3}}
        payload={'options':{'corrosion_mode':'double_independent'},'top_source':face,'bottom_source':face}
        code,error=self.request('/api/apdl/precheck',payload)
        self.assertEqual(code,400)
        self.assertIn('配准',error['error'])
        payload['registration_confirmed']=True
        code,preview=self.request('/api/apdl/precheck',payload)
        self.assertEqual(code,200)
        self.assertAlmostEqual(preview['stats']['min_remaining_thickness_mm'],5)
        with patch.object(self.server,'launch'):
            code,job=self.request('/api/apdl/jobs',payload)
        self.assertEqual(code,201)
        self.assertTrue((self.server.runtime/'jobs'/job['id']/'inputs'/'top.csv').is_file())
        payload['bottom_source']={**face,'mapping':{'dx_mm':.4,'dy_mm':.3}}
        code,error=self.request('/api/apdl/precheck',payload)
        self.assertEqual(code,400)
        self.assertIn('不匹配',error['error'])

    def test_capabilities_presets_and_missing_solver(self):
        self.assertEqual(self.request('/api/apdl/presets')[0],200)
        self.assertEqual(self.request('/api/apdl/capabilities')[0],200)
        with patch('backend.apdl_solver.mapdl_capabilities',return_value={'available':False}):
            code,value=self.request('/api/apdl/jobs',{'options':{'corrosion_mode':'flat'},'run_mode':'solve'})
        self.assertEqual(code,400)
        self.assertIn('MAPDL',value['error'])

    def test_legacy_surface_job_inherits_row_x_and_origins(self):
        job_id='e'*16
        root=self.server.runtime/'jobs'/job_id
        (root/'outputs').mkdir(parents=True)
        _atomic_json(root/'status.json',{'id':job_id,'state':'completed','kind':'finite_element'})
        _atomic_json(root/'spec.json',{'kind':'finite_element','options':{
            'grid_spacing_mm':.4,'origin_x_mm':12,'origin_y_mm':34}})
        savemat(root/'outputs'/'face.mat',{'F_filled':np.arange(6).reshape(2,3)/10})
        code,preview=self.request('/api/apdl/precheck',{'options':{'corrosion_mode':'single_top'},
            'top_source':{'source_job_id':job_id,'source_kind':'measured'}})
        self.assertEqual(code,200)
        self.assertEqual(preview['faces']['top']['shape'],[3,2])
        self.assertEqual(preview['faces']['top']['origin_x_mm'],12)
        self.assertEqual(preview['faces']['top']['origin_y_mm'],34)

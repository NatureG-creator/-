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
    def test_double_registration_signature_is_bound_to_sources_and_mapping(self):
        buf=io.BytesIO(b'0,0.1,0.2\n0.3,0.4,0.5\n')
        uploaded=self.server.upload('registration.csv',buf,len(buf.getvalue()))
        face={'upload_id':uploaded['id'],'mapping':{'dx_mm':.3,'dy_mm':.3}}
        payload={'options':{'corrosion_mode':'double_independent'},'top_source':face,
                 'bottom_source':face,'registration_confirmed':True}
        with patch.object(self.server,'launch'):
            code,error=self.request('/api/apdl/jobs',payload)
        self.assertEqual(code,400,'a boolean for an earlier pair is not a source-bound confirmation')
        self.assertIn('预检',error['error'])
        code,preview=self.request('/api/apdl/precheck',payload)
        self.assertEqual(code,200)
        signature=preview['registration_signature']
        self.assertEqual(len(signature),64)
        payload['registration_signature']=signature
        payload['options']['E_MPa']=190000
        code,new_preview=self.request('/api/apdl/precheck',payload)
        self.assertEqual(new_preview['registration_signature'],signature,'material does not change XY registration')
        with patch.object(self.server,'launch'):
            self.assertEqual(self.request('/api/apdl/jobs',payload)[0],201)
        payload['top_source']={**face,'mapping':{**face['mapping'],'flip_x':True}}
        with patch.object(self.server,'launch'):
            code,error=self.request('/api/apdl/jobs',payload)
        self.assertEqual(code,400)
        self.assertIn('配准',error['error'])

    def test_apdl_flat_precheck_and_real_worker_build(self):
        payload={'options':{'corrosion_mode':'flat'}}
        code,preview=self.request('/api/apdl/precheck',payload)
        self.assertEqual(code,200)
        self.assertEqual(preview['stats']['node_count'],220)
        self.assertEqual(preview['diagnostics']['mesh_quality']['status'],'precheck_only')
        self.assertEqual(preview['diagnostics']['output_policy']['result_save_mode'],'all')
        self.assertEqual(preview['diagnostics']['material_coverage']['status'],'not_applicable')
        with patch.object(self.server,'launch'):
            code,job=self.request('/api/apdl/jobs',payload)
        self.assertEqual(code,201)
        run_job(job['id'],self.server.runtime)
        detail=self.server.get_job(job['id'])
        self.assertEqual(detail['state'],'completed',detail.get('error'))
        root=self.server.runtime/'jobs'/job['id']/'outputs'
        result=json.loads((root/'summary.json').read_text(encoding='utf-8'))
        self.assertEqual(result['solve_state'],'not_requested')
        self.assertEqual(result['diagnostics_schema_version'],2)
        self.assertEqual(result['diagnostics']['mesh_quality']['status'],'precheck_only')
        self.assertEqual(result['diagnostics']['output_policy']['result_save_mode'],'all')
        self.assertTrue((root/'main.inp').is_file())
        self.assertFalse((root/'force_displacement.csv').exists())
        for filename in ('apdl_self_check.csv','mesh_quality_report.txt','material_coverage_history.csv'):
            self.assertFalse((root/filename).exists(),filename+' must only come from actual MAPDL')

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
        payload['registration_signature']=preview['registration_signature']
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

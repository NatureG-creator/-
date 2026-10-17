import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from backend.tests import test_apdl_api as api_tests
from backend.worker import run_job


class ToolsAPITests(unittest.TestCase):
    setUp = api_tests.ApdlApiTests.setUp
    tearDown = api_tests.ApdlApiTests.tearDown
    request = api_tests.ApdlApiTests.request

    def upload(self, text, name='data.csv'):
        raw = text.encode()
        return self.server.upload(name, io.BytesIO(raw), len(raw))['id']

    def build(self):
        with patch.object(self.server, 'launch'):
            code, job = self.request('/api/apdl/jobs', {'options': {'corrosion_mode': 'flat','nx':3,'ny':2,'layers':1}})
        self.assertEqual(code, 201)
        run_job(job['id'], self.server.runtime)
        return job['id']

    def test_material_file_inspect_import_and_reject_bad_mapping(self):
        upload_id = self.upload('strain,stress\n0,300\n0.01,400\n')
        self.assertEqual(self.request('/api/apdl/table-inspect', {'upload_id':upload_id})[0],200)
        selection = dict(strain_column=0,stress_column=1,strain_unit='fraction',
                         stress_unit='MPa',strain_type='true_plastic',E_MPa=200000)
        code, result = self.request('/api/apdl/material-import',dict(upload_id=upload_id,selection=selection))
        self.assertEqual(code, 200)
        self.assertEqual(result['points'], 2)
        self.assertEqual(result['source']['upload_id'], upload_id)
        selection['strain_column']=1
        self.assertEqual(self.request('/api/apdl/material-import',dict(upload_id=upload_id,selection=selection))[0],400)

    def test_editor_routes_and_separate_comparison_preserve_original(self):
        job_id = self.build()
        code, snapshot = self.request(f'/api/apdl/jobs/{job_id}/commands')
        self.assertEqual(code,200)
        code, report = self.request('/api/apdl/commands/check', dict(
            source_job_id=job_id,source_revision=snapshot['revision'],command_files=snapshot['files']))
        self.assertEqual(code,200)
        self.assertEqual(report['changes'],[])
        self.assertEqual(self.request(f'/api/apdl/jobs/{job_id}/diagnosis')[0],200)
        output = self.server.runtime/'jobs'/job_id/'outputs'
        summary = (output/'summary.json').read_bytes()
        (output/'force_displacement.csv').write_text('0,0,0,0,0,0\n0.5,1,1000,-1000,.01,10\n1,2,2000,-2000,.02,20\n')
        upload_id = self.upload('u,F\n0.0005,0.5\n0.0015,1.5\n')
        code, report = self.request('/api/apdl/comparisons',dict(source_job_id=job_id,
            upload_id=upload_id,name='第一次对照',selection=dict(displacement_column=0,force_column=1,
            displacement_unit='m',force_unit='kN')))
        self.assertEqual(code,201,report)
        self.assertEqual(report['rmse_N'],0)
        self.assertTrue((output/report['relative_directory']/'experiment_original.csv').exists())
        self.assertTrue((output/report['relative_directory']/'comparison.svg').exists())
        self.assertEqual((output/'summary.json').read_bytes(),summary)

    def test_material_source_is_recomputed_frozen_and_rejects_edits(self):
        upload_id=self.upload('strain,stress\n0,300\n0.01,400\n')
        selection=dict(strain_column=0,stress_column=1,strain_unit='fraction',stress_unit='MPa',strain_type='true_plastic',E_MPa=200000)
        payload=dict(options=dict(corrosion_mode='flat',nx=3,ny=2,layers=1,E_MPa=200000,material_model='multilinear_iso',plastic_curve=[[0,300],[.01,400]]),material_source=dict(upload_id=upload_id,selection=selection))
        with patch.object(self.server,'launch'):
            code,job=self.request('/api/apdl/jobs',payload)
        self.assertEqual(code,201,job)
        self.assertTrue((self.server.runtime/'jobs'/job['id']/'inputs/material_original.csv').is_file())
        payload['options']['plastic_curve'][1][1]=401
        self.assertEqual(self.request('/api/apdl/jobs',payload)[0],400)


if __name__ == '__main__':
    unittest.main()

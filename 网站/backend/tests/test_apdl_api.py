import io
import json
import os
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

    def _saved_solved_apdl_job(self, job_id='c'*16, state='completed'):
        folder=self.server.runtime/'jobs'/job_id
        output=folder/'outputs';output.mkdir(parents=True)
        rows=np.array([[0.,0.,10.,-10.,0.,1.], [1.,.1,20.,-20.,.001,2.]])
        np.savetxt(output/'force_displacement.csv',rows,delimiter=',')
        _atomic_json(folder/'status.json',{'id':job_id,'kind':'apdl_tension','state':state,
            'created_at':1,'updated_at':1,'pid':None})
        _atomic_json(folder/'spec.json',{'kind':'apdl_tension','options':{}})
        _atomic_json(output/'summary.json',{'kind':'apdl_tension','solve_state':'solved',
            'results':{'curve':rows.tolist(),'curve_plot':{'state':'disabled'},
                       'files':['force_displacement.csv']}})
        return rows

    def test_completed_apdl_result_can_generate_plot_after_solving(self):
        rows=self._saved_solved_apdl_job()
        with patch('backend.apdl_curve_plot._write_curve_plot',side_effect=lambda path,curve:path.write_bytes(b'PNG')):
            code,job=self.request(f'/api/apdl/jobs/{"c"*16}/force-displacement-plot',{})
        self.assertEqual(code,200,job)
        output=self.server.runtime/'jobs'/('c'*16)/'outputs'
        self.assertTrue((output/'load_displacement.png').is_file())
        self.assertEqual(job['summary']['results']['curve_plot']['state'],'completed')
        self.assertIn('load_displacement.png',[item['name'] for item in job['files']])
        np.testing.assert_array_equal(np.asarray(job['summary']['results']['curve']),rows)

    def test_historical_failed_job_gets_read_only_completion_explanation(self):
        from backend.tests.test_apdl_outcome import RECOVERED
        self._saved_solved_apdl_job('b'*16,state='failed')
        folder=self.server.runtime/'jobs'/('b'*16)
        output=folder/'outputs'
        summary={'kind':'apdl_tension','options':{'target_displacement_mm':11},
                 'solve_state':'failed','solver':{'exit_code':1},'error':'exit 1'}
        _atomic_json(output/'summary.json',summary)
        (output/'mapdl.out').write_text(RECOVERED)
        (output/'corrosion.rst').write_bytes(b'fixture')
        (output/'force_displacement.csv').write_text('0.5,5.5,100,-100,.05,1\n1,11,200,-200,.1,2\n')
        before={name:(folder/name).read_bytes() for name in ('status.json','outputs/summary.json')}
        code,job=self.request('/api/jobs/'+'b'*16)
        self.assertEqual(code,200,job)
        self.assertEqual(job['state'],'failed')
        self.assertTrue(job['summary']['result_explanation']['loading_complete'])
        for name,value in before.items():
            self.assertEqual((folder/name).read_bytes(),value)

    def test_completed_apdl_result_can_generate_stress_strain_plot_after_solving(self):
        rows=self._saved_solved_apdl_job('f'*16)
        seen=[]
        def write_plot(path,curve):
            seen.append(curve.copy())
            path.write_bytes(b'PNG')
        with patch('backend.apdl_curve_plot._write_stress_strain_plot',side_effect=write_plot):
            code,job=self.request(f'/api/apdl/jobs/{"f"*16}/stress-strain-plot',{})
        self.assertEqual(code,200,job)
        output=self.server.runtime/'jobs'/('f'*16)/'outputs'
        self.assertTrue((output/'engineering_stress_strain.png').is_file())
        self.assertEqual(job['summary']['results']['stress_strain_plot']['state'],'completed')
        self.assertIn('engineering_stress_strain.png',[item['name'] for item in job['files']])
        np.testing.assert_array_equal(seen[0][:,4],rows[:,4])
        np.testing.assert_array_equal(seen[0][:,5],rows[:,5])

    def test_failed_apdl_result_can_generate_diagnostic_stress_strain_plot_from_saved_curve(self):
        rows=self._saved_solved_apdl_job('a'*16,state='failed')
        output=self.server.runtime/'jobs'/('a'*16)/'outputs'
        summary=json.loads((output/'summary.json').read_text(encoding='utf-8'))
        summary['solve_state']='failed'
        _atomic_json(output/'summary.json',summary)
        seen=[]
        def write_plot(path,curve):
            seen.append(curve.copy())
            path.write_bytes(b'PNG')
        with patch('backend.apdl_curve_plot._write_stress_strain_plot',side_effect=write_plot):
            code,job=self.request(f'/api/apdl/jobs/{"a"*16}/stress-strain-plot',{})
        self.assertEqual(code,200,job)
        self.assertEqual(job['state'],'failed')
        report=job['summary']['results']['stress_strain_plot']
        self.assertEqual(report['data_quality'],'partial')
        self.assertIn('不能作为完整有效求解结果',report['note'])
        self.assertTrue((output/'engineering_stress_strain.png').is_file())
        np.testing.assert_array_equal(seen[0][:,4:],rows[:,4:])

    def test_postsolve_plot_rejects_running_jobs_and_unverified_csv(self):
        self._saved_solved_apdl_job('d'*16,state='running')
        folder=self.server.runtime/'jobs'/('d'*16)
        status=json.loads((folder/'status.json').read_text(encoding='utf-8'))
        status['pid']=os.getpid()
        _atomic_json(folder/'status.json',status)
        code,error=self.request(f'/api/apdl/jobs/{"d"*16}/force-displacement-plot',{})
        self.assertEqual(code,400)
        self.assertIn('已结束',error['error'])
        self._saved_solved_apdl_job('e'*16)
        csv=self.server.runtime/'jobs'/('e'*16)/'outputs'/'force_displacement.csv'
        csv.write_text('0,0,10,-10,0,1\n1,.1,20,-20,.002,2\n',encoding='ascii')
        code,error=self.request(f'/api/apdl/jobs/{"e"*16}/force-displacement-plot',{})
        self.assertEqual(code,400)
        self.assertIn('不一致',error['error'])

    def test_local_corrosion_precheck_reports_plate_and_patch_coordinates(self):
        stream=io.BytesIO();np.savetxt(stream,np.array([[.1,.2],[.3,.4]]),delimiter=',');data=stream.getvalue()
        upload=self.server.upload('local_patch.csv',io.BytesIO(data),len(data))
        payload={'options':{'corrosion_mode':'single_top','local_corrosion':True,
                            'length_mm':4,'width_mm':3,'layers':1},
                 'top_source':{'upload_id':upload['id'],'mapping':{'layout':'yx','dx_mm':1,
                    'dy_mm':1,'origin_x_mm':0,'origin_y_mm':0}}}
        code,preview=self.request('/api/apdl/precheck',payload)
        self.assertEqual(code,200,preview)
        self.assertEqual((preview['stats']['nx'],preview['stats']['ny']),(5,4))
        self.assertEqual(preview['corrosion_region']['x_range_mm'],[2,3])
        self.assertEqual(preview['corrosion_region']['y_range_mm'],[1,2])
        self.assertEqual(preview['preview']['top_depth'][1][2],.1)
        self.assertEqual(preview['options']['patch_offset_x_mm'],2)
        with patch.object(self.server,'launch'):
            code,job=self.request('/api/apdl/jobs',payload)
        self.assertEqual(code,201,job)
        run_job(job['id'],self.server.runtime)
        summary=json.loads((self.server.runtime/'jobs'/job['id']/'outputs'/'summary.json').read_text(encoding='utf-8'))
        self.assertEqual(summary['provenance']['corrosion_region'],preview['corrosion_region'])
        with np.load(self.server.runtime/'jobs'/job['id']/'outputs'/'surface_inputs.npz') as surface:
            self.assertEqual(surface['top_depth'].shape,(4,5))
            self.assertEqual(float(surface['top_depth'].sum()),1.0)

    def test_common_xy_precheck_frozen_worker_and_report_agree(self):
        from backend.apdl_service import sha256
        import zipfile
        faces={}
        for label,shape,step,origin in [('top',(5,7),.5,0.),('bottom',(3,4),.75,.25)]:
            x=origin+np.arange(shape[1])*step
            y=origin+np.arange(shape[0])*step
            depth=.1+.1*x[None,:]+.2*y[:,None]
            stream=io.BytesIO();np.savetxt(stream,depth,delimiter=',');data=stream.getvalue()
            upload=self.server.upload(label+'.csv',io.BytesIO(data),len(data))
            faces[label+'_source']={'upload_id':upload['id'],'mapping':{'layout':'yx',
                'dx_mm':step,'dy_mm':step,'origin_x_mm':origin,'origin_y_mm':origin}}
        payload={'options':{'corrosion_mode':'double_independent','surface_grid_mode':'common_xy'},
                 'registration_confirmed':True,**faces}
        code,preview=self.request('/api/apdl/precheck',payload)
        self.assertEqual(code,200,preview)
        self.assertEqual(preview['faces']['top']['shape'],[5,7])
        self.assertEqual(preview['faces']['bottom']['shape'],[3,4])
        self.assertEqual((preview['stats']['nx'],preview['stats']['ny']),(4,3))
        self.assertEqual(preview['options']['dx_mm'],.75)
        self.assertTrue(preview['surface_mapping']['sources']['top']['cropped'])
        payload['registration_signature']=preview['registration_signature']
        with patch.object(self.server,'launch'):
            code,job=self.request('/api/apdl/jobs',payload)
        self.assertEqual(code,201,job)
        run_job(job['id'],self.server.runtime)
        detail=self.server.get_job(job['id'])
        self.assertEqual(detail['state'],'completed',detail.get('error'))
        folder=self.server.runtime/'jobs'/job['id']
        summary=json.loads((folder/'outputs'/'summary.json').read_text(encoding='utf-8'))
        mapping=summary['provenance']['surface_mapping']
        self.assertEqual(mapping,preview['surface_mapping'])
        self.assertTrue(any('双线性' in w for w in summary['warnings']))
        with np.load(folder/'outputs'/'surface_inputs.npz') as stored:
            np.testing.assert_array_equal(stored['top_depth'],preview['preview']['top_depth'])
            np.testing.assert_array_equal(stored['x'],preview['preview']['x_mm'])
            np.testing.assert_array_equal(stored['y'],preview['preview']['y_mm'])
            np.testing.assert_allclose(stored['top_depth'],stored['bottom_depth'],atol=2e-16)
        for label in ('top','bottom'):
            self.assertEqual(sha256(folder/'inputs'/(label+'.csv')),preview['faces'][label]['sha256'])
        with zipfile.ZipFile(folder/'outputs'/'apdl_tension_input_bundle.zip') as archive:
            self.assertEqual(json.loads(archive.read('surface_mapping.json')),mapping)
        code,draft=self.request(f'/api/apdl/jobs/{job["id"]}/reload-config',{})
        self.assertEqual(code,200,draft)
        self.assertEqual(draft['options']['surface_grid_mode'],'common_xy')
        self.assertIsNone(draft['options']['mapping_dx_mm'])
        self.assertIsNone(draft['options']['mapping_dy_mm'])
        self.assertFalse(draft['registration_confirmed'])
        restored={'options':draft['options'],'registration_confirmed':True}
        for label in ('top','bottom'):
            restored[label+'_source']={k:draft[label][k] for k in ('upload_id','source_kind','mapping')}
        code,rechecked=self.request('/api/apdl/precheck',restored)
        self.assertEqual(code,200,rechecked)
        self.assertEqual(rechecked['surface_mapping'],mapping)
        payload['options']['mapping_dx_mm']=1.
        with patch.object(self.server,'launch'):
            code,error=self.request('/api/apdl/jobs',payload)
        self.assertEqual(code,400)
        self.assertIn('预检',error['error'])
        payload['options']['surface_grid_mode']='strict'
        code,error=self.request('/api/apdl/precheck',payload)
        self.assertEqual(code,400)
        self.assertIn('严格模式',error['error'])

    def test_coordinate_pair_strict_and_common_xy(self):
        top=self._upload_coordinate_triplet('top')
        bottom=self._upload_coordinate_triplet('bottom')
        payload={'options':{'corrosion_mode':'double_independent'},'registration_confirmed':True,
                 'top_source':{'source_kind':'coordinates','coordinate_uploads':top,'coordinate_direction':'front'},
                 'bottom_source':{'source_kind':'coordinates','coordinate_uploads':bottom,'coordinate_direction':'back'}}
        code,result=self.request('/api/apdl/precheck',payload)
        self.assertEqual(code,200,result)
        payload['bottom_source']['coordinate_uploads']=self._upload_coordinate_triplet('shift',x_shift=.01)
        payload['options'].update(surface_grid_mode='common_xy',mapping_dx_mm=.1)
        code,result=self.request('/api/apdl/precheck',payload)
        self.assertEqual(code,200,result)
        self.assertEqual(result['surface_mapping']['origin_x_mm'],.01)

    def _upload_coordinate_triplet(self, prefix='face', x_shift=0.0):
        x,y=np.meshgrid([0.0+x_shift,.3+x_shift],[0.0,.3])
        z=np.array([[5.0,4.8],[4.9,5.0]])
        ids={}
        for axis,values in (('x',x),('y',y),('z',z)):
            stream=io.BytesIO();np.savetxt(stream,np.asarray(values).reshape(-1),fmt='%.9g');data=stream.getvalue()
            ids[axis]=self.server.upload(f'{prefix}_{axis}.txt',io.BytesIO(data),len(data))['id']
        return ids

    def test_coordinate_files_precheck_and_freeze(self):
        uploads=self._upload_coordinate_triplet()
        payload={'options':{'corrosion_mode':'single_top'},'top_source':{
            'source_kind':'coordinates','origin':'coordinates','coordinate_uploads':uploads,
            'coordinate_direction':'front'}}
        code,preview=self.request('/api/apdl/precheck',payload)
        self.assertEqual(code,200)
        self.assertEqual(preview['faces']['top']['shape'],[2,2])
        self.assertEqual(preview['faces']['top']['xy_grid_sha256'].__class__,str)
        self.assertAlmostEqual(preview['faces']['top']['max_depth_mm'],.2)
        with patch.object(self.server,'launch'):
            code,job=self.request('/api/apdl/jobs',payload)
        self.assertEqual(code,201)
        inputs=self.server.runtime/'jobs'/job['id']/'inputs'
        self.assertTrue((inputs/'top_x.txt').is_file())
        self.assertTrue((inputs/'top_y.txt').is_file())
        self.assertTrue((inputs/'top_z.txt').is_file())

    def test_double_coordinate_files_reject_xy_mismatch(self):
        top=self._upload_coordinate_triplet('top')
        bottom=self._upload_coordinate_triplet('bottom',x_shift=.01)
        payload={'options':{'corrosion_mode':'double_independent'},'registration_confirmed':True,
                 'top_source':{'source_kind':'coordinates','coordinate_uploads':top,'coordinate_direction':'front'},
                 'bottom_source':{'source_kind':'coordinates','coordinate_uploads':bottom,'coordinate_direction':'back'}}
        code,error=self.request('/api/apdl/precheck',payload)
        self.assertEqual(code,400)
        self.assertRegex(error['error'],'不一致|配准|原点')
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

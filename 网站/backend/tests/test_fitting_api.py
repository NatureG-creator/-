import io
import json
import os
import unittest
import zipfile
from unittest.mock import patch
from backend.tests import test_finite_element_api as fixture
from backend.runner import _atomic_json
from backend.worker import run_job


class FittingApiTests(unittest.TestCase):
    setUp=fixture.FiniteElementApiTests.setUp
    tearDown=fixture.FiniteElementApiTests.tearDown
    request=fixture.FiniteElementApiTests.request

    def payload(self):
        return dict(source={'text':'x,y\n'+ '\n'.join(f'{i},{2*i+1}' for i in range(12))},
                    selection=dict(x_column=0,y_column=1),options=dict(models=['linear'],folds=3),
                    plot=dict(dpi=72,width_mm=120,height_mm=100))

    def apdl_source(self, job_id='c'*16, state='completed', include_curve=True):
        folder=self.server.runtime/'jobs'/job_id
        output=folder/'outputs';output.mkdir(parents=True)
        _atomic_json(folder/'status.json',dict(id=job_id,kind='apdl_tension',state=state,
                     created_at=1,updated_at=1,pid=os.getpid() if state=='running' else None))
        _atomic_json(folder/'spec.json',dict(kind='apdl_tension',case_name='test APDL'))
        if include_curve:
            (output/'force_displacement.csv').write_text(
                'time,displacement_mm,loaded_reaction_N,fixed_reaction_N,engineering_strain,nominal_stress_MPa\n'
                '0,0,10,-10,0,1\n1,0.1,20,-20,0.001,2\n',encoding='utf-8')
        return folder

    def test_apdl_sources_list_and_inspect_preserve_quality_and_curve_columns(self):
        self.apdl_source()
        self.apdl_source('d'*16,state='failed')
        self.apdl_source('e'*16,include_curve=False)
        code,sources=self.request('/api/fitting/sources')
        self.assertEqual(code,200,sources)
        self.assertEqual({row['id'] for row in sources},{'c'*16,'d'*16})
        self.assertEqual({row['id']:row['data_quality'] for row in sources},
                         {'c'*16:'complete','d'*16:'partial'})

        code,table=self.request('/api/fitting/inspect',{'source_job_id':'c'*16})
        self.assertEqual(code,200,table)
        self.assertEqual(len(table['columns']),6)
        self.assertEqual(table['source']['data_quality'],'complete')
        self.assertEqual(len(table['rows']),2)

        payload=dict(source={'source_job_id':'d'*16},selection=dict(x_column=1,y_columns=[2,5]),
                     plot=dict(kind='line',width_mm=120,height_mm=90))
        code,plot=self.request('/api/fitting/plot',payload)
        self.assertEqual(code,200,plot)
        self.assertEqual(plot['source']['data_quality'],'partial')
        self.assertEqual([item['plotted'] for item in plot['plot']['y_columns']],[2,2])

    def test_apdl_source_rejects_running_job_and_missing_curve(self):
        self.apdl_source('a'*16,state='running')
        self.apdl_source('b'*16,include_curve=False)
        for job_id in ('a'*16,'b'*16):
            code,result=self.request('/api/fitting/inspect',{'source_job_id':job_id})
            self.assertEqual(code,400,result)

    def test_catalog_and_precheck(self):
        code,catalog=self.request('/api/fitting/catalog')
        self.assertEqual(code,200)
        self.assertTrue(catalog['models'])
        self.assertEqual(catalog['origin']['state'],'direct_plotting')
        code,result=self.request('/api/fitting/precheck',self.payload())
        self.assertEqual(code,200,result)
        self.assertEqual(result['dataset']['row_count'],12)
        self.assertEqual(result['dataset']['audit']['retained_rows'],12)

    def test_direct_plot_renders_multiple_series_and_reports_skipped_rows(self):
        payload=dict(source={'text':'time,depth,width\n0,1,4\n1,2,5\n2,,6\n3,4,7'},
                     selection=dict(x_column=0,y_columns=[1,2]),
                     plot=dict(kind='line',width_mm=120,height_mm=90))
        code,result=self.request('/api/fitting/plot',payload)
        self.assertEqual(code,200,result)
        self.assertTrue(result['svg'].lstrip().startswith('<?xml'))
        self.assertEqual(result['row_count'],4)
        self.assertEqual([item['plotted'] for item in result['plot']['y_columns']],[3,4])
        self.assertEqual([item['skipped'] for item in result['plot']['y_columns']],[1,0])
        self.assertEqual(self.server.list_jobs(),[])

    def test_direct_plot_rejects_invalid_or_overlapping_columns(self):
        base=dict(source={'text':'x,a,b\n0,1,2\n1,2,3\n2,3,4'},
                  selection=dict(x_column=0,y_columns=[1]),plot={})
        for selection in (dict(x_column=0,y_columns=[0]),dict(x_column=True,y_columns=[1]),
                          dict(x_column=0,y_columns=[99]),dict(x_column=0,y_columns=[])):
            payload={**base,'selection':selection}
            self.assertEqual(self.request('/api/fitting/plot',payload)[0],400,selection)

    def test_worker_bundle_contains_real_outputs_and_hashes(self):
        with patch.object(self.server,'launch'):
            code,job=self.request('/api/fitting/jobs',self.payload())
        self.assertEqual(code,201,job)
        run_job(job['id'],self.server.runtime)
        state=self.server.get_job(job['id'])
        self.assertEqual(state['state'],'completed',state.get('error'))
        root=self.server.runtime/'jobs'/job['id']/'outputs'
        summary=json.loads((root/'summary.json').read_text(encoding='utf-8'))
        self.assertEqual(summary['kind'],'fitting')
        self.assertEqual(summary['groups'][0]['recommended_id'],'linear')
        self.assertTrue(summary['plots'])
        self.assertTrue((root/'origin_import.py').exists())
        with zipfile.ZipFile(root/'fitting_bundle.zip') as archive:
            self.assertIn('summary.json',archive.namelist())
            self.assertIn('inputs/table.json',archive.namelist())
            manifest=json.loads(archive.read('manifest.json'))
            import hashlib
            for item in manifest['files']:
                self.assertEqual(hashlib.sha256(archive.read(item['name'])).hexdigest(),item['sha256'])

    def test_upload_freeze_rejects_changed_source(self):
        raw=b'x,y\n0,1\n1,3\n2,5\n3,7\n4,9\n5,11'
        record=self.server.upload('fit.csv',io.BytesIO(raw),len(raw))
        payload=self.payload();payload['source']={'upload_id':record['id']}
        code,table=self.request('/api/fitting/inspect',payload['source'])
        self.assertEqual(code,200,table)
        self.assertEqual(table['columns'],['x','y'])
        _,source=self.server.get_upload(record['id']);source.write_bytes(raw+b'\n6,13')
        with patch.object(self.server,'launch'):
            code,error=self.request('/api/fitting/jobs',payload)
        self.assertEqual(code,400)
        self.assertIn('改变',error['error'])

    def test_precheck_rejects_bad_metric_and_missing(self):
        payload=self.payload();payload['options']['metric']='bogus'
        self.assertEqual(self.request('/api/fitting/precheck',payload)[0],400)

    def test_corrupt_spreadsheets_are_user_errors(self):
        for suffix,raw in (('xlsx',b'not a zip'),('mat',b'not a mat')):
            record=self.server.upload('broken.'+suffix,io.BytesIO(raw),len(raw))
            self.assertEqual(self.request('/api/fitting/inspect',dict(upload_id=record['id']))[0],400)
        payload=self.payload();payload['source']['text']='x,y\n0,1\n1,\n2,5\n3,7'
        self.assertEqual(self.request('/api/fitting/precheck',payload)[0],400)

    def test_truncated_excel_sheet_is_user_error(self):
        import openpyxl
        book=openpyxl.Workbook();book.active.append(['x','y']);book.active.append([1,2])
        original=io.BytesIO();book.save(original);book.close();original.seek(0)
        broken=io.BytesIO()
        with zipfile.ZipFile(original) as source, zipfile.ZipFile(broken,'w') as target:
            for name in source.namelist():
                raw=source.read(name)
                target.writestr(name,raw[:-10] if name=='xl/worksheets/sheet1.xml' else raw)
        raw=broken.getvalue();record=self.server.upload('broken.xlsx',io.BytesIO(raw),len(raw))
        self.assertEqual(self.request('/api/fitting/inspect',dict(upload_id=record['id']))[0],400)


if __name__=='__main__':unittest.main()

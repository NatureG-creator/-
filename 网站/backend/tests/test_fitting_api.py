import io
import json
import unittest
import zipfile
from unittest.mock import patch
from backend.tests import test_finite_element_api as fixture
from backend.worker import run_job


class FittingApiTests(unittest.TestCase):
    setUp=fixture.FiniteElementApiTests.setUp
    tearDown=fixture.FiniteElementApiTests.tearDown
    request=fixture.FiniteElementApiTests.request

    def payload(self):
        return dict(source={'text':'x,y\n'+ '\n'.join(f'{i},{2*i+1}' for i in range(12))},
                    selection=dict(x_column=0,y_column=1),options=dict(models=['linear'],folds=3),
                    plot=dict(dpi=72,width_mm=120,height_mm=100))

    def test_catalog_and_precheck(self):
        code,catalog=self.request('/api/fitting/catalog')
        self.assertEqual(code,200)
        self.assertTrue(catalog['models'])
        code,result=self.request('/api/fitting/precheck',self.payload())
        self.assertEqual(code,200,result)
        self.assertEqual(result['dataset']['row_count'],12)
        self.assertEqual(result['dataset']['audit']['retained_rows'],12)

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

import csv
import hashlib
import json
import unittest
from unittest.mock import patch
from urllib.request import urlopen

from backend.runner import _atomic_json
from backend.tests import test_apdl_api as api_tests
from backend.worker import run_job
from backend.apdl_stress_strain import _completed_curve


class ApdlStressStrainApiTests(unittest.TestCase):
    setUp = api_tests.ApdlApiTests.setUp
    tearDown = api_tests.ApdlApiTests.tearDown
    request = api_tests.ApdlApiTests.request

    def solved_job(self, name):
        with patch.object(self.server, 'launch'):
            code, job = self.request('/api/apdl/jobs', {'case_name': name,
                'options': {'corrosion_mode': 'flat', 'nx': 3, 'ny': 2, 'layers': 1}})
        self.assertEqual(code, 201, job)
        run_job(job['id'], self.server.runtime)
        output = self.server.runtime / 'jobs' / job['id'] / 'outputs'
        summary = json.loads((output / 'summary.json').read_text(encoding='utf-8'))
        summary['solve_state'] = 'solved'
        _atomic_json(output / 'summary.json', summary)
        (output / 'force_displacement.csv').write_text(
            '0,0,0,0,0,0\n0.5,1,1000,-1000,0.01,10\n1,2,2000,-2000,0.02,20\n',
            encoding='utf-8')
        return job['id']

    def test_completed_solver_curves_compare_and_export_with_provenance(self):
        first = self.solved_job('one')
        second = self.solved_job('two')
        originals = {name: path.read_bytes() for name in (first, second)
                     for path in [self.server.runtime / 'jobs' / name / 'outputs' / 'force_displacement.csv']}
        code, sources = self.request('/api/apdl/stress-strain/sources')
        self.assertEqual(code, 200)
        self.assertEqual({source['id'] for source in sources}, {first, second})

        code, report = self.request('/api/apdl/stress-strain/comparisons', {'sources': [
            {'job_id': first, 'label': '腐蚀 30 天'},
            {'job_id': second, 'label': '腐蚀 60 天'},
        ]})
        self.assertEqual(code, 201, report)
        self.assertEqual([item['label'] for item in report['sources']], ['腐蚀 30 天', '腐蚀 60 天'])
        self.assertEqual(report['sources'][0]['engineering_strain_percent_range'], [0, 2])
        self.assertEqual(report['x_axis']['source_column'], 5)
        self.assertEqual(report['y_axis']['source_column'], 6)
        for name in ('curve.csv', 'curve.png', 'curve.svg', 'report.json'):
            with urlopen(self.base + f"/api/apdl/stress-strain-comparisons/{report['id']}/{name}") as response:
                self.assertEqual(response.status, 200, name)
                self.assertTrue(response.headers['Content-Type'])
                self.assertGreater(len(response.read()), 0)
                self.assertIsNone(response.headers.get('Content-Disposition'))
        with urlopen(self.base + f"/api/apdl/stress-strain-comparisons/{report['id']}/curve.png?download=1") as response:
            self.assertIn('attachment', response.headers['Content-Disposition'])
        csv_path = self.server.runtime / 'apdl_stress_strain_comparisons' / report['id'] / 'curve.csv'
        with csv_path.open(encoding='utf-8-sig', newline='') as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(len(rows), 6)
        self.assertEqual([float(row['engineering_strain_percent']) for row in rows], [0, 1, 2, 0, 1, 2])
        self.assertEqual([float(row['nominal_stress_mpa']) for row in rows], [0, 10, 20, 0, 10, 20])
        for item in report['sources']:
            self.assertEqual(item['sha256'], hashlib.sha256(originals[item['job_id']]).hexdigest())
            path = self.server.runtime / 'jobs' / item['job_id'] / 'outputs' / 'force_displacement.csv'
            self.assertEqual(path.read_bytes(), originals[item['job_id']])

    def test_rejects_single_source_uncompleted_job_and_bad_curve(self):
        valid = self.solved_job('valid')
        self.assertEqual(self.request('/api/apdl/stress-strain/comparisons', {'sources': [
            {'job_id': valid, 'label': 'only'}]})[0], 400)
        self.assertEqual(self.request('/api/apdl/stress-strain/comparisons', {'sources': [
            {'job_id': valid, 'label': 'valid'},
            {'job_id': 'f' * 16, 'label': 'missing'}]})[0], 404)
        output = self.server.runtime / 'jobs' / valid / 'outputs'
        (output / 'force_displacement.csv').write_text('0,0,0,0,0,0\n', encoding='utf-8')
        other = self.solved_job('other')
        self.assertEqual(self.request('/api/apdl/stress-strain/comparisons', {'sources': [
            {'job_id': valid, 'label': 'bad'}, {'job_id': other, 'label': 'good'}]})[0], 400)

    def test_rejects_invalid_selection_and_non_solved_source(self):
        first, second = self.solved_job('first'), self.solved_job('second')
        sources = [{'job_id': first, 'label': 'a'}, {'job_id': second, 'label': 'b'}]
        for bad in ([sources[0]], [sources[0]] * 2, sources * 11,
                    [sources[0], {'job_id': [], 'label': 'bad'}],
                    [sources[0], {'job_id': second, 'label': ' '}],
                    [sources[0], {'job_id': second, 'label': 'a' * 81}]):
            with self.subTest(selection=bad):
                self.assertEqual(self.request('/api/apdl/stress-strain/comparisons', {'sources': bad})[0], 400)
        summary_path = self.server.runtime / 'jobs' / second / 'outputs' / 'summary.json'
        summary = json.loads(summary_path.read_text(encoding='utf-8'))
        for state in ('not_requested', 'failed', 'process_finished'):
            summary['solve_state'] = state
            _atomic_json(summary_path, summary)
            self.assertEqual(len(self.request('/api/apdl/stress-strain/sources')[1]), 1)
            self.assertEqual(self.request('/api/apdl/stress-strain/comparisons', {'sources': sources})[0], 400)

    def test_curve_validation_preserves_signs_and_rejects_changed_results(self):
        job_id = self.solved_job('validate')
        output = self.server.runtime / 'jobs' / job_id / 'outputs'
        path = output / 'force_displacement.csv'
        path.write_text('0,0,0,0,0,0\n1,2,-2000,2000,0.02,-20\n', encoding='utf-8')
        points, digest, _ = _completed_curve(self.server, job_id)
        self.assertEqual(points.tolist(), [[0, 0], [2, -20]])
        self.assertEqual(digest, hashlib.sha256(path.read_bytes()).hexdigest())
        for text in ('0,0,0,0,0\n1,2,3,4,5\n',
                     '0,0,0,0,0,0\n1,2,3,4,nan,6\n',
                     '0,0,0,0,0.02,0\n1,2,3,4,0.01,6\n',
                     '0,0,0,0,0,0\n1,2,3,4,1e308,6\n'):
            path.write_text(text, encoding='utf-8')
            with self.subTest(text=text), self.assertRaises(ValueError):
                _completed_curve(self.server, job_id)
        path.write_text('0,0,0,0,0,0\n1,2,-2000,2000,0.02,-20\n', encoding='utf-8')
        summary_path = output / 'summary.json'
        summary = json.loads(summary_path.read_text(encoding='utf-8'))
        summary['results'] = {'curve': [[0, 0, 0, 0, 0, 0], [1, 2, -2000, 2000, .02, -21]]}
        _atomic_json(summary_path, summary)
        with self.assertRaisesRegex(ValueError, '不一致'):
            _completed_curve(self.server, job_id)


if __name__ == '__main__':
    unittest.main()

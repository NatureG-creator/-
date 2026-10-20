import csv
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


class FittingOutputsTests(unittest.TestCase):
    def tempdir(self):
        base = Path(__file__).resolve().parents[1] / '.runtime' / 'output-tests'
        base.mkdir(parents=True, exist_ok=True)
        return tempfile.TemporaryDirectory(dir=base)

    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('backend.fitting_outputs'), 'fitting outputs module is missing')
        from backend import fitting_outputs
        return fitting_outputs

    def fixture(self):
        c = dict(id='linear', label='Linear', formula='a*x+b', status='success', parameters={'a': 2, 'b': 1}, metrics={'rmse': .1}, residuals=[.1, -.1, .1], y_fitted=[3, 5, 7], cv_predictions=[3.1, 4.9, 7.1], curve={'x': [0, 1, 2, 3, 4], 'y': [1, 3, 5, 7, 9], 'confidence_lower': [.8, 2.8, 4.8, 6.8, 8.8], 'confidence_upper': [1.2, 3.2, 5.2, 7.2, 9.2]})
        d = dict(x=[1, 2, 3], y=[3.1, 4.9, 7.1], sigma=[.2, .3, .2], groups=['=bad'] * 3, row_ids=[2, 3, 4], audit={})
        r = dict(options={'metric': 'rmse'}, groups=[dict(label='=bad', x=d['x'], y=d['y'], row_ids=d['row_ids'], recommended_id='linear', candidates=[c])])
        return r, d

    def test_options_budget_and_enum(self):
        m = self.module()
        self.assertEqual(m.normalise_plot_options({})['dpi'], 300)
        for options in ({'dpi': 601}, {'width_mm': 301}, {'x_scale': 'symlog'}, {'theme': 'evil'}, {'height_mm': float('nan')}):
            with self.assertRaises(ValueError):
                m.normalise_plot_options(options)

    def test_real_figures_csv_and_origin_package(self):
        m = self.module()
        r, d = self.fixture()
        with self.tempdir() as directory:
            out = m.write_fitting_outputs(r, d, directory, {'dpi': 72, 'width_mm': 100, 'height_mm': 100})
            json.dumps(out, allow_nan=False)
            self.assertEqual(len(out['plots']), 2)
            for base in ('g001_diagnostics', 'g001_models'):
                for ext in ('png', 'pdf', 'svg', 'tiff'):
                    p = Path(directory) / (base + '.' + ext)
                    self.assertGreater(p.stat().st_size, 100)
            svg = (Path(directory) / 'g001_diagnostics.svg').read_text(encoding='utf-8')
            self.assertNotIn('<script', svg)
            with (Path(directory) / 'data.csv').open(encoding='utf-8-sig', newline='') as handle:
                rows = list(csv.reader(handle))
            self.assertEqual(rows[1][1], "'=bad")
            script = (Path(directory) / 'origin_import.py').read_text(encoding='utf-8')
            compile(script, 'origin_import.py', 'exec')
            self.assertIn('import originpro', script)
            self.assertIn('__file__', script)

    def test_no_recommendation_does_not_invent_diagnostics(self):
        m = self.module()
        r, d = self.fixture()
        r['groups'][0]['recommended_id'] = None
        with self.tempdir() as directory:
            out = m.write_fitting_outputs(r, d, directory, {'dpi': 72})
            self.assertFalse((Path(directory) / 'g001_diagnostics.png').exists())
            self.assertTrue((Path(directory) / 'g001_linear_curve.csv').exists())
            self.assertTrue(out['warnings'])

    def test_log_rejects_nonpositive_observations(self):
        m = self.module()
        r, d = self.fixture()
        d['x'][0] = 0
        with self.tempdir() as directory:
            with self.assertRaises(ValueError):
                m.write_fitting_outputs(r, d, directory, {'x_scale': 'log'})

    def test_multiple_groups_generate_comparison_and_safe_names(self):
        m = self.module()
        r, d = self.fixture()
        import copy
        second = copy.deepcopy(r['groups'][0])
        second['label'] = '../../test'
        second['candidates'][0]['id'] = '../../model'
        second['candidates'][0]['status'] = 'ok'
        second['recommended_id'] = '../../model'
        r['groups'].append(second)
        with self.tempdir() as directory:
            out = m.write_fitting_outputs(r, d, directory, {'dpi': 72, 'width_mm': 100, 'height_mm': 100})
            self.assertTrue((Path(directory) / 'group_comparison.png').exists())
            self.assertEqual(len(out['plots']), 5)
            self.assertTrue(all('/' not in name and '\\' not in name for name in out['files']))

    def test_render_failure_keeps_csv_and_reports_limitation(self):
        m = self.module()
        r, d = self.fixture()
        with self.tempdir() as directory, patch.object(m, '_render_figures', side_effect=RuntimeError('renderer failed')):
            out = m.write_fitting_outputs(r, d, directory, {'dpi': 72})
            self.assertTrue((Path(directory) / 'data.csv').is_file())
            self.assertTrue(any('renderer failed' in note for note in out['warnings']))

    def test_ranking_preserves_invalid_cv_explanation_as_safe_json(self):
        m = self.module()
        r, d = self.fixture()
        r['metric'] = 'cv_rmse'
        r['groups'][0]['recommended_id'] = None
        candidate = r['groups'][0]['candidates'][0]
        candidate.update(status='ok', metrics={'cv_rmse': None}, cv_valid=False,
                         metric_reasons={'cv_rmse': '训练折样本不足，无法拟合三次多项式'},
                         warnings=['=HYPERLINK("https://example.invalid")', '交叉验证无效'])
        with self.tempdir() as directory:
            m.write_fitting_outputs(r, d, directory, {'dpi': 72})
            with (Path(directory) / 'model_ranking.csv').open(encoding='utf-8-sig', newline='') as handle:
                row = next(csv.DictReader(handle))
            self.assertIn('metric_reasons', row)
            self.assertEqual(json.loads(row['metric_reasons']), candidate['metric_reasons'])
            self.assertFalse(json.loads(row['cv_valid']))
            self.assertEqual(json.loads(row['warnings']), candidate['warnings'])
            for key in ('metric_reasons', 'cv_valid', 'warnings'):
                self.assertFalse(row[key].lstrip().startswith(('=', '+', '-', '@')))


if __name__ == '__main__':
    unittest.main()

import unittest

import numpy as np

from backend.fitting_multivariate import fit_multivariate_dataset, normalise_multivariate_options, profile_multivariate_data


class MultivariateFittingTests(unittest.TestCase):
    def dataset(self):
        x1 = np.tile(np.arange(1.0, 5.0), 8)
        x2 = np.repeat(np.arange(1.0, 9.0), 4)
        y = 2.0 * x1 + 3.0 * x2 + 1.5 * x1 * x2 + 4.0
        return {
            'x1': x1.tolist(),
            'x2': x2.tolist(),
            'y': y.tolist(),
            'groups': ['A'] * 16 + ['B'] * 16,
            'row_ids': list(range(1, 33)),
        }

    def test_interaction_model_is_selected_for_interaction_data(self):
        result = fit_multivariate_dataset(
            self.dataset(),
            {'models': ['linear2', 'interaction2', 'quadratic2'], 'folds': 4},
        )
        self.assertEqual(len(result['groups']), 2)
        for group in result['groups']:
            self.assertEqual(group['recommended_id'], 'interaction2')
            candidate = next(c for c in group['candidates'] if c['id'] == 'interaction2')
            self.assertLess(candidate['metrics']['cv_rmse'], 1e-10)
            self.assertEqual(candidate['status'], 'ok')
            self.assertIn('condition_number', candidate)

    def test_invalid_length_and_constant_predictor_are_rejected(self):
        data = self.dataset()
        data['x2'] = data['x2'][:-1]
        with self.assertRaises(ValueError):
            fit_multivariate_dataset(data)
        data = self.dataset()
        data['x2'] = [1.0] * len(data['x2'])
        result = fit_multivariate_dataset(data, {'models': ['linear2']})
        candidate = result['groups'][0]['candidates'][0]
        self.assertEqual(candidate['status'], 'failed')
        self.assertIn('常量', candidate['error'])

    def test_options_have_safe_budgets(self):
        options = normalise_multivariate_options({'models': ['linear2'], 'folds': 3})
        self.assertEqual(options['folds'], 3)
        with self.assertRaises(ValueError):
            normalise_multivariate_options({'models': ['unknown']})

    def test_profile_explains_data_shape_and_plot_recommendations(self):
        profile = profile_multivariate_data(self.dataset(), ['time', 'position', 'depth'])
        self.assertIn(profile['type'], {'时间/退化响应面', '点云剖面响应面', '通用双自变量'})
        self.assertTrue(profile['recommended_plots'])
        self.assertIn('依据', profile['reason'])


if __name__ == '__main__':
    unittest.main()

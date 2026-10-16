import json
import unittest
from unittest.mock import patch
import numpy as np
from backend.fitting_engine import fit_dataset, normalise_fit_options, model_catalog


class FittingTests(unittest.TestCase):
    def data(self, x=None, y=None):
        x = np.arange(1., 21.) if x is None else np.asarray(x, dtype=float)
        return dict(x=x.tolist(), y=(2*x+3).tolist() if y is None else list(y), sigma=None, groups=None, row_ids=list(range(1,len(x)+1)))

    def candidate(self, data=None, **options):
        result = fit_dataset(data or self.data(), dict(models=['linear'], **options))
        return result['groups'][0]['candidates'][0]

    def test_linear_selected_and_json(self):
        d=self.data(); d['y']=(np.asarray(d['y'])+0.02*np.sin(np.arange(20))).tolist()
        r=fit_dataset(d, dict(models=['linear','polynomial2'], metric='aicc', folds=4))
        self.assertEqual(r['groups'][0]['recommended_id'], 'linear')
        c=r['groups'][0]['candidates'][0]
        self.assertLess(c['metrics']['cv_rmse'], 0.03)
        self.assertAlmostEqual(c['parameters']['a'],2,places=3)
        json.dumps(r,allow_nan=False)

    def test_power_negative_rejected(self):
        c=fit_dataset(self.data([-2,-1,1,2,3]), {'models':['power']})['groups'][0]['candidates'][0]
        self.assertEqual(c['status'],'failed')
        self.assertIn('正', c['error'])

    def test_constant_and_small_aicc(self):
        c=self.candidate(self.data(y=np.ones(20)))
        self.assertIsNone(c['metrics']['r2'])
        c=self.candidate(self.data([1,2,3,4]), validation='loo')
        self.assertIsNone(c['metrics']['aicc'])

    def test_group_requires_independent_labels(self):
        d=self.data(); d['groups']=['A']*20
        with self.assertRaises(ValueError): fit_dataset(d,dict(validation='group'))
        d['validation_groups']=[str(i//4) for i in range(20)]
        c=self.candidate(d,validation='group',folds=3)
        for f in c['validation_folds']:
            self.assertFalse(set(d['validation_groups'][i] for i in f['train_indices']) & set(d['validation_groups'][i] for i in f['test_indices']))
        self.assertIsNone(c['curve']['confidence_lower'])

    def test_time_never_splits_equal_x(self):
        d=self.data([3,1,2,2,3,4,4,5,5,6,6,7])
        c=self.candidate(d,validation='time',folds=3)
        self.assertEqual(c['status'],'ok')
        for f in c['validation_folds']:
            self.assertLess(max(d['x'][i] for i in f['train_indices']), min(d['x'][i] for i in f['test_indices']))

    def test_ast_rejects_unsafe(self):
        for expr in ['np.exp(x)','__import__("os")','x[0]','(lambda: 1)()']:
            with self.assertRaises(ValueError): normalise_fit_options(dict(models=['custom'],custom_formula=expr,custom_parameters=['a']))

    def test_custom_fit_and_robust_information_criteria(self):
        c=fit_dataset(self.data(),dict(models=['custom'],custom_formula='a*x+b', custom_parameters=['a','b'],custom_initial=[1,0]))['groups'][0]['candidates'][0]
        self.assertAlmostEqual(c['parameters']['a'],2,places=6)
        c=self.candidate(loss='soft_l1')
        self.assertIsNone(c['metrics']['bic'])
        self.assertIsNone(c['curve']['prediction_lower'])

    def test_groups_and_reproducibility(self):
        d=self.data(); d['groups']=['A']*10+['B']*10
        opts=dict(models=['linear'],folds=3,seed=5)
        r=fit_dataset(d,opts)
        self.assertEqual(len(r['groups']),2)
        self.assertEqual(r,fit_dataset(d,opts))

    def test_normalized_custom_json_roundtrip(self):
        o=normalise_fit_options(dict(models=['custom'],custom_formula='a*x+b',custom_parameters=['a','b']))
        json.dumps(o,allow_nan=False)
        self.assertEqual(o,normalise_fit_options(o))

    def test_invalid_options_are_value_errors(self):
        for opts in [dict(prediction_min=True),dict(models=[{}]),dict(models=['custom'],custom_formula='a*x',custom_parameters=[{}]),dict(prediction_points=float('inf'))]:
            with self.assertRaises(ValueError): normalise_fit_options(opts)

    def test_rank_deficient_custom_not_recommended(self):
        r=fit_dataset(self.data(),dict(models=['custom'],custom_formula='a*x+b*x+c',custom_parameters=['a','b','c']))
        c=r['groups'][0]['candidates'][0]
        self.assertIsNone(r['groups'][0]['recommended_id'])
        self.assertTrue(c['warnings'])

    def test_cv_failed_not_recommended_even_training_metric(self):
        r=fit_dataset(self.data([1,2,3,4,5]),dict(models=['polynomial3'],metric='rmse',folds=5))
        c=r['groups'][0]['candidates'][0]
        self.assertEqual(c['status'],'ok')
        self.assertFalse(c['cv_valid'])
        self.assertIsNone(r['groups'][0]['recommended_id'])

    def test_weighted_original_scale_and_progress(self):
        d=self.data(); d['y'][-1]+=20; d['sigma']=[1.]*19+[100.]
        events=[]
        r=fit_dataset(d,dict(models=['linear']),events.append)
        c=r['groups'][0]['candidates'][0]
        self.assertAlmostEqual(c['metrics']['rmse'],np.sqrt(np.mean(np.asarray(c['residuals'])**2)))
        self.assertIsNone(c['metrics']['aicc'])
        self.assertAlmostEqual(c['parameters']['a'],2,places=3)
        self.assertEqual(events[-1]['progress'],1)

    def test_logistic_multistart_recovers_curve(self):
        x=np.linspace(-3,3,30); y=5/(1+np.exp(-2*(x-.3)))
        c=fit_dataset(self.data(x,y),dict(models=['logistic'],folds=3))['groups'][0]['candidates'][0]
        self.assertLess(c['metrics']['cv_rmse'],1e-6)
        self.assertGreater(c['multistart_count'],1)

    def test_overflow_custom_isolated_and_parameter_budget(self):
        r=fit_dataset(self.data(),dict(models=['custom','linear'],custom_formula='exp(a*x)',custom_parameters=['a'],custom_initial=[1000.]))
        self.assertEqual(r['groups'][0]['candidates'][0]['status'],'failed')
        self.assertEqual(r['groups'][0]['recommended_id'],'linear')
        with self.assertRaises(ValueError):
            normalise_fit_options(dict(models=['custom'],custom_formula='x',custom_parameters=list('abcdefghi')))

    def test_large_offset_variation_not_constant(self):
        x=np.arange(1.,21.); y=1e9+2*x+0.1*np.sin(x)
        c=self.candidate(self.data(x,y))
        self.assertIsNotNone(c['metrics']['r2'])
        self.assertIsNotNone(c['metrics']['aicc'])

    def test_log_prediction_domain_and_budgets(self):
        c=fit_dataset(self.data(),dict(models=['logarithmic'],prediction_min=-1))['groups'][0]['candidates'][0]
        self.assertEqual(c['status'],'failed')
        with self.assertRaises(ValueError): normalise_fit_options({'folds':6})

    def test_custom_zero_division_isolated(self):
        r=fit_dataset(self.data(),dict(models=['custom','linear'],custom_formula='a*x+1/0',custom_parameters=['a']))
        self.assertEqual(r['groups'][0]['candidates'][0]['status'],'failed')
        self.assertEqual(r['groups'][0]['recommended_id'],'linear')

    def test_boundary_delta_does_not_invalidate_fit(self):
        x=np.linspace(.1,1,20); y=np.sqrt(1e-10)*x
        c=fit_dataset(self.data(x,y),dict(models=['custom'],custom_formula='sqrt(a)*x',custom_parameters=['a'],custom_initial=[1e-10],custom_lower=[0],custom_upper=[1]))['groups'][0]['candidates'][0]
        self.assertEqual(c['status'],'ok')
        self.assertTrue(c['cv_valid'])
        self.assertIsNotNone(c['curve']['confidence_lower'])

    def test_interval_failure_preserves_fit_and_cv(self):
        with patch('backend.fitting_engine._prediction_jacobian',side_effect=ZeroDivisionError('interval test')):
            c=self.candidate()
        self.assertEqual(c['status'],'ok')
        self.assertTrue(c['cv_valid'])
        self.assertIsNone(c['curve']['confidence_lower'])
        self.assertIn('interval test',c['interval_reason'])

    def test_recommendation_invariant_under_y_units(self):
        x=np.linspace(0,1,20)
        for scale in [1.,1e-9,1e9]:
            r=fit_dataset(self.data(x,scale*x*x),dict(models=['linear','polynomial2']))
            self.assertEqual(r['groups'][0]['recommended_id'],'polynomial2')

    def test_exact_linear_floating_ties_favor_simple_model(self):
        for x in [np.linspace(1,20,20),np.linspace(.1,1,20)]:
            r=fit_dataset(self.data(x,2*x+3),dict(models=['linear','polynomial2','polynomial3']))
            self.assertEqual(r['groups'][0]['recommended_id'],'linear')

    def test_large_offset_does_not_hide_resolvable_curvature(self):
        x=np.linspace(.1,1,20)
        r=fit_dataset(self.data(x,1e9+1e-5*x*x),dict(models=['linear','polynomial2'],folds=3))
        self.assertEqual(r['groups'][0]['recommended_id'],'polynomial2')

    def test_statistics_follow_y_units_without_absolute_floor(self):
        x=np.arange(20.)
        base=2*x+1+.3*np.sin(x)
        reference=None
        for scale in [1.,1e-10,1e-16,1e-200,1e90]:
            g=fit_dataset(self.data(x,base*scale),dict(models=['linear'],metric='r2'))['groups'][0]
            c=g['candidates'][0]
            self.assertEqual(g['recommended_id'],'linear')
            for key in ['r2','adjusted_r2','aicc','bic']: self.assertIsNotNone(c['metrics'][key])
            if reference is None: reference=c['metrics']
            self.assertAlmostEqual(c['metrics']['r2'],reference['r2'],places=12)
            self.assertAlmostEqual(c['metrics']['adjusted_r2'],reference['adjusted_r2'],places=12)
            self.assertAlmostEqual(c['metrics']['aicc']-reference['aicc'],40*np.log(scale),places=9)
        for scale in [1.,1e-16,1e-200,1e90]:
            self.assertIsNone(self.candidate(self.data(x,np.full(20,scale)))['metrics']['r2'])

    def test_complex_expression_is_rejected_not_cast(self):
        for formula in ['a*x+(-1)**0.5','(-1)**0.5']:
            r=fit_dataset(self.data(),dict(models=['custom','linear'],custom_formula=formula,custom_parameters=['a']))
            self.assertEqual(r['groups'][0]['candidates'][0]['status'],'failed')
            self.assertEqual(r['groups'][0]['recommended_id'],'linear')


if __name__=='__main__': unittest.main()

import unittest
import numpy as np
from morphology_analysis import analyze_surface, analysis_caption
from corrosion_model.analysis import moving_avg_3d, jixiantiqu_3d
from unified_config import POSTPROCESS_CONFIG as pp, MATLAB_CA_COMPARISON_CONFIG as mc, matlab_ca_postprocess_settings


class MorphologyAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.a = np.ones((65, 43, 31))
        y, x = np.indices(self.a.shape[:2])
        depths = sum(h*np.exp(-((x-cx)**2+(y-cy)**2)/30) for cy,cx,h in [(10,10,20),(45,12,12),(30,33,26)])
        self.a[np.arange(31)[None,None,:] < depths[:,:,None]] = 0

    def test_ga_matches_original_extraction_and_preserves_state(self):
        original = self.a.copy()
        result = analyze_surface(self.a, mode='ga', space_xy_um=25, space_z_um=25, physical_layers=30)
        baseline,*_ = moving_avg_3d(self.a,pp['auto_plot_window_size'],65,43,30)
        threshold,nh = matlab_ca_postprocess_settings(float(np.ptp(baseline)))
        expected = jixiantiqu_3d(baseline,30,{'MinProminence':mc['min_prominence'],'MinDistance':mc['min_distance'],'Neighborhood':(nh,nh)},threshold)
        np.testing.assert_array_equal(result['pit_depth_cells'],expected[0])
        np.testing.assert_array_equal(result['max_locs'],expected[3])
        np.testing.assert_array_equal(self.a, original)
        self.assertEqual(result['metadata']['window_size'],15)
        self.assertIn('不约束',result['report']['objective_note'])

    def test_detail_retains_existing_interactive_rules(self):
        result = analyze_surface(self.a,mode='detail',space_xy_um=25,space_z_um=25)
        baseline,*_ = moving_avg_3d(self.a,pp['interactive_window_size'],65,43,30)
        expected = jixiantiqu_3d(baseline,30,{'MinProminence':pp['min_prominence'],'MinDistance':pp['min_distance'],'Neighborhood':(pp['neighborhood'],)*2},pp['watershed_threshold'])
        np.testing.assert_array_equal(result['pit_depth_cells'],expected[0])
        self.assertEqual(result['metadata']['physical_layers'],30)
        self.assertIn('末层',result['metadata']['layer_rule'])
        self.assertIn('n=',analysis_caption(result['report']))

    def test_ga_matches_optimized_evaluation_operators(self):
        from corrosion_model.analysis_优化版 import moving_avg_3d as smooth, jixiantiqu_3d as extract
        result=analyze_surface(self.a,mode='ga',space_xy_um=25,space_z_um=25,physical_layers=30)
        baseline,*_=smooth(self.a,pp['auto_plot_window_size'],65,43,30)
        threshold,nh=matlab_ca_postprocess_settings(float(np.ptp(baseline)))
        expected=extract(baseline,30,{'MinProminence':mc['min_prominence'],'MinDistance':mc['min_distance'],'Neighborhood':(nh,nh)},threshold)
        np.testing.assert_array_equal(result['baseline'],baseline)
        np.testing.assert_array_equal(result['pit_depth_cells'],expected[0])
        np.testing.assert_array_equal(result['max_locs'],expected[3])
        np.testing.assert_allclose(result['jsb'],np.log(1/np.maximum(expected[1]/mc['sjb_divisor'],1e-12)))

    def test_invalid_mode_and_layer_contract(self):
        for kwargs in ({'mode':'unknown'},{'physical_layers':32}):
            with self.assertRaises(ValueError): analyze_surface(self.a,space_xy_um=25,space_z_um=25,**kwargs)

    def test_empty_population_has_no_invented_distribution(self):
        result=analyze_surface(np.ones((10,12,5)),space_xy_um=25,space_z_um=25)
        self.assertEqual(result['report']['valid_count'],0)
        self.assertIsNone(result['report']['log_ratio']['mean'])


if __name__ == '__main__': unittest.main()

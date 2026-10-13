"""诊断功能的变换、缺失值、导出和出图检查。"""
import json
from tempfile import TemporaryDirectory
import unittest
import numpy as np
import matplotlib
matplotlib.use('Agg')
matplotlib.rcParams['font.sans-serif'] = ['Microsoft YaHei','SimHei','DejaVu Sans']
from depth_distribution_diagnostics import (
    prepare_depth_samples,
    make_report,
    export_diagnostics,
    plot_depth_comparison,
    plot_single_depth_distribution,
    plot_single_ratio_distribution,
)


class DepthDiagnosticsTests(unittest.TestCase):
    def test_raw_log_and_normalized_values(self):
        samples = prepare_depth_samples([1,2,4],25,1.04)
        np.testing.assert_array_equal(samples['raw_depth_um'],[25,50,100])
        np.testing.assert_allclose(samples['log_depth'],np.log([25,50,100]))
        np.testing.assert_allclose(samples['normalized_log_depth'],np.log([25,50,100])/1.04)

    def test_empty_and_invalid_values_never_add_samples(self):
        empty = make_report(prepare_depth_samples([],25,1.04))
        self.assertEqual(empty['valid_count'],0)
        report = make_report(prepare_depth_samples([0,-1,np.nan,2],25,1.04))
        self.assertEqual(report['valid_count'],1)
        self.assertEqual(report['invalid_count'],3)
        for factor in (0,-1,np.nan):
            with self.assertRaises(ValueError): prepare_depth_samples([1],25,factor)

    def test_normalization_only_rescales(self):
        samples = prepare_depth_samples(np.arange(1,31),25,1.04)
        report = make_report(samples)
        self.assertIn('mu_L=mean(L)', report['normal_fit_formula'])
        self.assertIn('sigma_L=std(L,ddof=1)', report['normal_fit_formula'])
        self.assertAlmostEqual(report['log_depth']['shapiro_p'],report['normalized_log_depth']['shapiro_p'],places=10)
        self.assertAlmostEqual(report['log_depth']['std']/1.04,report['normalized_log_depth']['std'])

    def test_export_and_three_panel_plot(self):
        samples = prepare_depth_samples([1,2,3,4],25,1.04)
        with TemporaryDirectory() as directory:
            csv_path,json_path = export_diagnostics(samples,make_report(samples),directory)
            self.assertEqual(len(csv_path.read_text(encoding='utf-8-sig').splitlines()),5)
            self.assertEqual(json.loads(json_path.read_text(encoding='utf-8'))['valid_count'],4)
            figure = plot_depth_comparison(samples)
            self.assertEqual(len(figure.axes),3)
            self.assertEqual(figure.axes[0].get_title().split('\n')[0], 'Data Histogram and Fitting Curve')
            self.assertEqual(figure.axes[0].get_xlabel(), 'Corrosion Depth')
            self.assertEqual(figure.axes[0].get_ylabel(), 'Probability Density')
            self.assertIn('ln(',figure.axes[1].get_xlabel())
            import matplotlib.pyplot as plt
            plt.close(figure)

    def test_single_depth_plot_uses_logarithmic_depth_axis(self):
        samples = prepare_depth_samples([120, 180, 240, 300, 360], 1, 1.04)
        figure = plot_single_depth_distribution(samples)
        self.assertEqual(len(figure.axes), 1)
        self.assertEqual(figure.axes[0].get_xlabel(), 'ln(H / 1 μm)')
        self.assertIn('Probability Density', figure.axes[0].get_ylabel())
        self.assertEqual(len(figure.axes[0].patches) > 0, True)
        self.assertEqual(len(figure.axes[0].lines), 1)
        self.assertLess(figure.axes[0].get_xlim()[0], np.log(120))
        self.assertGreater(figure.axes[0].get_xlim()[1], np.log(360))
        import matplotlib.pyplot as plt
        plt.close(figure)

    def test_single_ratio_plot_has_clear_axes(self):
        figure = plot_single_ratio_distribution(np.array([1.6, 2.0, 2.4, 3.0, 3.8]))
        self.assertEqual(len(figure.axes), 1)
        self.assertIn('ln(1 /', figure.axes[0].get_xlabel())
        self.assertEqual(figure.axes[0].get_ylabel(), 'Probability Density')
        self.assertEqual(len(figure.axes[0].lines), 1)
        import matplotlib.pyplot as plt
        plt.close(figure)


if __name__ == '__main__': unittest.main(verbosity=2)

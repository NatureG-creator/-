import copy
import unittest
from unittest.mock import patch

import numpy as np

from backend.apdl_geometry import normalise_options
from backend.apdl_surface_mapping import common_grid, map_surfaces, mapping_report


class SurfaceMappingTests(unittest.TestCase):
    def setUp(self):
        self.metadata = {
            'top': dict(shape=[5, 7], origin_x_mm=0., origin_y_mm=0., dx_mm=.5, dy_mm=.5),
            'bottom': dict(shape=[3, 4], origin_x_mm=.25, origin_y_mm=.25, dx_mm=.75, dy_mm=.75),
        }
        self.depths = {}
        for label, m in self.metadata.items():
            x = m['origin_x_mm'] + np.arange(m['shape'][1])*m['dx_mm']
            y = m['origin_y_mm'] + np.arange(m['shape'][0])*m['dy_mm']
            self.depths[label] = .1 + .1*x[None, :] + .2*y[:, None]
        self.options = normalise_options({'surface_grid_mode': 'common_xy'})

    def test_coarser_intersection_and_bilinear_plane_preserve_inputs(self):
        original = copy.deepcopy(self.metadata)
        arrays = {k: a.copy() for k, a in self.depths.items()}
        mapping = common_grid(self.metadata, self.options)
        self.assertEqual((mapping['dx_mm'], mapping['dy_mm']), (.75, .75))
        self.assertEqual(mapping['target_x_range_mm'], [.25, 2.5])
        self.assertEqual(mapping['target_y_range_mm'], [.25, 1.75])
        mapped = map_surfaces(self.depths, self.metadata, mapping)
        x = .25 + np.arange(4)*.75
        y = .25 + np.arange(3)*.75
        expected = .1 + .1*x[None, :] + .2*y[:, None]
        for a in mapped.values():
            np.testing.assert_allclose(a, expected, rtol=0, atol=2e-16)
        report = mapping_report(mapping, self.depths, mapped)
        self.assertFalse(report['extrapolation'])
        self.assertTrue(report['sources']['top']['cropped'])
        self.assertEqual(self.metadata, original)
        for k, a in self.depths.items():
            np.testing.assert_array_equal(a, arrays[k])

    def test_manual_spacing_trims_incomplete_edge(self):
        self.options.update(mapping_dx_mm=1., mapping_dy_mm=.5)
        mapping = common_grid(self.metadata, self.options)
        self.assertEqual(mapping['overlap_x_range_mm'], [.25, 2.5])
        self.assertEqual(mapping['target_x_range_mm'], [.25, 2.25])
        self.assertEqual((mapping['y_count'], mapping['x_count']), (4, 3))

    def test_no_area_overlap_and_insufficient_interval_rejected(self):
        for origin in (3., 4.):
            with self.subTest(origin=origin):
                self.metadata['bottom']['origin_x_mm'] = origin
                with self.assertRaisesRegex(ValueError, '共同覆盖'):
                    common_grid(self.metadata, self.options)
        self.metadata['bottom']['origin_x_mm'] = .25
        self.options['mapping_dx_mm'] = 3.
        with self.assertRaisesRegex(ValueError, '不足'):
            common_grid(self.metadata, self.options)

    def test_fine_grid_rejected_before_target_allocation(self):
        self.options.update(mapping_dx_mm=1e-6, mapping_dy_mm=1e-6)
        with patch('backend.apdl_surface_mapping.np.meshgrid', side_effect=AssertionError('allocated')):
            with self.assertRaisesRegex(ValueError, '网格超过上限'):
                common_grid(self.metadata, self.options)

    def test_frozen_mapping_never_extrapolates(self):
        mapping = common_grid(self.metadata, self.options)
        mapping['origin_x_mm'] = 0.
        with self.assertRaisesRegex(ValueError, '禁止外推'):
            map_surfaces(self.depths, self.metadata, mapping)

    def test_invalid_spacing_and_mode_rejected(self):
        for key in ('mapping_dx_mm', 'mapping_dy_mm'):
            for value in (0, -1, float('nan'), float('inf'), True, '0.5'):
                with self.subTest(key=key, value=value):
                    with self.assertRaises(ValueError):
                        normalise_options({key: value})
        with self.assertRaises(ValueError):
            normalise_options({'surface_grid_mode': 'guess'})

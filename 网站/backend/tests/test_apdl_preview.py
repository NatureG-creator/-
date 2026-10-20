import unittest
from unittest.mock import patch

import numpy as np

from backend.apdl_service import precheck_apdl


class ApdlPreviewTests(unittest.TestCase):
    def test_preview_preserves_edges_origin_and_array_alignment_without_changing_geometry(self):
        for ny, nx in ((83, 193), (3, 4)):
            with self.subTest(shape=(ny, nx)):
                x = -12.5 + np.arange(nx) * .025
                y = 31.2 + np.arange(ny) * .03
                depth = np.arange(ny * nx).reshape(ny, nx) * 1e-5
                geometry = dict(x=x, y=y, top_depth=depth.copy(), bottom_depth=depth * .2,
                                remaining=6-depth * 1.2, stats={}, warnings=[])
                original = {key: value.copy() for key, value in geometry.items() if isinstance(value, np.ndarray)}
                spec = dict(options={}, faces={}, run_mode='build', registration_confirmed=False,
                            registration_signature=None, reading_seconds=0)
                with patch('backend.apdl_service._prepare', return_value=(spec, None, geometry)), patch(
                        'backend.apdl_diagnostics.diagnostics_for_geometry', return_value={}):
                    preview = precheck_apdl(None, {})['preview']
                rows = np.linspace(0, ny-1, min(80, ny), dtype=int)
                cols = np.linspace(0, nx-1, min(80, nx), dtype=int)
                self.assertEqual(preview['x_mm'][0], x[0])
                self.assertEqual(preview['x_mm'][-1], x[-1])
                self.assertEqual(preview['y_mm'][0], y[0])
                self.assertEqual(preview['y_mm'][-1], y[-1])
                for key in ('top_depth', 'bottom_depth', 'remaining'):
                    np.testing.assert_array_equal(preview[key], geometry[key][np.ix_(rows, cols)])
                for key, value in original.items():
                    np.testing.assert_array_equal(geometry[key], value)

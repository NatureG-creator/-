import tempfile
import unittest
from pathlib import Path

import numpy as np

from backend.apdl_coordinates import (
    parse_coordinate_triplet,
    surface_depth,
    validate_coordinate_pair,
)


def write_triplet(folder, prefix, x, y, z):
    paths = []
    for suffix, values in (('X', x), ('Y', y), ('Z', z)):
        path = Path(folder) / f'{prefix}_{suffix}.txt'
        np.savetxt(path, np.asarray(values).reshape(-1), fmt='%.9g')
        paths.append(path)
    return paths


def temporary_folder():
    return tempfile.TemporaryDirectory()


class CoordinateParserTests(unittest.TestCase):
    def test_restores_regular_flattened_mesh_and_front_depth(self):
        with temporary_folder() as folder:
            x, y = np.meshgrid([0.0, 0.25, 0.5], [1.0, 1.25])
            z = np.array([[5.0, 4.75, 5.0], [4.5, 4.75, 5.0]])
            paths = write_triplet(folder, 'front', x, y, z)
            parsed = parse_coordinate_triplet(*paths)

            self.assertEqual(parsed['shape'], [2, 3])
            self.assertAlmostEqual(parsed['dx_mm'], 0.25)
            self.assertAlmostEqual(parsed['dy_mm'], 0.25)
            np.testing.assert_allclose(parsed['z_grid'], z)
            np.testing.assert_allclose(surface_depth(parsed, 'front'), z.max() - z)

    def test_back_depth_and_invalid_grid_are_rejected(self):
        with temporary_folder() as folder:
            x, y = np.meshgrid([0.0, 0.25], [0.0, 0.25])
            z = np.array([[0.2, 0.3], [0.25, 0.4]])
            paths = write_triplet(folder, 'back', x, y, z)
            parsed = parse_coordinate_triplet(*paths)
            np.testing.assert_allclose(surface_depth(parsed, 'back'), z - z.min())

            bad = Path(folder) / 'bad.txt'
            np.savetxt(bad, [0.0, 0.25, 0.5])
            with self.assertRaisesRegex(ValueError, '至少需要 4 个点'):
                parse_coordinate_triplet(paths[0], paths[1], bad)

    def test_duplicate_missing_and_nonfinite_coordinates_are_rejected(self):
        with temporary_folder() as folder:
            x, y = np.meshgrid([0.0, 0.25], [0.0, 0.25])
            z = np.ones_like(x)
            paths = write_triplet(folder, 'face', x, y, z)
            values = np.loadtxt(paths[0])
            values[1] = values[0]
            np.savetxt(paths[0], values)
            with self.assertRaisesRegex(ValueError, '重复|网格'):
                parse_coordinate_triplet(*paths)

            np.savetxt(paths[0], [0.0, 0.25, np.nan, 0.25])
            with self.assertRaisesRegex(ValueError, '有限|NaN'):
                parse_coordinate_triplet(*paths)

    def test_double_faces_must_share_xy_grid(self):
        with temporary_folder() as folder:
            x, y = np.meshgrid([0.0, 0.25], [0.0, 0.25])
            top = parse_coordinate_triplet(*write_triplet(folder, 'top', x, y, np.ones_like(x)))
            bottom = parse_coordinate_triplet(*write_triplet(folder, 'bottom', x + 0.01, y, np.zeros_like(x)))
            with self.assertRaisesRegex(ValueError, 'XY|坐标|一致'):
                validate_coordinate_pair(top, bottom)

            bottom = parse_coordinate_triplet(*write_triplet(folder, 'bottom2', x, y, np.zeros_like(x)))
            self.assertIsNone(validate_coordinate_pair(top, bottom))


if __name__ == '__main__':
    unittest.main()

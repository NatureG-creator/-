import unittest

from backend.apdl_joint_calibration import _neck_position, _weights


class ApdlJointCalibrationTests(unittest.TestCase):
    def test_weights_require_a_positive_component(self):
        self.assertEqual(_weights({'weights': {'force': 2, 'neck_position': 0, 'dic_field': 0}})['force'], 2.)
        with self.assertRaises(ValueError):
            _weights({'weights': {'force': 0, 'neck_position': 0, 'dic_field': 0}})

    def test_neck_position_falls_back_to_section_index(self):
        value = _neck_position({'section_index': 20}, {'options': {'tensile_direction': 'X', 'length_mm': 10, 'width_mm': 2, 'nx': 41}})
        self.assertAlmostEqual(value, 5.)


if __name__ == '__main__':
    unittest.main()

from pathlib import Path
import tempfile
import unittest
import numpy as np


class AnalysisTests(unittest.TestCase):
    def test_solver_control_echo_is_not_a_convergence_failure(self):
        from backend.apdl_analysis import diagnose_output
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'mapdl.out').write_text('TERMINATE ANALYSIS IF NOT CONVERGED . . .YES (EXIT)\n')
            report=diagnose_output(root)
            self.assertEqual(report['state'],'no_explicit_errors')
            self.assertEqual(report['evidence'],[])

    def test_diagnostics_preserve_evidence_and_line_numbers(self):
        from backend.apdl_analysis import diagnose_output
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'mapdl.out').write_text('start\n*** ERROR ***\nElement 124 has highly distorted shape.\nSOLUTION DID NOT CONVERGE\n')
            report = diagnose_output(root)
            self.assertEqual(report['state'], 'errors_found')
            self.assertEqual(report['evidence'][0]['line'], 2)
            self.assertIn('mesh', report['categories'])
            self.assertFalse(report['convergence_verified'])

    def test_comparison_uses_overlap_and_units_without_extrapolation(self):
        from backend.apdl_analysis import compare_curves
        sim = np.array([[0, 0], [1, 1000], [2, 2000]])
        result = compare_curves(sim, [[.0005, .5], [.0015, 1.5], [.003, 3]],
                                displacement_unit='m', force_unit='kN')
        self.assertEqual(result['overlap_mm'], [.5, 2.0])
        self.assertEqual(result['compared_points'], 2)
        self.assertAlmostEqual(result['rmse_N'], 0)
        self.assertEqual(result['outside_overlap_points'], 1)

    def test_rejects_repeated_displacement_and_no_overlap(self):
        from backend.apdl_analysis import compare_curves
        for trial in ([[0, 0], [0, 1]], [[3, 3], [4, 4]]):
            with self.subTest(trial=trial), self.assertRaises(ValueError):
                compare_curves([[0, 0], [1, 1]], trial)


if __name__ == '__main__':
    unittest.main()

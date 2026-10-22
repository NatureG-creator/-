from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from backend.apdl_outcome import explain_result
from backend.apdl_solver import run_mapdl


RECOVERED = '''*** ERROR ***
Element 10499 (type = 1, SOLID185) has become highly distorted.
*** LOAD STEP 1 SUBSTEP 39 NOT COMPLETED. CUM ITER = 75
*** BEGIN BISECTION NUMBER 2 NEW TIME INCREMENT=0.002
*** LOAD STEP 1 SUBSTEP 39 COMPLETED. CUM ITER = 77
*** TIME = 0.737222 TIME INC = 0.002
*** WARNING ***
Accumulated equivalent plastic strain value outside of bounds of
defined multilinear hardening table(s).
*** LOAD STEP 1 SUBSTEP 57 COMPLETED. CUM ITER = 124
*** TIME = 1.00000 TIME INC = 0.009
'''


class OutcomeTests(unittest.TestCase):
    def fixture(self, root, log=RECOVERED):
        (root/'mapdl.out').write_text(log)
        (root/'corrosion.rst').write_bytes(b'fixture only; not a verified RST')
        (root/'force_displacement.csv').write_text('0.5,5.5,100,-100,0.05,1\n1,11,200,-200,0.1,2\n')
        return dict(options=dict(target_displacement_mm=11), solver=dict(exit_code=1),
                    solve_state='failed', failure_stage='solver', error='exit code 1')

    def test_recovered_trial_error_with_full_loading_is_explained_not_erased(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            summary=self.fixture(root)
            (root/'corrosion0.err').write_text('*** ERROR ***\nElement 10499 has become highly distorted.\n')
            before=(root/'mapdl.out').read_bytes()
            report=explain_result(root,summary,'failed')
            self.assertTrue(report['loading_complete'])
            self.assertTrue(report['recovered_distortion'])
            self.assertEqual(report['final_displacement_mm'],11)
            self.assertEqual(report['last_converged']['substep'],57)
            self.assertEqual(report['outcome'],'completed_with_warnings')
            self.assertEqual(report['original_state'],'failed')
            self.assertTrue(any(i['category']=='material' for i in report['issues']))
            self.assertEqual((root/'mapdl.out').read_bytes(),before)

    def test_not_completed_is_not_a_converged_record(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            summary=self.fixture(root,'*** LOAD STEP 1 SUBSTEP 57 NOT COMPLETED.\n*** TIME = 1.0\n')
            report=explain_result(root,summary)
            self.assertFalse(report['loading_complete'])
            self.assertIsNone(report['last_converged'])

    def test_curve_alone_or_run_completed_banner_does_not_prove_completion(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            summary=self.fixture(root,'RUN COMPLETED\n')
            self.assertFalse(explain_result(root,summary)['loading_complete'])

    def test_partial_or_invalid_curve_does_not_recover_error(self):
        for text in ('0.5,5.5,100,-100,.05,1\n', '1,11,NaN,0,0,0\n', 'time,ux,F,F,e,s\n', '1,9,100,-100,.05,1\n'):
            with self.subTest(text=text),tempfile.TemporaryDirectory() as directory:
                root=Path(directory)
                summary=self.fixture(root)
                (root/'force_displacement.csv').write_text(text)
                report=explain_result(root,summary)
                self.assertFalse(report['loading_complete'])
                self.assertFalse(report['recovered_distortion'])

    def test_unknown_fatal_error_after_final_convergence_remains_unresolved(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            summary=self.fixture(root,RECOVERED+'*** ERROR ***\nCannot write output database.\n')
            report=explain_result(root,summary)
            self.assertTrue(report['loading_complete'])
            self.assertFalse(report['recovered_distortion'])
            self.assertEqual(report['outcome'],'needs_review')

    def test_self_check_error_and_abnormal_exit_are_not_recovered(self):
        for side in ('APDL_SELF_CHECK_FAILED,1\n','*** ERROR ***\nLicense checkout failed\n'):
            with self.subTest(side=side),tempfile.TemporaryDirectory() as directory:
                root=Path(directory)
                summary=self.fixture(root)
                (root/'mesh_quality_report.txt').write_text(side)
                self.assertFalse(explain_result(root,summary)['recovered_distortion'])
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            summary=self.fixture(root)
            summary['solver']['exit_code']=9
            self.assertFalse(explain_result(root,summary)['recovered_distortion'])

    def test_late_error_is_retained_after_many_material_warnings(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            prefix=('*** WARNING ***\nPlastic strain outside bounds of hardening table.\n'*200)
            summary=self.fixture(root,prefix+RECOVERED)
            report=explain_result(root,summary)
            distortion=next(i for i in report['issues'] if i['category']=='distortion')
            self.assertGreater(distortion['evidence']['line'],400)
            self.assertTrue(report['recovered_distortion'])

    def test_changed_logs_invalidate_scan_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            summary=self.fixture(root)
            self.assertTrue(explain_result(root,summary)['recovered_distortion'])
            with (root/'mapdl.out').open('a') as stream:
                stream.write('*** ERROR ***\nOutput failed.\n')
            self.assertFalse(explain_result(root,summary)['recovered_distortion'])

    def test_early_constraint_and_performance_warnings_have_specific_explanations(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            summary=self.fixture(root)
            (root/'mesh_quality_report.txt').write_text('*** WARNING ***\nNo constraints have been defined using the D command.\n')
            with (root/'mapdl.out').open('a') as stream:
                stream.write('*** WARNING ***\nDuring this session the elapsed time exceeds the CPU time by 172%.\n')
            report=explain_result(root,summary)
            self.assertEqual({'constraints','performance'}-set(i['category'] for i in report['issues']),set())
            self.assertIn('mesh_quality_report.txt',report['diagnostic_files'])

    def test_empty_rst_and_build_failure_are_not_reported_as_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            summary=self.fixture(root)
            (root/'corrosion.rst').write_bytes(b'')
            self.assertFalse(explain_result(root,summary)['loading_complete'])
        with tempfile.TemporaryDirectory() as directory:
            report=explain_result(Path(directory),dict(run_mode='build',build_state='failed',error='bad geometry'))
            self.assertEqual(report['outcome'],'incomplete')

    def test_material_limit_and_first_exceedance_are_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            summary=self.fixture(root)
            summary['options'].update(material_model='multilinear_iso',plastic_curve=[[0,332],[.137798,621]])
            (root/'material_coverage_history.csv').write_text('.2,.1,7,1,2,3\n.395,.142155,7,1,2,3\n1,1.457157,8,2,3,4\n')
            m=explain_result(root,summary)['material_screening']
            self.assertEqual(m['limit'],.137798)
            self.assertEqual(m['first_time'],.395)
            self.assertEqual(m['first_element'],7)
            self.assertAlmostEqual(m['maximum'],1.457157)

    def test_process_continues_only_for_confirmed_recovered_standard_solve(self):
        for allowed,extra in ((True,''),(False,''),(True,'*** ERROR ***\nUnknown error.\n')):
            with self.subTest(allowed=allowed,extra=extra),tempfile.TemporaryDirectory() as directory:
                root=Path(directory)
                (root/'main.inp').write_text('/SOLU')
                process=Mock(pid=999999999)
                process.record={}
                process.wait.return_value=1
                process.close.return_value={'state':'stopped','verified_empty':True}
                def launch(*args,**kwargs):
                    self.fixture(root,RECOVERED+extra)
                    return process
                cap={'available':True,'executable':'C:/ANSYS/ansys.exe','warnings':[]}
                with patch('backend.apdl_solver.mapdl_capabilities',return_value=cap),patch('backend.apdl_solver.launch_owned',side_effect=launch):
                    if allowed and not extra:
                        report=run_mapdl(root,dict(cores=2,timeout_seconds=5,target_displacement_mm=11),allow_recovered=True)
                        self.assertEqual(report['state'],'process_finished')
                        self.assertEqual(report['exit_code'],1)
                    else:
                        with self.assertRaises(RuntimeError):
                            run_mapdl(root,dict(cores=2,timeout_seconds=5,target_displacement_mm=11),allow_recovered=allowed)

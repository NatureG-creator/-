import tempfile
import unittest
from pathlib import Path

import numpy as np
from scipy.io import savemat


class ApdlSourceTests(unittest.TestCase):
    def test_native_plot_failure_does_not_change_successful_solve(self):
        from backend.apdl_service import run_apdl_job
        from backend.apdl_geometry import normalise_options
        from unittest.mock import patch
        for plot_result in ({'state': 'failed', 'error': 'graphics unavailable', 'plots': []}, OSError('cannot export')):
            with self.subTest(plot_result=plot_result), tempfile.TemporaryDirectory() as folder:
                spec = {'faces': {}, 'options': normalise_options({'corrosion_mode': 'flat'}), 'run_mode': 'solve'}
                kwargs = {'side_effect': plot_result} if isinstance(plot_result, Exception) else {'return_value': plot_result}
                with patch('backend.apdl_solver.run_mapdl', return_value={'state': 'process_finished'}), \
                     patch('backend.apdl_solver.read_tension_results', return_value={'solve_state': 'solved', 'warnings': [], 'files': []}), \
                     patch('backend.apdl_plots.render_result_contours', **kwargs) as plotting:
                    result = run_apdl_job(spec, Path(folder))
                self.assertEqual(result['solve_state'], 'solved')
                self.assertEqual(result['results']['contour_plots']['state'], 'failed')
                self.assertTrue(result['results']['warnings'])
                plotting.assert_called_once()

    def test_solver_failure_preserves_built_inputs_and_failed_summary(self):
        from backend.apdl_service import run_apdl_job
        from backend.apdl_geometry import normalise_options
        from unittest.mock import patch
        import json
        with tempfile.TemporaryDirectory() as folder:
            job=Path(folder)
            spec={'faces':{},'options':normalise_options({'corrosion_mode':'flat'}),'run_mode':'solve'}
            with patch('backend.apdl_solver.run_mapdl',side_effect=RuntimeError('solver license test failure')):
                with self.assertRaisesRegex(RuntimeError,'license'):
                    run_apdl_job(spec,job)
            summary=json.loads((job/'outputs'/'summary.json').read_text(encoding='utf-8'))
            self.assertEqual(summary['solve_state'],'failed')
            self.assertIn('license',summary['error'])
            self.assertGreaterEqual(summary['timing']['solver_seconds'],0)
            self.assertEqual(summary['stage_states']['solver'],'failed')
            self.assertEqual(summary['failure_stage'],'solver')
            self.assertTrue((job/'outputs'/'main.inp').is_file())

    def test_postprocess_failure_keeps_execution_record_and_all_elapsed_stages(self):
        from backend.apdl_service import run_apdl_job
        from backend.apdl_geometry import normalise_options
        from unittest.mock import patch
        import json
        with tempfile.TemporaryDirectory() as folder:
            job=Path(folder)
            spec={'faces':{},'options':normalise_options({'corrosion_mode':'flat'}),'run_mode':'solve'}
            execution={'state':'completed','exit_code':0,'elapsed_seconds':1.5}
            def solver(output,options,progress=None):
                (output/'mapdl_execution.json').write_text(json.dumps(execution),encoding='utf-8')
                return execution
            with patch('backend.apdl_solver.run_mapdl',side_effect=solver), patch(
                    'backend.apdl_solver.read_tension_results',side_effect=ValueError('节点坐标不一致')) as reader:
                with self.assertRaisesRegex(ValueError,'节点'):
                    run_apdl_job(spec,job)
            summary=json.loads((job/'outputs'/'summary.json').read_text(encoding='utf-8'))
            self.assertEqual(summary['failure_stage'],'postprocess')
            self.assertEqual(summary['stage_states']['solver'],'completed')
            self.assertEqual(summary['stage_states']['postprocess'],'failed')
            self.assertGreaterEqual(summary['timing']['postprocess_seconds'],0)
            self.assertEqual(summary['solver'],execution)
            self.assertEqual(summary['execution_record'],'mapdl_execution.json')
            self.assertEqual(reader.call_args.kwargs['expected_nodes'].shape[1],4)

    def test_geometry_failure_preserves_elapsed_time_without_claiming_solver_failed(self):
        from backend.apdl_service import run_apdl_job
        from unittest.mock import patch
        import json
        with tempfile.TemporaryDirectory() as folder:
            job=Path(folder)
            with patch('backend.apdl_geometry.build_geometry',side_effect=ValueError('几何无效')):
                with self.assertRaisesRegex(ValueError,'几何'):
                    run_apdl_job({'faces':{},'options':{},'run_mode':'solve'},job)
            summary=json.loads((job/'outputs'/'summary.json').read_text(encoding='utf-8'))
            self.assertEqual(summary['build_state'],'failed')
            self.assertEqual(summary['solve_state'],'not_started')
            self.assertEqual(summary['failure_stage'],'geometry')
            self.assertGreaterEqual(summary['timing']['geometry_seconds'],0)
            self.assertNotIn('solver_seconds',summary['timing'])

    def test_failure_persistence_does_not_hide_original_postprocess_error(self):
        from backend.apdl_service import run_apdl_job
        from backend.apdl_geometry import normalise_options
        from backend.runner import _atomic_json
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as folder:
            spec={'faces':{},'options':normalise_options({'corrosion_mode':'flat'}),'run_mode':'solve'}
            def write(path,value):
                if value.get('stage_states',{}).get('postprocess')=='failed':
                    raise PermissionError('test summary write denied')
                return _atomic_json(path,value)
            with patch('backend.apdl_service._atomic_json',side_effect=write), patch(
                    'backend.apdl_solver.run_mapdl',return_value={'state':'process_finished'}), patch(
                    'backend.apdl_solver.read_tension_results',side_effect=ValueError('original node failure')):
                with self.assertRaisesRegex(ValueError,'original node failure') as caught:
                    run_apdl_job(spec,Path(folder))
            self.assertTrue(any('write denied' in note for note in caught.exception.__notes__))

    def test_original_preset_keeps_all_49_plastic_points(self):
        from backend.apdl_presets import get_presets
        from backend.apdl_geometry import normalise_options
        preset=get_presets()[1]
        options=normalise_options(preset['options'])
        self.assertEqual(len(options['plastic_curve']),49)
        self.assertEqual(options['plastic_curve'][0],[0,332.87])
        self.assertEqual(options['plastic_curve'][-1],[.137798,621.16])
        self.assertEqual(options['boundary_mode'],'legacy_recommended')

    def test_original_double_assembly_is_equivalent_up_to_translation(self):
        from backend.apdl_service import read_face
        from backend.apdl_geometry import build_geometry
        with tempfile.TemporaryDirectory() as folder:
            z=np.array([[.2,-.1,.3],[-.2,.1,0]])
            f=np.array([[.1,.2,-.2],[0,-.1,.1]])
            faces=[]
            for label,array in [('z',z),('f',f)]:
                path=Path(folder)/(label+'.csv')
                np.savetxt(path,array,delimiter=',')
                faces.append(read_face(path,'measured',{'value_mode':'height','reference_mode':'maximum','dx_mm':.3,'dy_mm':.3})[0])
            g=build_geometry(*faces,{'corrosion_mode':'double_independent','thickness_mm':6})
            shift=6-z.max()
            original_bottom=-f+z.max()-6+f.max()
            np.testing.assert_allclose(6-g['top_depth'],z+shift,atol=1e-14)
            np.testing.assert_allclose(g['bottom_depth'],original_bottom+shift,atol=1e-14)

    def test_original_github_maximum_reference_after_explicit_crop(self):
        from backend.apdl_service import read_face
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'height.csv'
            raw=np.array([[99,1,2,3,99],[99,4,5,6,99]],dtype=float)
            np.savetxt(path,raw,delimiter=',')
            depth,meta=read_face(path,'measured',{'value_mode':'height','reference_mode':'maximum',
                'center_crop_columns':3,'dx_mm':.3,'dy_mm':.3})
            np.testing.assert_array_equal(depth,6-raw[:,1:4])
            self.assertEqual(meta['original_shape'],[2,5])
            self.assertEqual(meta['crop_columns_zero_based'],[1,4])
            self.assertEqual(meta['reference_height'],6)

    def test_non_square_mat_orientation_and_units(self):
        from backend.apdl_service import read_face
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'face.mat'
            raw=np.array([[0,100,200],[300,400,500]],dtype=float)
            savemat(path,{'Z_filled':raw})
            depth,meta=read_face(path,'measured',{'unit':'um','layout':'yx','value_mode':'depth','dx_mm':.2,'dy_mm':.3})
            np.testing.assert_array_equal(depth,raw/1000)
            self.assertEqual(meta['shape'],[2,3])
            self.assertEqual(meta['dx_mm'],.2)
            self.assertEqual(meta['dy_mm'],.3)

    def test_mat_two_variables_require_explicit_selection(self):
        from backend.apdl_service import read_face
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'both.mat'
            savemat(path,{'Z_filled':np.zeros((2,3)),'F_filled':np.ones((2,3))})
            with self.assertRaisesRegex(ValueError,'变量'):
                read_face(path,'measured',{'dx_mm':.2,'dy_mm':.3})

    def test_height_reference_transpose_and_flip_are_explicit(self):
        from backend.apdl_service import read_face
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'height.csv'
            raw=np.array([[0,-.1,-.2],[-.3,-.4,-.5]])
            np.savetxt(path,raw,delimiter=',')
            depth,meta=read_face(path,'measured',{'value_mode':'height','reference_height':0,'unit':'mm','layout':'yx','dx_mm':.2,'dy_mm':.3,'transpose':True,'flip_x':True})
            np.testing.assert_array_equal(depth,(-raw).T[:,::-1])
            self.assertEqual((meta['dx_mm'],meta['dy_mm']),(.3,.2))
            with self.assertRaisesRegex(ValueError,'负'):
                read_face(path,'measured',{'value_mode':'depth','unit':'mm','dx_mm':.2,'dy_mm':.3})

    def test_simulation_inherits_geometry_and_row_x_layout(self):
        from backend.apdl_service import read_face
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'state.npz'
            state=np.zeros((2,3,5),dtype=np.uint8)
            state[:,:,2:]=1
            state[0,1,1]=1
            np.savez(path,perfect_a=state)
            depth,meta=read_face(path,'simulation',{}, {'space_z_um':25,'space_xy_um':40})
            self.assertEqual(depth.shape,(3,2))
            self.assertEqual(depth[1,0],.025)
            self.assertEqual(depth[0,0],.05)
            self.assertEqual(meta['dx_mm'],.04)
            self.assertEqual(meta['value_mode'],'depth')

    def test_missing_upload_spacing_and_nonfinite_are_rejected(self):
        from backend.apdl_service import read_face
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'face.csv'
            np.savetxt(path,np.ones((2,3)),delimiter=',')
            with self.assertRaisesRegex(ValueError,'间距'):
                read_face(path,'measured',{})
            np.savetxt(path,np.array([[1,np.nan],[1,1]]),delimiter=',')
            with self.assertRaisesRegex(ValueError,'有限'):
                read_face(path,'measured',{'dx_mm':.2,'dy_mm':.3})


if __name__=='__main__':
    unittest.main()

import tempfile
import unittest
from pathlib import Path

import numpy as np
from scipy.io import savemat


class ApdlSourceTests(unittest.TestCase):
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
            self.assertTrue((job/'outputs'/'main.inp').is_file())

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

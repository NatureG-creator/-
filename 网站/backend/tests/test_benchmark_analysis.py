import tempfile
import unittest
from pathlib import Path
import numpy as np
from backend.config import default_simulation_config
from backend.benchmark_analysis import physical_comparison

class PhysicalComparisonTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.root=Path(self.folder.name)
        self.config=default_simulation_config()
        self.config['GEOMETRY_CONFIG']['space_z_um']=25
    def tearDown(self):
        self.folder.cleanup()
    def save(self,name,a,objv=None):
        path=self.root/name
        np.savez(path,a=a,objv=np.zeros(4) if objv is None else objv)
        return path
    def test_true_surface_difference_and_undefined_pit_metrics(self):
        a=np.ones((5,6,5)); b=a.copy(); b[0,0,0]=0
        result=physical_comparison(self.save('a.npz',a),self.save('b.npz',b),self.config)
        self.assertEqual(result['surface_depth']['max_abs_diff_um'],25)
        self.assertEqual(result['surface_depth']['mismatch_count'],1)
        self.assertAlmostEqual(result['surface_depth']['rmse_um'],25/np.sqrt(30))
        self.assertIsNone(result['metrics']['sigma_log_depth']['reference'])
        self.assertTrue(result['notes'])
    def test_reject_shape_mismatch(self):
        with self.assertRaises(ValueError):
            physical_comparison(self.save('a.npz',np.ones((5,6,5))),self.save('b.npz',np.ones((4,6,5))),self.config)
    def test_population_uses_same_reference_index(self):
        a=np.ones((2,5,6,5)); b=a.copy(); b[0,:,:,0]=0
        left=np.array([[0,0,0,0,0,0],[5,5,5,5,5,5]])
        right=left[::-1]
        result=physical_comparison(self.save('a.npz',a,left),self.save('b.npz',b,right),self.config)
        self.assertEqual(result['reference_best_index'],0)
        self.assertEqual(result['candidate_best_index'],1)
        self.assertEqual(result['comparison_index'],0)
        self.assertEqual(result['surface_depth']['mismatch_count'],30)

    def test_optional_plot_and_parameters(self):
        a=np.ones((5,6,5)); path=self.root/'ref.npz'; other=self.root/'candidate.npz'
        np.savez(path,a=a,objv=np.zeros(4),perfect_parameter=np.arange(10,dtype=float))
        np.savez(other,a=a,objv=np.zeros(4),perfect_parameter=np.arange(10,dtype=float)+1)
        plot=self.root/'surface.png'
        result=physical_comparison(path,other,self.config,plot)
        self.assertEqual(result['plot_file'],'surface.png')
        self.assertEqual(plot.read_bytes()[:8],b'\x89PNG\r\n\x1a\n')
        self.assertEqual(result['parameters']['p_uniform_base']['delta'],1)

"""原MATLAB导出合同：防止负参考、错误六值及算法来源变化。"""
import sys
import unittest
import tempfile
import hashlib
from pathlib import Path
import numpy as np
from scipy.io import savemat

SHARED=Path(__file__).resolve().parents[1]/'09_共享模拟内核与指标'
sys.path.insert(0,str(SHARED))
from original_target_contract import validate_original_target,load_original_target
from native_metric_client import matlab_numeric_config


class OriginalTargetContractTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source=Path(self.temp.name)/'source.m'
        self.source.write_text('original algorithm',encoding='utf-8')
        self.depth=np.arange(12.,dtype=float).reshape(3,4)+4
        ld=np.log([5.,8.]);lr=np.log([2.,3.])
        self.mat=dict(extraction_method='original_matlab_positive_depth_v2',calibration_ready=True,
            reference_metadata=dict(physical_reference_verified=True),
            original_config=dict(preprocessing=dict(grid_resolution_mm=.3,main_gaussian_sigma=2.),
                pit_detection=dict(min_prominence=.001,min_distance=15,neighborhood=np.array([12,12]),edge_margin=1),
                watershed=dict(threshold=.3,gaussian_sigma=.5)),
            depth_um=self.depth.copy(),processed_depth_um=self.depth.copy(),valid_mask=np.ones((3,4)),
            uniform_depth_um=4.,spacing_um=300.,log_depth=ld,log_ratio=lr,
            target_data=np.array([self.depth.mean(),(self.depth-4).mean(),lr.mean(),ld.mean(),lr.std(ddof=1),ld.std(ddof=1)]),
            source_provenance=dict(source_type='measured_pointcloud'),
            original_source_paths=[str(self.source)],
            original_source_sha256=[hashlib.sha256(self.source.read_bytes()).hexdigest()])

    def test_valid_contract(self):
        validate_original_target(self.mat)

    def test_old_signed_target_cannot_mix_with_new_rule(self):
        self.mat['extraction_method']='original_matlab_v1'
        with self.assertRaisesRegex(ValueError,'v2'):
            validate_original_target(self.mat)

    def test_negative_raw_surface_cannot_be_hidden_by_smoothing(self):
        self.mat['depth_um'][0,0]=-1.
        with self.assertRaisesRegex(ValueError,'负'):
            validate_original_target(self.mat)

    def test_valid_mat_roundtrip_without_reextracting(self):
        # 仅测试序列化合同的合成矩阵，非真实校准目标。
        self.mat['original_config']['reference']=dict(flat_height_ratio=.2,flat_column_count=200,corrosion_column_count=168)
        self.mat.update(pit_depth_um=np.array([5.,8.]),pit_diameter_um=np.array([10.,24.]),
            pit_centers_rc_matlab=np.array([[1,1],[2,2]]),peaks_rc_matlab=np.array([[1,1],[2,2]]),
            pit_count=2,pit_density_per_mm2=1.,max_depth_um=15.,labels=np.zeros((3,4)),
            analysis_config={},depth_quantiles_um=np.array([4,6,8,10,15]),negative_fraction=0.,
            raw_min_depth_um=4.,reference_metadata=dict(depth_unit='um',test_fixture=True,physical_reference_verified=True))
        path=Path(self.temp.name)/'serialization_fixture.mat'
        savemat(path,self.mat,long_field_names=True)
        result=load_original_target(path)
        np.testing.assert_array_equal(result['vector'],self.mat['target_data'])
        np.testing.assert_array_equal(result['raw_depth_um'],self.depth)
        self.assertNotIn('python_crosscheck_vector',result)

    def test_exported_matlab_config_uses_double_numbers(self):
        raw=dict(pit=dict(distance=15,neighborhood=np.array([12,12],dtype=np.int64)),invert=True,root='D:/original')
        converted=matlab_numeric_config(raw)
        self.assertIsInstance(converted['pit']['distance'],float)
        self.assertEqual(converted['pit']['neighborhood'].dtype,np.float64)
        self.assertEqual(converted['root'],raw['root'])
        self.assertEqual(raw['pit']['neighborhood'].dtype,np.int64)

    def test_negative_uniform_rejected_without_abs(self):
        self.mat['uniform_depth_um']=-4.
        with self.assertRaisesRegex(ValueError,'均匀'):
            validate_original_target(self.mat)

    def test_not_ready_rejected(self):
        self.mat['calibration_ready']=False
        with self.assertRaisesRegex(ValueError,'校准'):
            validate_original_target(self.mat)

    def test_relative_height_target_cannot_be_used_as_total_depth(self):
        self.mat['extraction_method']='original_matlab_height_relative_v3'
        self.mat['target_data'][0]=np.nan
        self.mat['calibration_ready']=False
        with self.assertRaisesRegex(ValueError,'相对深度'):
            validate_original_target(self.mat)

    def test_old_ready_flag_does_not_prove_physical_reference(self):
        self.mat['reference_metadata']['physical_reference_verified']=False
        with self.assertRaisesRegex(ValueError,'物理确认'):
            validate_original_target(self.mat)

    def test_wrong_metric_order_rejected(self):
        self.mat['target_data'][0],self.mat['target_data'][1]=self.mat['target_data'][1],self.mat['target_data'][0]
        with self.assertRaisesRegex(ValueError,'六'):
            validate_original_target(self.mat)

    def test_algorithm_change_rejected(self):
        self.source.write_text('changed algorithm',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'来源'):
            validate_original_target(self.mat)

    def test_config_change_rejected(self):
        self.mat['original_config']['preprocessing']['grid_resolution_mm']=.2
        with self.assertRaisesRegex(ValueError,'网格'):
            validate_original_target(self.mat)

    def test_zero_or_one_pit_rejected(self):
        self.mat['log_depth']=self.mat['log_depth'][:1]
        with self.assertRaises(ValueError):
            validate_original_target(self.mat)

if __name__=='__main__':
    unittest.main(verbosity=2)

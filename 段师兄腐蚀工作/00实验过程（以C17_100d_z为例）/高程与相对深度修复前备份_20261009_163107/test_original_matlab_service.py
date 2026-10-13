"""真实MATLAB服务测试，合成深度只作接口核验，不冒充实测校准。"""
import sys
import tempfile
import unittest
from pathlib import Path
import numpy as np
from scipy.io import loadmat

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'09_共享模拟内核与指标'))
from native_metric_client import use_matlab_metrics
from calibration_bridge import _load_target
from unified_config import RUN_INPUTS,ANALYSIS_CONFIG


class OriginalMatlabServiceTests(unittest.TestCase):
    def test_actual_service_uses_original_and_is_repeatable(self):
        pointer=ROOT/'01_实测目标接口/实测目标/latest_original_target.txt'
        mat=loadmat(pointer.read_text(encoding='utf-8-sig'),simplify_cells=True)
        y,x=np.mgrid[1:41,1:51]
        synthetic=100+50*np.exp(-((x-15)**2+(y-12)**2)/35)+80*np.exp(-((x-35)**2+(y-28)**2)/50)
        with tempfile.TemporaryDirectory() as tmp:
            with use_matlab_metrics(RUN_INPUTS['matlab_executable'],Path(tmp)/'private_service',mat['original_config']) as client:
                first=client.extract(synthetic,300.,ANALYSIS_CONFIG,np.ones(synthetic.shape,bool))
                second=client.extract(synthetic,300.,ANALYSIS_CONFIG,np.ones(synthetic.shape,bool))
                self.assertEqual(first['extraction_method'],'original_matlab_positive_depth_v2')
                self.assertGreaterEqual(first['pit_count'],2)
                for key in ('vector','log_depth','log_ratio','processed_depth_um','peaks_rc'):
                    np.testing.assert_array_equal(first[key],second[key])
                self.assertIsNone(client.process.poll())
            self.assertIsNotNone(client.process.poll())

    def test_real_negative_reference_is_rejected(self):
        pointer=ROOT/'01_实测目标接口/实测目标/latest_original_target.txt'
        path=pointer.read_text(encoding='utf-8-sig')
        mat=loadmat(path,simplify_cells=True)
        if mat['calibration_ready']:
            self.skipTest('当前已重新导出可校准的真实目标。')
        with self.assertRaisesRegex(ValueError,'校准'):
            _load_target(path)

    def test_real_positive_target_reextract_matches_export(self):
        pointer=ROOT/'01_实测目标接口/实测目标/latest_original_target.txt'
        path=pointer.read_text(encoding='utf-8-sig').strip()
        target=_load_target(path)
        with tempfile.TemporaryDirectory() as tmp:
            with use_matlab_metrics(RUN_INPUTS['matlab_executable'],Path(tmp)/'c17_check',target['original_config']) as client:
                actual=client.extract(target['raw_depth_um'],300.,ANALYSIS_CONFIG,
                    np.ones(target['raw_depth_um'].shape,bool))
                for key in ('vector','log_depth','log_ratio','processed_depth_um'):
                    np.testing.assert_allclose(actual[key],target[key],rtol=1e-10,atol=1e-9)
                for key in ('depth_um','diameter_um'):
                    np.testing.assert_allclose([p[key] for p in actual['pits']],
                        [p[key] for p in target['pits']],rtol=1e-10,atol=1e-9)
                np.testing.assert_array_equal(actual['peaks_rc'],target['peaks_rc'])
                print('C17_NATIVE_VECTOR='+repr(actual['vector'].tolist()))

if __name__=='__main__':
    unittest.main(verbosity=2)

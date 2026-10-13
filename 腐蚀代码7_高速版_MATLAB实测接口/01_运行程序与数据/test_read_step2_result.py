"""测试 10_read_step2_result.py 的基本读取能力。"""

from pathlib import Path

import numpy as np

from importlib.util import module_from_spec, spec_from_file_location


ROOT = Path(__file__).resolve().parent
MODULE_PATH = ROOT / "10_read_step2_result.py"
SPEC = spec_from_file_location("read_step2_result", MODULE_PATH)
MODULE = module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_load_result_fields_and_shapes():
    """应读取结果字段，并保留关键数组形状。"""
    result_path = ROOT / "step2_stage_moni_result.npz"
    result = MODULE.load_result(result_path)

    assert "perfect_result_sd" in result
    assert "perfect_parameter_sd" in result
    assert result["perfect_result_sd"].shape == (1, 4)
    assert result["perfect_parameter_sd"].shape == (1, 10)
    assert result["perfect_a"].shape == (100, 100, 101)


def test_weighted_error_matches_saved_result():
    """四项误差按 [0.1, 0.3, 0.2, 0.4] 加权应得到 0.0342。"""
    result = MODULE.load_result(ROOT / "step2_stage_moni_result.npz")
    weighted_error = MODULE.calculate_weighted_error(result["perfect_result_sd"])

    assert np.isclose(weighted_error, 0.0342, atol=1e-12)

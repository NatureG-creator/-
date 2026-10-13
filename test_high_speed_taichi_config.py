"""The high-speed entry must follow the unified Taichi settings."""

from optimization_config import HIGH_SPEED_CONFIG
from unified_config import TAICHI_CONFIG


def test_high_speed_taichi_settings_follow_unified_config():
    assert HIGH_SPEED_CONFIG["use_taichi"] == TAICHI_CONFIG["use_taichi"]
    assert HIGH_SPEED_CONFIG["taichi_arch"] == TAICHI_CONFIG["arch"]
    assert HIGH_SPEED_CONFIG["allow_taichi_parallel"] == TAICHI_CONFIG["allow_taichi_parallel"]
    assert HIGH_SPEED_CONFIG["verbose"] == TAICHI_CONFIG["verbose"]

"""高速入口的兼容映射；Taichi 设置统一在 unified_config.py 修改。"""

from unified_config import TAICHI_CONFIG

HIGH_SPEED_CONFIG = {
    "use_taichi": TAICHI_CONFIG["use_taichi"],
    "taichi_arch": TAICHI_CONFIG["arch"],
    "allow_taichi_parallel": TAICHI_CONFIG["allow_taichi_parallel"],
    "verbose": TAICHI_CONFIG["verbose"],
}

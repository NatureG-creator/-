"""仅供第二步高速入口使用；模型尺寸、目标数据和 GA 参数仍在 unified_config.py。"""

HIGH_SPEED_CONFIG = {
    # False：NumPy/SciPy + Processes，启用仅回传误差优化，便于对照原 Python 数值。
    # True：启用原 Taichi 边界内核及缓冲区复用；其原有 float32/原子更新差异仍存在。
    "use_taichi": False,
    "taichi_arch": "cpu",  # Taichi 后端：cpu 或 gpu，仅 use_taichi=True 时生效。
    "allow_taichi_parallel": False,  # 同开 Taichi 和进程池可能竞争 CPU，默认关闭。
    "verbose": True,  # 显示阶段、代数和约 5% 一次的个体/CA 进度。
}

# Build Note — 独立点云与 MAT

| Rung | Feature | Acceptance check | Tier | Status |
|------|---------|------------------|------|--------|
| F0 | MAT上传→任务→单变量MAT与点云 | python -m unittest backend.tests.test_surface_generation.SurfaceGenerationTests.test_mat_job_spine | MUST | passed |
| F1 | 尺寸裁剪、方向、精确重采样 | python -m unittest backend.tests.test_surface_generation | MUST | passed |
| F2 | XYZ/NPZ/源模拟、双面、预检 | python -m unittest backend.tests.test_surface_generation | MUST | passed |
| F3 | 独立页面与结果展示 | node --test frontend/tests/surface_generation.test.mjs | MUST | pending |
| F4 | 8560真实验收、GitHub及快捷方式 | python scripts/verify_surface_generation.py | MUST | pending |

## Run record
F0：命令退出0；真实worker生成单变量double MAT、CSV/XYZ和ZIP；回读逐值相等。无占位输出。
F1：6项测试退出0；检查50mm子矩阵逐值相等、精确插值线性场、Y方向、来源不足、单位及方向。一次测试改为浮点单位换算容差。
F2：11项测试退出0；实数NPZ阶段与轴转换、冻结模拟几何、XYZ单位/重复点/缺失点及双面分别输出均覆盖。预检复用生成算法，无额外状态写入。

## Deferred
无需求内功能延后。

## Blockers
无。

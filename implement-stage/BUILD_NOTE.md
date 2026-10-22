# Build Note — 独立点云与 MAT

| Rung | Feature | Acceptance check | Tier | Status |
|------|---------|------------------|------|--------|
| F0 | MAT上传→任务→单变量MAT与点云 | python -m unittest backend.tests.test_surface_generation.SurfaceGenerationTests.test_mat_job_spine | MUST | passed |
| F1 | 尺寸裁剪、方向、精确重采样 | python -m unittest backend.tests.test_surface_generation | MUST | pending |
| F2 | XYZ/NPZ/源模拟、双面、预检 | python -m unittest backend.tests.test_surface_generation | MUST | pending |
| F3 | 独立页面与结果展示 | node --test frontend/tests/surface_generation.test.mjs | MUST | pending |
| F4 | 8560真实验收、GitHub及快捷方式 | python scripts/verify_surface_generation.py | MUST | pending |

## Run record
F0：命令退出0；真实worker生成单变量double MAT、CSV/XYZ和ZIP；回读逐值相等。无占位输出。

## Deferred
无需求内功能延后。

## Blockers
无。

# Build Note — 独立点云与 MAT

## 影响结果含义的约定
默认只裁剪原矩阵节点，不把实际189.3mm来源拉伸成190mm；精确尺寸需显式选择插值。XYZ先线性网格化（重复XY取Z均值），结果明确记录插值，缺失格默认拒绝。外部MAT/XYZ默认mm与0.3mm间距，可编辑并预检。NPZ使用原模拟元胞尺寸、首金属层深度规则；已完成模拟指定阶段时使用a_sd历史，perfect_a仅代表最终快照。转置交换XY物理坐标和间距。双面独立输出、无自动配准；逐面尺寸与偏移可覆盖公共设置。详见ASSUMPTIONS.md。

| Rung | Feature | Acceptance check | Tier | Status |
|------|---------|------------------|------|--------|
| F0 | MAT上传→任务→单变量MAT与点云 | python -m unittest backend.tests.test_surface_generation.SurfaceGenerationTests.test_mat_job_spine | MUST | passed |
| F1 | 尺寸裁剪、方向、精确重采样 | python -m unittest backend.tests.test_surface_generation | MUST | passed |
| F2 | XYZ/NPZ/源模拟、双面、预检 | python -m unittest backend.tests.test_surface_generation | MUST | passed |
| F3 | 独立页面与结果展示 | node --test frontend/tests/surface_generation.test.mjs | MUST | passed |
| F4 | 8560真实验收、GitHub及快捷方式 | python scripts/verify_surface_generation.py | MUST | local passed; GitHub sync pending |

## Run record
F0：命令退出0；真实worker生成单变量double MAT、CSV/XYZ和ZIP；回读逐值相等。无占位输出。
F1：6项测试退出0；检查50mm子矩阵逐值相等、精确插值线性场、Y方向、来源不足、单位及方向。一次测试改为浮点单位换算容差。
F2：11项测试退出0；实数NPZ阶段与轴转换、冻结模拟几何、XYZ单位/重复点/缺失点及双面分别输出均覆盖。预检复用生成算法，无额外状态写入。
F3：新增5项前端测试及全部179项前端测试退出0。新增左侧独立导航、两面来源、尺寸裁剪、预检、结果说明及任务导出目录。已有index样式版本行与styles.css未提交改动保留。
F4：最终相关后端42项、全部前端181项通过；之后手动刷新来源列表的局部修改再次通过7项前端测试。两轮同family复核发现的问题均已修复或显式声明；未进行跨family科学正确性审计，审查结论provisional。
Live：scripts/verify_surface_generation.py退出0，6项上传→预检→worker→下载ZIP→MAT/XYZ回读通过：实测50/60mm原网格、实测50mm精确插值、解析测试190mm双面、解析XYZ及NPZ阶段2。所有解析夹具标为ANALYTIC_TEST_ONLY，不视作实测腐蚀。
Browser：最终页面真实上传C17_100D/190/z.mat并生成任务5043631df0d34989；状态已完成，65×167，49.8×19.2mm，10855点，0.3mm间距；ZIP按钮下载成功。截图保存在本地visualizations目录。
Shortcut：桌面“腐蚀研究工作台.lnk”指向本仓库网站/launch_desktop.py；使用同一入口--no-browser启动成功，固定8560。仅重启HTTP监听进程，原模拟5281f5a8180b4c64的worker PID66492保留，重启后状态running。

修复记录：显式模拟阶段读取a_sd，XYZ重采样标记，两面独立裁剪覆盖，非等距转置和非零原点，MAT多变量默认选择，传统MAT版本限制提示。来源列表改为按需刷新，避免无关慢请求覆盖成功预检说明。

## Deferred
MAT v7.3/HDF5需在MATLAB中另存-v7后上传，页面与上传检查均说明此限制。无随机合成、无自动双面配准。

## Blockers
无。

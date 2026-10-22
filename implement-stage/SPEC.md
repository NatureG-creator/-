# 独立点云与 MAT 生成

目标：从单面或分别提交的双面 MAT、XYZ 文本、外部 NPZ、已完成模拟生成规则点云与单变量 double MAT；提供 190/60/50 mm、自定义及完整尺寸，支持 X/Y 长度方向、裁剪、保留网格和精确尺寸插值。用户已确认方案。

Base commit: b214d9e753cb55dce0f21e83c89cbc5995c6cbb1

输入：每面一个来源，MAT 变量、单位/高程或深度含义、方向、间距及裁剪设置。输出：每面 Z_filled/F_filled MAT、CSV、XYZ、预览、manifest.json，以及成果 ZIP；通过现有任务服务管理。

Success command: Python unittest backend.tests.test_surface_generation；Node frontend/tests/surface_generation.test.mjs；8560 真实上传、下载、MAT 回读检查。

边界：不生成随机腐蚀形貌，不运行六指标或 CA/GA，不自动配准拼接双面，不补造来源不足的长度。保留已有未提交视觉样式，新增导航相关更改单独提交。

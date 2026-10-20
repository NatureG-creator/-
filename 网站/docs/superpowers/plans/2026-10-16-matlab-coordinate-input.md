# MATLAB 坐标文件输入实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 MATLAB 生成的单面/双面 XYZ 坐标文件接入 APDL 耦合区，并在提交前完成可追溯的坐标与网格校验。

**Architecture:** 新增独立坐标解析模块，将三份一维坐标文件恢复为规则 XY 网格和正腐蚀深度矩阵；APDL 服务把解析结果接入现有 `read_face` 和冻结输入包。前端增加来源选择和每面三文件控件，任务提交仍使用原 APDL 几何和求解器。

**Tech Stack:** Python、NumPy、现有 `unittest`；原生 JavaScript 模块测试；现有本地 HTTP API。

## Global Constraints

- 不调用或修改 MATLAB 脚本本身。
- 不改变 CA 状态到表面深度的原有规则、单双面建模逻辑和 49 点材料曲线。
- 单面只要求一组 XYZ；双面要求两组且 XY 网格一致。
- 坐标输入失败必须在预检阶段明确报错，不能静默重采样或猜测尺寸。
- 每次生产代码修改后立即运行相关测试，再运行 APDL 全量回归。

---

### Task 1: 坐标解析器

**Files:**
- Create: `backend/apdl_coordinates.py`
- Test: `backend/tests/test_apdl_coordinates.py`

**Interfaces:**
- `parse_coordinate_triplet(x_path, y_path, z_path) -> ParsedCoordinateSurface`
- `surface_depth(parsed, direction) -> ndarray`
- `validate_coordinate_pair(top, bottom) -> None`

- [ ] 写测试覆盖一列 TXT 解析、规则网格恢复、正/反方向深度、重复点/缺点/间距不规则拒绝和双面坐标不一致拒绝。
- [ ] 运行单模块测试确认新接口尚不存在并正确失败。
- [ ] 实现有限数值读取、唯一坐标排序、完整笛卡尔网格检查和矩阵恢复；不做插值。
- [ ] 运行单模块测试确认通过，并检查错误消息包含具体文件与原因。

### Task 2: 后端 APDL 来源接入

**Files:**
- Modify: `backend/job_service.py`
- Modify: `backend/server.py`
- Modify: `backend/apdl_service.py`
- Modify: `backend/tests/test_apdl_api.py`
- Create: `backend/tests/test_apdl_coordinates_api.py`

**Interfaces:**
- 组合坐标上传记录保存三份或六份文件和原始 SHA。
- APDL source descriptor 增加 `origin: coordinate_files`、`coordinate_uploads` 和 `coordinate_direction`。

- [ ] 写 API 测试覆盖单面三文件上传、双面六文件提交、缺文件、尺寸不一致和冻结副本读取。
- [ ] 实现组合上传检查和输入复制；保留普通上传接口兼容。
- [ ] 在 `read_face` 中调用解析器并复用现有深度/几何校验；metadata 记录坐标范围、间距和方向。
- [ ] 运行坐标 API 测试和已有 APDL API 测试。

### Task 3: 前端单面/双面坐标输入

**Files:**
- Modify: `frontend/apdl.mjs`
- Test: `frontend/tests/apdl-coordinate-input.test.mjs`

**Interfaces:**
- 每个 face 的 `coordinate_uploads: {x, y, z}` 及方向字段进入 source payload。

- [ ] 写前端测试覆盖单面只显示一组、双面显示两组、切换来源清除旧文件、坐标文件未齐不能提交。
- [ ] 实现坐标来源选择、三文件输入、方向选择、上传状态、摘要和错误显示。
- [ ] 运行前端 APDL 三组测试。

### Task 4: 质量门禁与文档

**Files:**
- Modify: `backend/apdl_service.py`
- Modify: `frontend/apdl.mjs`
- Modify: `README.md`
- Modify: `docs/2026-10-15-APDL单双面拉伸使用与验收.md`

- [ ] 将坐标恢复后的网格质量摘要接入预检；严重畸变时禁用“生成并求解”，保留“仅生成模型”。
- [ ] 在网页和 README 说明 MATLAB 脚本输出格式、单面/双面文件数量、单位和方向规则。
- [ ] 运行 APDL 全量后端回归和前端回归，并启动网站做浏览器验收。

### Task 5: 同步与最终验证

**Files:**
- Modify only the ten feature files above in the synchronization checkout.

- [ ] 检查 staged diff 仅包含坐标输入功能。
- [ ] 提交并推送当前 Git 分支。
- [ ] 用远端 commit hash 和测试输出核对后再报告完成。

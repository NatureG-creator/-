# 第三大模块：形貌导出与 APDL 输入包实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不改变 MATLAB 六指标、CA–GA 演化和断点恢复逻辑的前提下，新增一个可从已完成任务生成有限元表面数据和 APDL 输入包的独立运行区域。

**Architecture:** 后端新增有限元导出服务，复用现有 `export_apdl_mat.py` 的表面提取规则，将已完成模拟任务或点云任务结果冻结到新的导出任务目录；前端增加“有限元耦合”面板，通过任务选择、参数预检、导出进度和文件清单完成闭环。所有导出结果进入当前任务的 `.runtime/jobs/<id>/outputs`，不覆盖原始科研目录。

**Tech Stack:** Python 标准库 HTTP 服务、NumPy、SciPy `savemat`、现有 Vanilla JS/CSS 前端、unittest、Node test。

## Global Constraints

- 不修改 `corrosion_model/` 的 CA、GA、六指标和检查点算法。
- 导出默认保留二维矩阵原始行列，不做隐式重采样。
- 只接受有限二维数值矩阵；输出变量只能是 `Z_filled` 或 `F_filled`。
- simulation 模式的深度单位为 μm 输入、mm 输出；measured 模式保留源矩阵数值和尺寸。
- 导出任务只能引用已完成且文件来源可验证的本地任务。
- 所有下载路径必须限制在任务 `outputs` 目录内。
- 先保存数值文件和元数据，再生成预览图；预览图失败不能删除数值输出。

---

### Task 1: 修正并锁定 APDL 表面导出核心

**Files:**
- Modify: `engine/01_运行程序与数据/export_apdl_mat.py`
- Create: `backend/finite_element_export.py`
- Create: `backend/tests/test_finite_element_export.py`
- Modify: `engine/01_运行程序与数据/test_export_apdl_mat.py`

**Interfaces:**
- `load_simulation_surface(path: Path, space_z_um: float) -> np.ndarray`
- `load_measured_matrix(path: Path, variable: str | None) -> tuple[str, np.ndarray]`
- `save_apdl_mat(matrix: np.ndarray, output: Path, variable: str) -> Path`
- `create_surface_bundle(source_kind: str, source_file: Path, output_dir: Path, options: dict) -> dict`

- [ ] **Step 1: Write failing tests**

```python
def test_export_rejects_non_finite_matrix():
    with self.assertRaises(ValueError):
        validate_surface_matrix(np.array([[1.0, np.nan]]))

def test_bundle_keeps_dimensions_and_writes_manifest():
    result = create_surface_bundle("measured", source, output_dir, {
        "input_variable": "F_filled", "output_variable": "F_filled",
        "space_z_um": 25.0, "grid_spacing_mm": 0.05,
    })
    self.assertEqual(result["shape"], [2, 3])
    self.assertTrue((output_dir / "F_filled.mat").is_file())
    self.assertTrue((output_dir / "finite_element_manifest.json").is_file())
```

- [ ] **Step 2: Run the focused tests and verify they fail because the bundle API is absent**

Run: `python -B -m unittest backend.tests.test_finite_element_export -v`

- [ ] **Step 3: Remove the hard-coded demonstration `argv` and duplicate parser call from `export_apdl_mat.py`**

保留命令行参数入口；`main(argv)` 只解析一次传入参数，不能再写死科研目录。

- [ ] **Step 4: Implement `finite_element_export.py`**

实现矩阵校验、simulation/measured 两种来源、MAT/CSV/坐标文件导出、manifest、SHA-256 和 ZIP 打包；simulation 复用 `surface_from_ca_state` 的“第一层金属”规则。

- [ ] **Step 5: Run focused tests and existing APDL tests**

Run: `python -B -m unittest backend.tests.test_finite_element_export engine.01_运行程序与数据.test_export_apdl_mat -v`

- [ ] **Step 6: Commit**

```powershell
git add backend/finite_element_export.py backend/tests/test_finite_element_export.py engine/01_运行程序与数据/export_apdl_mat.py engine/01_运行程序与数据/test_export_apdl_mat.py
git commit -m "feat: add finite element surface export core"
```

### Task 2: 增加有限元导出任务服务与 HTTP 接口

**Files:**
- Modify: `backend/job_service.py`
- Modify: `backend/server.py`
- Modify: `backend/worker.py`
- Create: `backend/tests/test_finite_element_api.py`

**Interfaces:**
- `POST /api/finite-element/exports` 创建导出任务
- `GET /api/finite-element/exports` 查询导出任务
- `GET /api/finite-element/exports/<id>` 获取状态、预检、来源和文件
- `POST /api/finite-element/exports/<id>/stop` 停止排队任务

- [ ] **Step 1: Write failing API tests**

覆盖：已完成模拟任务可创建、未完成任务拒绝、非法变量拒绝、输出路径不能越界、状态包含 manifest 和文件清单。

- [ ] **Step 2: Run focused API tests to verify failure**

Run: `python -B -m unittest backend.tests.test_finite_element_api -v`

- [ ] **Step 3: Implement task creation and worker execution**

冻结源任务 ID、源文件哈希、配置参数和环境指纹；任务目录使用现有 `.runtime/jobs/<id>`；导出完成后状态为 `completed`，失败保留日志和错误。

- [ ] **Step 4: Add safe file serving**

沿用现有下载路由的路径约束，为有限元任务提供 MAT、CSV、PNG、JSON 和 ZIP 下载。

- [ ] **Step 5: Run backend regression tests**

Run: `python -B -m unittest discover -s backend/tests -p "test*.py" -q`

- [ ] **Step 6: Commit**

```powershell
git add backend/job_service.py backend/server.py backend/worker.py backend/tests/test_finite_element_api.py
git commit -m "feat: expose finite element export jobs"
```

### Task 3: 增加前端有限元耦合运行区

**Files:**
- Modify: `frontend/index.html`
- Modify: `frontend/app.js`
- Modify: `frontend/styles.css`
- Modify: `frontend/state.mjs`
- Modify: `frontend/tests/state.test.mjs`

**Interfaces:**
- 面板 ID：`finite-element-panel`
- 状态字段：`feSourceJobId`、`feSourceKind`、`feOptions`、`feExportId`
- 前端请求：创建导出、轮询状态、显示下载文件和错误

- [ ] **Step 1: Write failing state tests**

覆盖源任务筛选、默认选项、变量切换、导出状态转换和失败状态显示。

- [ ] **Step 2: Run Node tests to verify failure**

Run: `node --test frontend/tests/state.test.mjs`

- [ ] **Step 3: Add the panel and controls**

新增来源任务、来源类型、正/反面变量、`space_z_um`、XY 间距、输出精度和导出按钮；显示尺寸、深度范围、来源哈希和预检信息。

- [ ] **Step 4: Add polling and download rendering**

导出任务完成后显示二维预览、坐标文件、MAT、CSV、manifest 和 ZIP 链接；轮询结束时停止定时器。

- [ ] **Step 5: Run Node tests and browser smoke test**

Run: `node --test frontend/tests/state.test.mjs`

浏览器验证：面板切换、任务选择、非法参数提示、提交、进度、下载链接和移动端布局。

- [ ] **Step 6: Commit**

```powershell
git add frontend/index.html frontend/app.js frontend/styles.css frontend/state.mjs frontend/tests/state.test.mjs
git commit -m "feat: add finite element coupling workspace"
```

### Task 4: 文档、验收和同步

**Files:**
- Modify: `README.md`
- Create: `docs/2026-10-15-第三模块验收记录.md`
- Modify: `docs/2026-10-14-验收清单.md`

- [ ] **Step 1: Document data flow and limitations**

明确第一版只生成 APDL 输入包，不自动调用 ANSYS；说明 MATLAB/APDL 变量、单位、尺寸和来源规则。

- [ ] **Step 2: Run full verification**

Run:

```powershell
python -B -m unittest discover -s backend/tests -p "test*.py" -q
node --test frontend/tests/*.test.mjs
```

- [ ] **Step 3: Start local server and run browser smoke test**

使用 `打开网站.cmd` 或 `python start_server.py --port 8523`，验证 `/api/health`、第三模块、任务创建和下载。

- [ ] **Step 4: Review git diff and synchronize**

确认没有 `.runtime`、结果、日志或凭据进入提交；使用网页“一键同步”或 `sync.cmd` 推送。

- [ ] **Step 5: Commit**

```powershell
git add README.md docs/2026-10-15-第三模块验收记录.md docs/2026-10-14-验收清单.md docs/superpowers/plans/2026-10-15-finite-element-coupling.md
git commit -m "docs: document finite element coupling module"
```

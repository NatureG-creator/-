# 单双面APDL拉伸实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 将用户选择的单轴拉伸接入网站，支持单面/双面实体建模、输入包与可核验的MAPDL执行。

**Architecture:** 在现有表面导出旁新增apdl_tension任务。几何、宏生成、来源冻结、求解进程、结果解析和页面分别独立；JobService只做任务接线。原engine/matlab不改。

**Tech Stack:** Python/NumPy/SciPy/现有HTTP服务、纯JavaScript模块、SOLID185 APDL宏、unittest/Node/Edge浏览器。

## Global Constraints

- 依据 `docs/superpowers/specs/2026-10-15-apdl-tension-design.md`。
- 不修改原CA、GA、MATLAB科学逻辑；不改变原表面导出契约。
- 全部APDL数值文件ASCII、N-mm-MPa；深度正值mm；无隐式重采样或厚度裁切。
- 只使用上传或已完成任务来源；冻结副本和哈希，拒绝路径越界。
- 缺ANSYS不能伪造已求解结果；解析理论参考与FE实算分开。
- 在现有功能分支工作，保留main和原科研目录；测试/输出/依赖不上传。

### Task 1：几何与APDL输入包

**Files:** Create `backend/apdl_geometry.py`, `backend/apdl_deck.py`, `backend/tests/test_apdl_geometry.py`, `backend/tests/test_apdl_deck.py`.

**Interfaces:**
- `normalise_options(options: dict) -> dict` 校验并填充模型、材料、网格、求解选项。
- `build_geometry(top_depth: ndarray|None, bottom_depth: ndarray|None, options: dict) -> dict` 返回规范options、top/bottom/remaining、x/y坐标、nodes(N,4含ID)、elements(M,9含ID)、stats、warnings。
- `create_tension_bundle(geometry: dict, output_dir: Path, provenance: dict) -> dict` 写APDL、矩阵/预览/NPZ、manifest和ZIP；返回可JSON化summary。

- [x] 先加测试并运行，确认缺函数/不满足约束时失败：6mm板上下0.8/0.5残厚4.7，非方形方向，穿透拒绝，网格节点/单元/正体积，flat解析参考。
- [x] 实现几何、默认自由泊松约束和夹持模板、SOLID185八节点连接、ASCII宏和数值先保存。
- [x] 目标测试通过后生成差异并独立审阅规格与代码质量。

### Task 2：结果解析与MAPDL执行器

**Files:** Create `backend/apdl_solver.py`, `backend/tests/test_apdl_solver.py`.

**Interfaces:**
- `mapdl_capabilities() -> dict` 返回路径是否可用和来源；不将文件存在等同许可证可用。
- `run_mapdl(output_dir: Path, options: dict, progress=None) -> dict` 在输入包目录执行明确的可执行文件，返回真实结果与分项耗时；缺求解器/超时/无结果/不收敛抛清晰异常。
- `read_tension_results(output_dir: Path, geometry_stats: dict) -> dict` 严格读6列curve（time,u,F,RF_fixed,strain,nominalstress）及可选9列nodal（id,x,y,z,ux,uy,uz,seqv,eqpl）；检验有限性/最终目标位移/两端反力，结果标实算而非理论。

- [x] 先测试合法/非法CSV、结束未达目标、平衡、真实可控假进程超时和缺二进制。
- [x] 实现子进程生命周期与日志/退出码/结果联合检查，不输出模拟求解值。
- [x] 目标测试及独立审阅通过。

### Task 3：来源冻结、任务与HTTP

**Files:** Create `backend/apdl_service.py`, `backend/tests/test_apdl_api.py`; Modify `backend/job_service.py`, `backend/server.py`, `backend/worker.py`.

**Interfaces:**
- `prepare_apdl(service, payload: dict) -> tuple[dict, list[dict]]` 返回任务spec及内部来源记录path/label/sha。
- `precheck_apdl(service,payload:dict)->dict` 返回几何stats/warnings及小尺寸预览，不创建计算任务。
- `freeze_apdl_sources(records, job_dir:Path)->None` 冻结并核对哈希。
- `run_apdl_job(spec:dict,job_dir:Path,progress=None)->dict` 从冻结来源生成包，按run_mode调用求解，分开build/solved状态。

- [x] 先加来源合法性、MAT双变量歧义、source shape/spacing、上传与任务冻结、build API真实worker测试。
- [x] 加kind和三端点；保持旧finite_element任务与导出正常。
- [x] 验证缺求解器在创建solve前明确反馈，并保留可用build路径；求解中失败保留输入。

### Task 4：网页独立拉伸区与交付

**Files:** Create `frontend/apdl.mjs`, `frontend/tests/apdl.test.mjs`; Modify `frontend/index.html`, `frontend/app.js`, `frontend/styles.css`, `README.md`; Create 中文验收说明。

**Interfaces:** `mountApdl({get,post,upload,openJob})`, `renderApdlResult(summary)`；复用现有任务、下载和图片展示。

- [x] 先测前端payload类型、单/双面要求、相对高度/深度与来源转换、非法材料/位移。
- [x] 面板分模式/来源、几何材料、网格加载、预检、建模/求解；保留原表面导出收在兼容区域。
- [x] 桌面/390px浏览器运行flat建模、双面上传、穿透拒绝、ZIP下载与未配置求解器反馈。
- [x] 全量Python/Node回归、独立最终复核；可用真实ANSYS时加无腐蚀基准求解，否则如实标未验收。
- [x] 更新中文说明并提交源码；不提交原始文件、生成模型、求解结果及缓存。

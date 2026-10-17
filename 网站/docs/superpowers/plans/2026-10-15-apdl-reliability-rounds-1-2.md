# APDL前两轮可靠性整改实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 落实用户批准的来源一致性与结果/进程可靠性两轮整改，并同步现有GitHub草稿PR。

**Architecture:** 保留几何、原材料曲线及APDL科学设置。前端集中维护来源草稿和配准确认，后端用来源签名锁定确认对象；结果校核将节点场与实际网格对应，RST未核验明确降级；求解器使用受控进程组管理，计时与停止状态由实际执行记录决定。

**Tech Stack:** 原生JS模块、Python/NumPy、Windows Job Object/受控启动器、unittest与node:test。

## Global Constraints

- 基线`5ca474c85cb9ac17ab4cc1abea674698d0bc02d3`，现有隔离功能分支`codex/performance-comparison`。
- 用户已批准前两轮并要求同步GitHub；不再请求实施或推送确认，不自动合并main。
- 不修改原CA、GA、MATLAB科学源码、49点MISO、双面装配公式或默认材料/加载参数。
- 本机没有MAPDL；不安装求解器或RST依赖，不伪造已完成真实ANSYS验收。
- RST仅非空不能代表完整数值校核；本轮明确`unverified/needs_review`，真实RST读取与原宏实算对照留第三轮。
- 不改用户运行数据；测试文件与日志放忽略的`.runtime`。仅停止本轮自己创建或经完整身份核验的进程。
- 每项按RED→GREEN→独立审阅执行，最后全量回归、浏览器验收及GitHub同步。

## Task 1：来源草稿与配准确认

**Files:** Modify `frontend/apdl.mjs`, `frontend/tests/apdl.test.mjs`; root负责 `backend/apdl_service.py`, `backend/tests/test_apdl_api.py` 的来源签名接线。

**Interfaces:**
- `precheck_apdl` 双面返回`registration_signature`，以当前逐面来源SHA、来源身份及已解析映射生成SHA256。
- `prepare_apdl` 在双面建任务时要求payload签名与重新读取的来源签名相同；预检仍接受显式配准布尔确认。
- 前端提交自动预检后将返回签名带入任务创建；换源/文件/阶段/变量/映射取消配准确认，材料与加载更改只使预检失效。

- [x] RED：同类型任务A阶段2切B只阶段1、旧MAT切新MAT，payload不应携带旧字段；异步返回前输入未blur不应丢失。
- [x] 实现换任务清空阶段/文件、单一草稿状态；input同步原始字符串；重绘前保留当前输入。
- [x] RED：实测um/height切模拟时只读显示需为mm/正深度/继承真实间距；修改来源后配准确认失效，修改E时保留。
- [x] 实现模拟解析值显示和配准生命周期；后端对缺失、过期签名拒绝建任务。
- [x] Node/APDL API测试通过，独立审阅确认。

## Task 2：节点场交叉验证与诚实校核状态

**Files:** Modify `backend/apdl_solver.py` 的结果解析部分、`backend/tests/test_apdl_solver.py`; root负责 `run_apdl_job` 传入实际节点、分阶段计时及前端结果提示接线。

**Interfaces:** `read_tension_results(output,stats,options=None,*,expected_nodes=None)`；expected_nodes为N×4初始节点ID/XYZ。不提供或不能恢复预期网格时，明确未核验，不能完整passed。

- [x] RED：错坐标、全零位移却有非零曲线、加载端/固定端位移矛盾必须失败。
- [x] 按ID比对初始坐标与边界位移，使用适合E13.5节点输出精度的有限容差；维持原6列/9列格式。
- [x] RED：假/不可读取RST不得获得完整passed，零承载需显式异常；无解析参考时不得静默通过异常响应。
- [x] 保留非空RST检查但新增`rst_validation.state='unverified'`和`checks.rst_consistency=null`，总体`needs_review`；输出CSV/节点检查分项结果。
- [x] 正常节点测试夹具使用与几何及载荷一致的场值；更新旧测试，不拿测试RST当真实求解证据。
- [x] 分阶段finally保存成功/失败耗时及执行记录路径，进度卡区分建模/求解/后处理/待复核。
- [x] 目标测试通过，独立审阅确认。

## Task 3：受控求解器生命周期和停止闭环

**Files:** Create `backend/apdl_process.py`, `backend/tests/test_apdl_process.py`; Modify `apdl_solver.py` 执行/清理部分；root负责 `job_service.py` 和对应停止测试。

**Interfaces:** 受控启动返回具有poll/wait/kill及close/terminate的拥有者对象；提供按任务执行记录核验并停止求解组的函数，记录清理状态与创建时间。

- [x] RED：自有launcher启动长任务子进程后先退出，清理仍必须终止本任务后代；模拟停止失败不得宣称已停止。
- [x] Windows使用kill-on-close Job Object；通过受控启动器握手，使实际求解器在成功加入监管后才启动，避免先启动后分组的竞态。
- [x] 生命周期记录持久化后再允许真实程序启动；不继承管理句柄；worker异常退出由句柄关闭处理。目标ANSYS/MPI兼容性标未实算。
- [x] taskkill/受控停止检查返回码，核验本任务所有登记进程；失败保留明确可重试状态和日志，不沿用CA检查点消息。
- [x] 补超时、父先退出、权限失败、PID复用、正常完成/清理等测试；Windows自有Python进程做实际验收。
- [x] 独立审阅确认，保留原非APDL任务停止行为的回归。

## Task 4：整体验收、文档与GitHub同步

**Files:** README、中文整改验收说明、本实施计划、已有复查报告。

- [x] 全量Python及Node回归，检查科学源码未改。
- [x] 浏览器核对换源、配准失效、模拟继承值、平板/双面建模及新的结果状态；已有任务不受影响。
- [x] 独立最终复核，修正Important问题。
- [x] 仅同步源码、测试和中文文档到原草稿PR；核对远端树与本地一致，不提交运行数据，不合并main。

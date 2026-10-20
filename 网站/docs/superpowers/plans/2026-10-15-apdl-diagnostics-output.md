# APDL四项增强实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development task-by-task. 单一实施worker完成后独立审阅，root负责接口、网页与整体验收。

**Goal:** 保持科研逻辑和49点曲线不变，实现材料覆盖提示、命令流内部自检、网格质量报告及三种保存模式，验证后同步现有草稿PR。

**Architecture:** 诊断/配置模块定义纯数据合同，命令流模块生成只读检查与输出控制，结果模块解析真实诊断文件，前端展示估算/实测/未核验层级。

**Tech Stack:** Python/NumPy、APDL、原生JS、unittest/node:test、Windows本机网页。

## Global Constraints

- 基线54edc67；保留原科学源码、ORIGINAL_CURVE全部49点、双面装配/网格/材料/边界和求解物理设置。
- 新选项默认result_save_mode=all，field_output_times=[0.25,0.5,0.75,1]，不更改默认完整输出。
- 材料估算与ETABLE元素节点筛查都不是已验证的积分点验收；RST仍unverified，整体needs_review。
- 无MAPDL，不安装求解器，不伪造运行结果，不终止现有计算任务，不提交.runtime或实验数据。
- 用户已批准实施和GitHub同步，继续当前功能分支和草稿PR，不重复请求批准，不合并main。

## Task 1：诊断和输出合同

Files：新backend/apdl_diagnostics.py、backend/tests/test_apdl_diagnostics.py；root接normalise_options及precheck。

Interfaces：normalise_output_options(options)->dict(result_save_mode,field_output_times)；output_policy_summary(options)->dict；material_coverage_hint(options)->dict；mesh_quality_precheck(nodes,elements,limit=20)->dict；diagnostics_for_geometry(geometry)->dict(material_coverage,mesh_quality,output_policy)。所有函数不修改输入。

- [x] RED：三模式默认及非法比例、49点覆盖估算、弹性/BISO不适用、正交/剪切单元、输入不变。
- [x] 实现纯诊断函数与分块最差单元统计；scaled Jacobian<0.1仅几何预警，不修补或中止。
- [x] root将新选项规范化、precheck诊断返回与警告接线；目标测试GREEN，独立审阅。

## Task 2：APDL检查宏与保存控制

Files：backend/apdl_deck.py、新backend/apdl_macros.py、新tests/test_apdl_macros.py及既有deck测试；root接执行标记识别。

- [x] RED：原materials/boundary及物理solve设置逐字不变，all沿用原OUTRES；last/selected每步曲线和MISO NLDAT不断档。
- [x] 生成mesh_quality.mac、mesh_self_check.mac、boundary_self_check.mac；实际运行生成原始质量报告及6列两阶段自检CSV(stage,node_count,element_count,fixed_count,loaded_count,passed)。自检失败APDL_SELF_CHECK_FAILED并退出。
- [x] MISO后处理生成6列筛查历史；纯元素节点代理不称积分点结果。保留既有6列曲线和9列节点场。
- [x] 输入包包含diagnostics schema=2及只读precheck报告，记录策略/生成宏/哈希；不预生成真实求解诊断文件。
- [x] GREEN、官方命令格式核对与独立审阅。

## Task 3：真实诊断文件解析

Files：新backend/apdl_reports.py、新tests/test_apdl_reports.py、apdl_solver.py结果部分。

- [x] RED：新schema缺自检/质量/筛查、坏列/非有限/重复/错误ID/时间、旧schema兼容。
- [x] 新schema严格检查两阶段CSV与预期网格；保存原质量报告链接不虚构passed；材料筛查与曲线结果集对应，代理超表提示、缺失不得补0。
- [x] 新诊断汇总并入结果，RST仍unverified/needs_review；失败阶段保留原始文件。
- [x] GREEN及独立审阅。

## Task 4：网页、整体验证与同步

Files：root拥有frontend/apdl.mjs、tests/apdl.test.mjs、backend/apdl_geometry.py规范化接线、apdl_service.py、README和中文验收文档。

- [x] 前端先RED，新增保存模式与比例输入，预设不改49点；区分RST与末步CSV，显示材料估算、Python质量诊断及实际文件状态。
- [x] 全量Python/Node、网页模式切换与平板/双面预检/输入包，核对旧任务兼容和科学源码无改。
- [x] 最终独立整体审阅，修复Important；写中文验收和真实MAPDL限制。
- [x] 同步原草稿PR并核对远端树、本地提交一致；仅提交源码测试文档，不合并main。

## 执行记录

- Task1：12项新增测试及geometry合计22项通过；独立审阅无Critical/Important/Minor，额外通过旋转/平移/极端尺度和跨块探针。root的预检API与前端参数测试通过。
- Task2：宏/deck/API目标16项通过，材料/边界/网格/默认solve哈希保护通过；独立审阅无Critical/Important/Minor；独立macro+solver33项通过。

- Task3：新增结果解析与原solver共38项通过；独立发现1项末点CSV舍入误报，另起修复任务新增3回归，修正后41项通过并经原审阅者复核。
- Task4：前端70项通过，最终后端全量273项通过（175.162秒）；隔离单/双面预检、两种输入包与真实下载ZIP哈希核验通过，正式服务已刷新。最终整体独立审阅approve，无未解决Critical/Important/Minor。仅同步源码/测试/中文文档至现有草稿PR，保持main不合并。

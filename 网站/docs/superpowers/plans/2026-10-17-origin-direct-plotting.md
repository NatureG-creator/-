# Origin 本机绘图实施计划

已获用户批准，沿用当前 codex/performance-comparison 工作副本和既有数据目录，不修改拟合计算或研究任务。

1. 验证官方 originpro/OriginExt 能新建专属实例，二维和三维出图并保存 OPJU；记录实际支持的样式及导出。验收：真实导出文件及工程重开。
2. 新增 Origin 参数校验、来源冻结、执行模块（origin_plotting.py）；先测试非法配置、冻结后源修改、未完成拟合和缺软件情形。验收：独立任务不重新拟合，输出带数据来源 hash。
3. 接入 origin_plot 任务、API、独立串行队列；不占腐蚀模拟槽，停止仅影响任务所属 Origin 实例。验收：调度/API 单测和错误状态。
4. 新增 origin.mjs，在拟合结果区域提供模型/组选择、二维/三维适用设置、绘图及继续编辑按钮。验收：前端测试和浏览器真实提交。
5. 用合成二维和双自变量数据端到端验收，核对来源 hash 和可编辑工程；更新依赖及使用文档。验收：回归通过，说明真实验证与限制。

## 接口与责任边界

- GET /api/origin/capabilities：本机安装、依赖、参数默认值。
- POST /api/origin/jobs：{source_job_id, group_index:0, model_id, plot_type:'curve'|'surface', options:{...}}；返回普通任务。
- POST /api/origin/jobs/{id}/open：仅已完成任务的 outputs/origin_project.opju；新建专属交互实例。
- origin_plotting.py 提供 origin_capabilities(), prepare_origin(payload, source_job_dir), freeze_origin(spec, source_job_dir, job_dir), run_origin(job_dir, spec, update), open_origin_project(job_dir)。prepare 返回可序列化 spec；freeze 写冻结来源与样式，worker 仅读取本任务 inputs。
- 前端以 completed fitting job 的 summary.groups 列出候选；options 以 origin_capabilities.defaults 为准。
- 每个任务保留配置、数据 hash、Origin 日志、OPJU 与导出图；禁止执行用户输入的 LabTalk 或任意路径。
- 不清空或关闭用户手动打开的 Origin 工程，不修改前三大部分及49点材料曲线，不覆盖旧结果。

## 进度

- [x] 官方接口及真实出图
- [x] 后端绘图与安全验证
- [x] 服务调度/API
- [x] 前端控件
- [x] 端到端、回归和文档

验收记录见 `docs/2026-10-17-Origin联动验收.md`。本机三维色标刻度字体仍采用模板字体，结果页与使用说明均明确提示；可进入Origin修改。

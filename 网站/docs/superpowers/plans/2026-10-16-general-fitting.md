# 通用数据拟合与科研绘图实施计划

> For agentic workers: 使用 subagent-driven-development，独立文件由专责代理实施，根代理负责接口整合、数据和图形、验收与同步。

**Goal:** 新增第四独立运行区，支持表格与粘贴数据、显式函数自动比较、可选评价指标、诊断图及Origin交换包。

**Architecture:** fitting_data负责表格解析和行审计；fitting_engine负责安全公式、逐组训练与验证及推荐；fitting_outputs负责图表和归档；fitting_service接入现有独立worker、冻结输入与文件下载。前端fitting.mjs独立维护草稿。

**Tech Stack:** Python/NumPy/SciPy/openpyxl/Matplotlib、原生JS、unittest与node:test。

## 全局约束

- 前三部分科学程序与49点曲线不变。不发布远程Sites，沿用本机服务与现有GitHub分支。
- “最佳”仅指所选候选与验证规则；保留失败和无效指标原因，缺少证据不强制推荐。
- 对数/权重/删除行必须显式；时间/分组验证不可随机泄漏。AICc与BIC仅在普通同方差最小二乘口径比较。
- 先单X单Y和分类分组的显式函数回归；自定义公式使用AST白名单，禁用eval/exec；灵活样条与共享参数联合拟合另列未接入能力。
- 第一版Origin支持数据包和可运行导入脚本；不冒充已验证本机Origin连接。

## 接口契约

`load_table(path=None,text=None,sheet=None,variable=None)->{columns,rows,sheets,variables}`；rows为二维JSON数组，缺失为null。

`prepare_dataset(table,selection)->{x,y,sigma,groups,row_ids,audit,x_label,y_label,x_unit,y_unit}`。x/y/sigma/groups等为列表；sigma无选择为null；拒绝不完整行，只有missing_policy=drop才显式剔除并记录原行号。selection包含x_column/y_column/group_column/sigma_column、exclude_rows、x_min/x_max、missing_policy。

`model_catalog()->list`；`normalise_fit_options(options)->dict`；`fit_dataset(dataset,options,progress=None)->dict`。options：models、metric(cv_rmse/cv_mae/aicc/bic/rmse/mae/r2/adjusted_r2)、validation(kfold/loo/time/group)、folds、seed、loss(linear/soft_l1)、custom_formula/custom_parameters/custom_initial/custom_lower/custom_upper、prediction_min/max/points。结果groups:[{label,recommended_id,reason,candidates:[{id,label,formula,status,error,parameters,metrics,cv_predictions,curve:{x,y,confidence_lower,confidence_upper,prediction_lower,prediction_upper},residuals,y_fitted}]}]。所有非有限指标转null并附原因。

HTTP GET /api/fitting/catalog；POST /api/fitting/inspect（upload_id/text/sheet/variable）；POST /api/fitting/precheck（source/selection/options/plot）；POST /api/fitting/jobs，创建kind=fitting；沿用/api/jobs/:id与files下载。

## Task 1 数值引擎

- [x] 写失败测试：线性数据选择简单正确函数、负X幂函数拒绝、时间和分组验证、常量Y的R²缺失、小样本AICc无效、自定义公式拒绝属性/导入、多初值拟合和有限JSON。
- [x] 实现fitting_engine.py与fitting_models.py，参数和预测矩阵尺度预算、逐候选失败隔离，验证在原Y尺度。
- [x] 运行专项测试并独立复核统计口径。

## Task 2 数据、任务、图形和归档

- [x] 写失败测试：CSV标题/无标题、XLSX多表、MAT变量、显式缺失剔除、输入冻结、运行worker及文件哈希。
- [x] 实现fitting_data.py/fitting_outputs.py/fitting_service.py并接入server/job_service/worker。
- [x] 生成散点拟合+残差+QQ+预测对比多面板、模型比较、组间比较；PDF/SVG/PNG/TIFF及CSV/JSON/Origin脚本，置信带不可计算时明确原因。
- [x] 原始冻结输入和实际运行设置记录SHA、种子、耗时及范围，整体ZIP包含原始输入与数值图形。

## Task 3 网页

- [x] 写前端纯函数测试，安全转义、选择、指标帮助和结果空值。
- [x] 新增fitting.mjs及第四导航区域，上传/粘贴→预览→选列→选函数与指标→独立提交→排名/图/下载。
- [x] 草稿即时保存；配置JSON往返；自动推荐说明；单位/图形风格和输出参数可调。

## Task 4 验收

- [x] 各模块专项与独立审阅修复；全量后端/前端回归。
- [x] 本机真实网页：粘贴与上传、分类预检、候选比较、任务、绘图和下载；非线性及非法输入另经专项测试，ZIP逐文件核对。
- [x] 中文使用与边界说明；同步GitHub并核验远端树；不提交运行数据。

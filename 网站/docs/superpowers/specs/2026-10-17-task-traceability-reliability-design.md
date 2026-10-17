# 任务可追溯与运行可靠性设计

## 目标

为点云处理、腐蚀模拟、APDL 和拟合任务建立统一的运行状态与可追溯清单，使网站明确区分输入包生成、真实外部软件运行、结果后处理、校核和归档状态。保持现有腐蚀算法、随机数规则、Taichi/PyCharm 模式和 49 点材料曲线不变。

## 范围

本轮仅处理后端任务元数据、状态表达、归档清单和自动化测试；不重写模拟核心、不改变 APDL 建模方程、不改变 MATLAB 转换规则、不新增 Origin 实机调用。

## 设计

### 1. 统一任务清单

每个任务目录生成 `manifest.json`，至少包含：

- `manifest_version`
- `task_id`、`task_type`
- `created_at`、`started_at`、`finished_at`
- `git_commit`
- `run_mode`、`random_seed`
- 有效配置摘要
- 输入文件路径、类型、字节数、SHA-256
- 输出文件路径、字节数、SHA-256
- MATLAB/MAPDL 是否发现、是否实际调用、版本或探测说明
- 当前任务状态、失败阶段、错误码
- 校核状态和归档状态

清单写入采用临时文件加替换，避免进程中断产生半截 JSON。

### 2. 统一状态与错误表达

任务状态使用以下值：

`created`、`validating`、`queued`、`running`、`checkpointing`、`postprocessing`、`archiving`、`completed`、`failed`、`stopped`、`resumable`。

错误记录包含 `error_code`、`failure_stage`、`message`、`exit_code` 和 `recoverable`。外部软件缺失、许可证失败、结果文件缺失、归档失败必须可区分。

### 3. 归档清单

点云成果归档清单增加来源任务、计算状态、真实 MATLAB/MAPDL 状态、校核状态、归档状态和文件哈希。归档失败不改变计算结果，但必须在任务结果中明确显示 `archive_failed`，并保留重新归档所需信息。

### 4. 验收测试

测试覆盖：

1. 正常任务生成完整清单并包含稳定字段；
2. 输出文件哈希与实际文件一致；
3. MATLAB/MAPDL 不可用时状态为可解释失败或仅输入包完成；
4. 归档失败不会伪装为完整成功；
5. 中断任务记录可恢复性和最后阶段；
6. 旧任务或缺少可选字段时仍能读取并使用默认值；
7. 现有点云、模拟、APDL、拟合测试保持通过。

## 验收标准

- 任何结果页都能回答“是否真实调用 MATLAB/MAPDL、是否通过校核、是否归档成功”。
- 任务目录中的 `manifest.json` 可独立解释输入、配置、输出和状态。
- 清单写入中断不会生成无法解析的 JSON。
- 不改变现有数值结果和材料曲线。
- 既有自动化测试全部通过。


# PyCharm 运行模式设计

## 目标

网页腐蚀模拟默认采用与 PyCharm 高速脚本一致的计算路径：NumPy CA/GA 算子、`ProcessPoolExecutor` 个体并行评估、Taichi 关闭。默认阶段和单阶段并行数为 10，仍可在完整参数目录中编辑。

## 模式语义

- `pycharm`：NumPy 多进程；每个遗传代的种群通过现有 `fitness_优化版.py` 评估。阶段完成后写出 `stage_XXX.npz` 和 manifest，恢复时复用完整阶段；阶段内部中断后从该阶段起重新计算。
- `strict`：NumPy 单进程；保留原有逐个体检查点、随机状态和精确续算能力。
- `fast`：Taichi 路径；依赖和设备由原有配置控制，不提供阶段复用恢复。

## 数据流

网页 `/api/defaults` 返回 `pycharm` 配置。提交后，`runner.py` 将模式映射为 `NumPy ProcessPool`，把 `parallel_workers` 传给现有 `run_ga`。每个阶段结束后导出数值、manifest、汇总和图像；任务中断时，服务端只允许复用通过指纹校验的阶段文件。

## 资源和可观测性

预检使用配置中的 `parallel_workers` 估算并行内存，并提示优先降低进程数或网格层数。任务汇总记录实际后端、配置进程数、读取/计算/导出时间及恢复提示，网页进度显示当前阶段、代数和种群完成数。

## 验收标准

1. 网页默认模式为 `pycharm`，`use_taichi=false`，两个 GA 配置默认 `parallel_workers=10`。
2. `pycharm` 配置禁止打开 Taichi，`strict` 的单进程约束保持不变。
3. 已完成阶段的 manifest 与当前任务指纹一致时可恢复；未完成阶段不会伪造逐个体恢复记录。
4. Python 和前端源文件可通过语法检查；项目依赖环境可用时运行配置、运行器和状态测试。

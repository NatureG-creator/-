# 腐蚀研究网站

本目录是可独立启动的本地研究工作台。原仓库中的科研目录保持原样；网站通过相对路径调用 `engine/` 下的计算副本。

## 内容

- `engine/01_MATLAB实测目标接口/`：MATLAB 实测目标数据读取适配。
- `engine/01_运行程序与数据/`：统一配置、点云/目标数据接口、单阶段 GA、多阶段 `stage_moni`、CA/GA 优化模型、结果处理和测试。
- `engine/实测目标/20261012z100d/matlab_target.mat`：默认工况使用的目标数据示例。
- `frontend/`：参数编辑、文件上传、任务状态、结果下载页面。
- `backend/`：本地HTTP接口、输入校验、任务进程、原子检查点和结果导出。
- `matlab/`：点云到六指标的原MATLAB脚本副本；支持环境变量注入输入和输出路径。
- `DEPENDENCIES.md`：文件来源、用途和同步边界。

## 启动前检查

安装依赖后，在 `网站/` 目录启动：

```powershell
python start_server.py
```

浏览器打开 `http://127.0.0.1:8523/`。

源代码修改后，可双击 `sync.cmd` 一键提交并推送 `网站/` 到 GitHub 的 `main` 分支。脚本只暂存网站目录，不会提交仓库中的其他科研目录。

运行网站测试：

```powershell
python -m unittest discover -s backend/tests -p "test*.py"
```

严格模式默认使用 NumPy、单worker和固定随机种子，支持每个体/每代检查点恢复。高速模式只有在当前Python安装 Taichi 后才可提交。

## 同步原则

源代码修改后，先更新 `engine/` 中对应副本，再运行测试；确认通过后再提交 `网站/`。不要同步 `.runtime/`、`__pycache__`、大体积结果文件、其他原始实验数据或包含个人路径和密钥的配置。

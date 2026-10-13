# MATLAB 转 Python 版本

这个文件夹是对原 MATLAB 腐蚀元胞自动机代码的 Python 转写版，核心目标是保持计算流程和输出含义一致。

## 文件说明

- `corrosion_sim.py`：核心函数库，对应 `CA.m`、`GA.m`、`detect_boundry_3D.m`、`moving_avg_3D.m`、`jixiantiqu_3D.m` 等函数。
- `run_ca_single4.py`：对应 `CA_single4.m` 的脚本入口。
- `run_stage_moni.py`：对应 `stage_moni.m` 的阶段遗传算法入口。
- `requirements.txt`：Python 依赖。

## 安装依赖

我已经在本目录创建了虚拟环境 `.venv`，并安装好了依赖。以后优先使用这个 Python：

```bash
.\.venv\Scripts\python.exe
```

如果你重新安装，可执行：

```bash
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 运行

```bash
.\.venv\Scripts\python.exe run_ca_single4.py
```

或：

```bash
.\.venv\Scripts\python.exe run_stage_moni.py
```

Taichi 环境测试：

```bash
.\.venv\Scripts\python.exe test_taichi_smoke.py
```

## 关于 Taichi

已提供 `init_taichi()`，可以在脚本开头加入：

```python
from corrosion_sim import init_taichi
init_taichi("gpu")
```

当前已加入 `taichi_accel.py`。`run_ca_single4.py` 默认 `use_taichi = True`，会把 `block_process` 中边界元胞的腐蚀、钝化、破裂判断交给 Taichi kernel 处理；图像滤波、分水岭、局部极值检测和统计分析仍使用 `NumPy/SciPy/scikit-image`，这样更接近 MATLAB 工具箱效果。

如果 GPU 后端不可用，程序会自动尝试 CPU 后端；仍失败时会回退到 NumPy/SciPy。

注意：你电脑默认的 `python` 是 Python 3.14/32-bit，不适合 Taichi。当前项目使用本机 `Python 3.11 64-bit` 创建 `.venv`。

## 注意

Python 使用 0 起始索引，MATLAB 使用 1 起始索引。本版本已经在翻译时调整了数组下标。

随机模拟不会逐点复现 MATLAB 的随机数序列，但统计意义和计算流程保持一致。若要重复结果，可在脚本中固定 `np.random.default_rng(seed)` 的种子。

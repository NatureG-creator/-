# APDL 单面运行包

这个目录单独保存原始的单面 MATLAB 点云坐标生成程序，与 `APDL_推荐运行包` 的双面流程分开。原始项目文件没有被覆盖。

## 目录结构

```text
00_输入数据/       原项目中的全部 MAT 输入数据，保留 C、NH 和元胞自动机目录层级
01_MATLAB预处理/   单面 MATLAB 程序、推荐入口和原始配置版
02_坐标文件/       MATLAB 生成的 DIANYUN_X.txt、DIANYUN_Y.txt、DIANYUN_Z.txt
03_APDL建模求解/   单面 APDL 命令流预留目录
04_结果/           运行记录和最终结果
```

## 单面程序的作用

`matlab_apdl_danmian.m` 是独立版单面程序，只处理一个表面矩阵：

```text
Z_filled (ny×nx)
    ↓
DIANYUN_X.txt
DIANYUN_Y.txt
DIANYUN_Z.txt
```

它不会生成反面坐标，也不会自动生成双面实体模型。

`01_MATLAB预处理/原始配置版/` 中还保留了原项目的配置版：

```text
matlab_apdl.m
step00_corrosion_config.m
```

配置版会根据 `step00_corrosion_config.m` 中的路径和输出参数工作，保留它是为了追溯原始流程。新包的直接运行入口使用上面的独立版 `run_prepare_single.m`，这样输出会固定写入本包的 `02_坐标文件`。

## 推荐运行方式

在 MATLAB 中运行：

```matlab
run('01_MATLAB预处理/run_prepare_single.m')
```

默认输入：

```text
00_输入数据/C/C17_100D/60/Z60193.mat
```

该文件包含变量 `Z_filled`，尺寸为 `60×193`。原始单面程序使用：

```matlab
dx = 0.3;
dy = 0.3;
```

因此默认坐标范围为 X=`0～57.6 mm`、Y=`0～17.7 mm`。

## 更换其他 MAT 文件

更换输入文件时，MAT 中需要包含二维变量 `Z_filled`。如果尺寸变化，MATLAB 程序可以生成相应数量的坐标点，但后续 APDL 命令流中的 `nx`、`ny`、坐标间距和节点编号必须同步修改。

## 与双面程序的区别

单面流程只生成：

```text
DIANYUN_X.txt
DIANYUN_Y.txt
DIANYUN_Z.txt
```

双面流程还需要正反面六个坐标文件。不能把单面的三个坐标文件直接当作双面 APDL 的正反面文件。

## APDL 命令流说明

当前原始目录中找到的是单面 MATLAB 坐标生成程序；没有找到与它配套、明确只读取 `DIANYUN_X/Y/Z.txt` 的独立单面 APDL 求解命令流。因此 `03_APDL建模求解` 暂作为单面 APDL 模型放置位置，不能把双面 `model3` 命令流直接复制过来当作单面模型。

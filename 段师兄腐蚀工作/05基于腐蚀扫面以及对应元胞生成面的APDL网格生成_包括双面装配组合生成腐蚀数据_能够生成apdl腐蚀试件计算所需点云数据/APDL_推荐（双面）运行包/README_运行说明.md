# APDL 推荐运行包

这个目录把原始数据、MATLAB 表面处理、APDL 建模求解和结果文件分开保存。原项目目录中的文件没有被覆盖。

## 目录作用

```text
00_输入数据/       全部 MAT 输入数据，保留原来的 C、NH 和元胞自动机目录层级
01_MATLAB预处理/   默认 MATLAB 驱动和双面坐标生成脚本
02_坐标文件/       MATLAB 生成的六个 DIANYUN_*.txt
03_APDL建模求解/   推荐的 model3 APDL 命令流
04_结果/           用于保存最终整理后的力—位移结果
```

## 推荐运行链

默认示例使用：

```text
00_输入数据/C/C17_100D/60/Z60193.mat
00_输入数据/C/C17_100D/60/F.mat
```

两个 MAT 文件分别包含 `Z_filled` 和 `F_filled`，尺寸均为 `60×193`。

### 1. MATLAB 生成坐标文件

在 MATLAB 中将当前目录切换到：

```text
01_MATLAB预处理
```

运行：

```matlab
run('run_prepare_front_back.m')
```

驱动脚本会自动：

1. 加载默认的 `Z60193.mat` 和 `F.mat`；
2. 检查变量名和 `60×193` 尺寸；
3. 调用 `matlab_apdl_shuangmian_recommended.m`；
4. 将坐标文件写入 `02_坐标文件`。

应生成六个文件：

```text
DIANYUN_FRONT_X.txt
DIANYUN_FRONT_Y.txt
DIANYUN_FRONT_Z.txt
DIANYUN_BACK_X.txt
DIANYUN_BACK_Y.txt
DIANYUN_BACK_Z.txt
```

由于正反面共用同一套 X、Y 网格，APDL 实际读取 `FRONT_X`、`FRONT_Y`、`FRONT_Z` 和 `BACK_Z` 四个文件；`BACK_X`、`BACK_Y` 是为数据完整性保留的冗余坐标文件。

### 2. 运行 MAPDL 建模和求解

将 MAPDL 的工作目录设置为 `02_坐标文件`，使 APDL 中的 `*VREAD` 能找到六个坐标文件。然后执行：

```apdl
/INPUT,"..\03_APDL建模求解\model3_recommended",inp
```

推荐命令流会完成：

- `nx=193`、`ny=60`、`nlayers=8` 的双表面实体建模；
- 生成 104220 个节点和 90624 个 `SOLID185` 单元；
- 设置弹性模量、泊松比和 49 点 `MISO` 塑性曲线；
- 左端 `X=0` 约束 `UX=0`；
- 右端 `X=(nx-1)*0.3` 施加 `UX=11`；
- 使用 `NLGEOM,ON`、自动子步和线搜索进行非线性静力分析；
- 在后处理中累加加载边节点的 `RF,FX`。

### 3. 保存结果

APDL 默认会在当前 MAPDL 工作目录（即 `02_坐标文件`）生成：

```text
model3_force_displacement.txt
```

确认文件完整生成后，将它复制到 `04_结果` 保存。文件三列依次为：

```text
Time, Displacement_UX, Total_Reaction_Force_FX
```

## 更换其他 MAT 数据

只有正反面矩阵尺寸一致的数据可以直接进入双面预处理。当前 APDL 主模型固定为 `60×193`：

- `60×193`：可以直接使用当前主模型；
- 行数不是 60 或列数不足 193：需要先重采样、补边或同步修改 APDL 的 `nx`、`ny`；
- 列数大于 193：MATLAB 脚本会从中间裁剪 193 列；
- 正反面尺寸不一致：MATLAB 会直接报错，不能直接建模。

所有原始 MAT 文件均已复制到 `00_输入数据`，但它们不代表都能直接用于当前 `model3`。

## 重要检查

运行前确认：

1. 六个坐标文件各有 `11580` 个数值；
2. 坐标单位、弹性模量、应力和力的单位一致；
3. 反面数据的符号变换与实际扫描方向一致；
4. MAPDL `.out` 和 `.err` 文件中没有未收敛或材料表超范围错误；
5. `model3_force_displacement.txt` 的数据行数与实际结果子步一致。

## 当前验证边界

本目录整理和参数检查已经完成，但当前环境没有实际运行 MAPDL 求解。因此不能仅凭文件存在断言模型已经收敛，也不能替代 ANSYS 中的网格质量、边界条件、材料单位和物理方向检查。


## 本次验证记录

静态检查已通过，详细记录见 `04_结果/验证记录.txt`。本次尝试用 MATLAB 2024b 的 `-batch` 实际运行时，MATLAB 在启动阶段报错：

```text
failed to load settings errors_warnings plugin
```

该错误发生在 MATLAB 执行项目脚本之前，且使用临时用户配置目录重复测试后仍出现，因此目前判断为 MATLAB 安装组件或运行环境问题。坐标文件需要在修复 MATLAB 启动环境后重新运行 `run_prepare_front_back.m` 生成。

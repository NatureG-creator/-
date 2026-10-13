# APDL 推荐运行包 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 创建一个不覆盖原始文件的独立 APDL 推荐运行包，集中保存全部 MAT 输入，并提供默认 `60×193` 双面腐蚀数据的 MATLAB→APDL 运行链。

**Architecture:** 新目录按输入、MATLAB预处理、坐标文件、APDL建模求解、结果和说明分层。MATLAB 驱动脚本加载默认 MAT 对、调用双面坐标生成脚本并把六个文本文件输出到固定目录；APDL 修正版从该目录读取坐标，建立 `SOLID185` 实体并导出力—位移结果。

**Tech Stack:** MATLAB `.m`、ANSYS MAPDL `.inp/.txt`、MAT 文件、PowerShell 静态校验。

## Global Constraints

- 不覆盖当前目录中的任何原始文件。
- 全部 `.mat` 文件复制到新包并保留原相对目录层级。
- 默认示例必须为 `C/C17_100D/60/Z60193.mat` 与 `C/C17_100D/60/F.mat`，变量均为 `60×193`。
- APDL 主模型固定 `nx=193`、`ny=60`、`nlayers=8`，输出文件名必须与 MATLAB 生成文件一致。
- 不声称 MAPDL 实际求解成功；只做文件和参数静态一致性检查。

---

### Task 1: 创建目录并复制输入数据

**Files:**
- Create: `APDL_推荐运行包/00_输入数据/`
- Copy: all existing `*.mat` files under `元胞自动机碳钢/`, `元胞自动机NH/`, `C/`, `NH/`

- [ ] **Step 1: Create target directory tree**

```powershell
$pkg = Join-Path (Get-Location) 'APDL_推荐运行包'
New-Item -ItemType Directory -Force -Path @(
  "$pkg\00_输入数据",
  "$pkg\01_MATLAB预处理",
  "$pkg\02_坐标文件",
  "$pkg\03_APDL建模求解",
  "$pkg\04_结果"
)
```

- [ ] **Step 2: Copy all MAT files while preserving relative paths**

Use `Get-ChildItem -Recurse -Filter *.mat` under the four source directories, compute each path relative to the project root, and copy it below `00_输入数据`.

- [ ] **Step 3: Verify copy count and default pair**

Compare source and target MAT counts and verify both default files exist and contain `Z_filled`/`F_filled` of shape `60×193`.

### Task 2: Add MATLAB preprocessing entry point

**Files:**
- Create: `APDL_推荐运行包/01_MATLAB预处理/run_prepare_front_back.m`
- Copy: `matlab_apdl_shuangmian.m` to `APDL_推荐运行包/01_MATLAB预处理/matlab_apdl_shuangmian_recommended.m`

- [ ] **Step 1: Write the driver**

The driver loads the default pair using `load`, checks variable names and dimensions, changes directory to `02_坐标文件`, runs the recommended preprocessing script, and restores the caller directory with `onCleanup`.

- [ ] **Step 2: Keep coordinate filenames aligned**

Verify the preprocessing script writes exactly `DIANYUN_FRONT_X.txt`, `DIANYUN_FRONT_Y.txt`, `DIANYUN_FRONT_Z.txt`, `DIANYUN_BACK_X.txt`, `DIANYUN_BACK_Y.txt`, and `DIANYUN_BACK_Z.txt`.

### Task 3: Add APDL main command stream

**Files:**
- Copy: `上下表面APDL/model3上下表面APDL的数据合成_修正版.txt` to `APDL_推荐运行包/03_APDL建模求解/model3_recommended.inp`

- [ ] **Step 1: Copy the revision without altering the original**

- [ ] **Step 2: Verify the APDL input contract**

Check `nx=193`, `ny=60`, `nlayers=8`, four `*VREAD` filenames, `SOLID185`, `MP,EX`, `MP,PRXY`, `TB,PLASTIC`, `UX=0` at `X=0`, `UX=11` at `X=(nx-1)*0.3`, `RF,FX` summation, and output `model3_force_displacement.txt`.

### Task 4: Write Chinese run documentation

**Files:**
- Create: `APDL_推荐运行包/README_运行说明.md`

- [ ] **Step 1: Document the complete run order**

Include MATLAB command, generated files, MAPDL `/INPUT` command, expected node/element counts, result location, and compatibility rules for other MAT pairs.

- [ ] **Step 2: Document non-verified boundaries**

State that MAPDL solver execution, convergence, license, and physical correctness still require actual ANSYS/MAPDL verification.

### Task 5: Static validation

**Files:**
- No implementation files changed.

- [ ] **Step 1: Validate all copied MAT files and default dimensions**
- [ ] **Step 2: Validate MATLAB/APDL filename agreement**
- [ ] **Step 3: Validate APDL mesh counts and loading coordinates**
- [ ] **Step 4: Confirm original files remain unchanged by comparing hashes before/after where available**

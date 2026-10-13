%--------------------------------------------------------------------------

cfg = step00_corrosion_config();
% MATLAB 代码：根据网格矩阵生成 ANSYS 点云坐标文件
% 输入：Z 矩阵 (grid_matrix)
% 输出：DIANYUN_X.txt, DIANYUN_Y.txt, DIANYUN_Z.txt
% 网格间距：0.3 (单位：mm 或 m，取决于你的模型)
%--------------------------------------------------------------------------

% === 1. 用户输入部分 ===
% 假设这是你的网格矩阵 (行数 = Ny, 列数 = Nx)
% 例如：从文件读取可以用 load() 或 readmatrix()
% 这里用一个示例矩阵代替，你需要替换成你自己的数据
% 示例：假设矩阵是 60x190 (对应 Y方向60个点，X方向190个点)
% grid_matrix = peaks(190); % 示例函数，生成 190x190 的测试数据
% 或者从 Excel/CSV 读取：
% grid_matrix = readmatrix('your_data.xlsx');

% --- 请在这里定义或读取你的矩阵 ---
if ~exist(cfg.apdl.grid_matrix_variable, 'var')
    error('matlab_apdl: 工作区缺少矩阵变量 %s。', ...
        cfg.apdl.grid_matrix_variable);
end
grid_matrix = eval(cfg.apdl.grid_matrix_variable);
% ----------------------------------

% 网格间距
dx = cfg.apdl.dx_mm;
dy = cfg.apdl.dy_mm;

% 网格起始点 (左下角坐标)
x_start = cfg.apdl.x_start_mm;
y_start = cfg.apdl.y_start_mm;

% === 2. 获取矩阵尺寸 ===
[ny, nx] = size(grid_matrix); % ny = 行数, nx = 列数

% === 3. 生成 X, Y 坐标矩阵 ===
% 注意：meshgrid 的顺序是 x, y
[X, Y] = meshgrid(1:nx, 1:ny);

% 将索引转换为实际物理坐标
X_coords = x_start + (X - 1) * dx;
Y_coords = y_start + (Y - 1) * dy;
Z_coords = grid_matrix; % Z 值直接使用输入矩阵

% === 4. 将矩阵按列优先顺序展开为列向量 (ANSYS 读取顺序) ===
% 注意：ANSYS *VREAD 读取数组时是按列填充的 (Fortran order)
% MATLAB 默认是按列，所以直接 reshape 即可
x_vec = X_coords(:);
y_vec = Y_coords(:);
z_vec = Z_coords(:);

% === 5. 写入文本文件 (ANSYS APDL 格式) ===
% 注意：ANSYS 读取时通常不需要表头，直接是数据

% 写入 X 坐标
filename_x = cfg.output.apdl_x_txt;
dlmwrite(filename_x, x_vec, ...
    'delimiter', cfg.apdl.delimiter, ...
    'precision', cfg.apdl.precision, ...
    'newline', cfg.apdl.newline);
fprintf('X 坐标已保存至: %s\n', filename_x);

% 写入 Y 坐标
filename_y = cfg.output.apdl_y_txt;
dlmwrite(filename_y, y_vec, ...
    'delimiter', cfg.apdl.delimiter, ...
    'precision', cfg.apdl.precision, ...
    'newline', cfg.apdl.newline);
fprintf('Y 坐标已保存至: %s\n', filename_y);

% 写入 Z 坐标
filename_z = cfg.output.apdl_z_txt;
dlmwrite(filename_z, z_vec, ...
    'delimiter', cfg.apdl.delimiter, ...
    'precision', cfg.apdl.precision, ...
    'newline', cfg.apdl.newline);
fprintf('Z 坐标已保存至: %s\n', filename_z);

% === 6. 显示统计信息 ===
fprintf('\n--- 统计信息 ---\n');
fprintf('节点总数: %d\n', length(x_vec));
fprintf('X 范围: [%.3f, %.3f]\n', min(x_vec), max(x_vec));
fprintf('Y 范围: [%.3f, %.3f]\n', min(y_vec), max(y_vec));
fprintf('Z 范围: [%.6f, %.6f]\n', min(z_vec), max(z_vec));

%--------------------------------------------------------------------------
% MATLAB 代码：根据正反面网格矩阵生成 ANSYS 点云坐标文件 (修正扩展维度+处理顺序)
% 输入：Z_filled (正面矩阵), F_filled (反面原始矩阵), m (最大厚度)
%       d_pingjun1, d_pingjun2 (扩展列填充参数)
% 输出：正面坐标文件 (Z不变), 反面坐标文件 (F先扩展→再翻转→再移动)
% 核心修正：1. 扩展维度为 原行数 × (原列数+150)；2. F_filled 先扩展再翻转
%--------------------------------------------------------------------------

% === 1. 用户输入部分 ===
% --- 请在这里定义或读取你的矩阵 ---
grid_matrix_Z = -baseline'.*0.025;    % 正面矩阵 (保持不变)
grid_matrix_F = -baseline'.*0.025;    % 反面原始矩阵 (未翻转)
%m = 6;                   % <-- 设置你的最大厚度值
%d_pingjun1 = 0.025;           % <-- 正面扩展列填充参数1
%d_pingjun2 = 0.025;              % <-- 反面扩展列填充参数2（修正你笔误的d_pingjun12）
%Z_filled=F_filled;
%grid_matrix_Z = Z_filled;
%grid_matrix_F = F_filled;
m = 6;                   % <-- 设置你的最大厚度值
d_pingjun1 = 0.025;           % <-- 正面扩展列填充参数1
d_pingjun2 = 0.025;              % <-- 反面扩展列填充参数2（修正你笔误的d_pingjun12）
% 网格间距
dx = 0.25;
dy = 0.25;
% ----------------------------------

% === 核心修正：矩阵列扩展功能 (确保维度正确) ===
% 1. 获取原始矩阵尺寸 (行: ny, 列: nx)
[nx, ny] = size(grid_matrix_Z);  % 原始尺寸：ny 行 × nx 列
fprintf('原始矩阵尺寸: %d 行 × %d 列\n', ny, nx);

% 2. 计算原始矩阵的最高点
H1 = max(grid_matrix_Z(:));  % Z_filled的最高点
H2 = max(grid_matrix_F(:));  % F_filled的最高点

% 3. 定义扩展列数（左右各75列，总计150列）
expand_cols = 10;
target_cols = ny + 2 * expand_cols;  % 扩展后列数：原列数+150
fprintf('目标扩展尺寸: %d 行 × %d 列\n', ny, target_cols);

% 4. 生成扩展列的填充值
fill_val_Z = d_pingjun1 + H1;  % 正面扩展列填充值
fill_val_F = d_pingjun2 + H2;  % 反面扩展列填充值

% 5. 构造左右扩展的矩阵块（行数与原矩阵一致=ny，列数=75）
left_Z = fill_val_Z * ones(nx, expand_cols);   % 正面左侧扩展块 (ny×75)
right_Z = fill_val_Z * ones(nx, expand_cols);  % 正面右侧扩展块 (ny×75)
left_F = fill_val_F * ones(nx, expand_cols);   % 反面左侧扩展块 (ny×75)
right_F = fill_val_F * ones(nx, expand_cols);  % 反面右侧扩展块 (ny×75)

% 6. 拼接扩展后的矩阵（核心：行不变，列扩展为 nx+150）
grid_matrix_Z_expanded = [left_Z, grid_matrix_Z, right_Z];  % 正面扩展后：ny × (nx+150)
grid_matrix_F_expanded = [left_F, grid_matrix_F, right_F];  % 反面扩展后：ny × (nx+150)

% 7. 验证扩展维度
[ny_exp, nx_exp] = size(grid_matrix_Z_expanded);
fprintf('实际扩展后尺寸: %d 行 × %d 列\n', ny_exp, nx_exp);
fprintf('正面扩展列填充值: %.6f (d_pingjun1=%.6f + H1=%.6f)\n', fill_val_Z, d_pingjun1, H1);
fprintf('反面扩展列填充值: %.6f (d_pingjun2=%.6f + H2=%.6f)\n', fill_val_F, d_pingjun2, H2);
% ==========================



% 网格起始点 (左下角坐标)
x_start = 0;
y_start = 0;

% === 2. 使用扩展后的矩阵尺寸 ===
[ny, nx] = size(grid_matrix_Z_expanded);  % 扩展后：ny 行 × nx 列

% === 3. 生成 X, Y 坐标矩阵 (正反面共用同一坐标系) ===
[X, Y] = meshgrid(1:nx, 1:ny);
X_coords = x_start + (X - 1) * dx;
Y_coords = y_start + (Y - 1) * dy;

% 展开坐标向量 (用于写入文件)
x_vec = X_coords(:);
y_vec = Y_coords(:);

% === 4. 处理正面 (Z) - 保持不变 ===
Z_coords_front = grid_matrix_Z_expanded;  % 扩展后的正面矩阵
z_vec_front = Z_coords_front(:);

% === 5. 处理反面 (F) - 核心修正：先扩展 → 再翻转 → 最后移动 ===
% 步骤1: 对扩展后的反面进行修正翻转
F_flipped = -(grid_matrix_F_expanded); 
% 步骤2: 计算正面最高点和翻转后反面的最低点
max_front = max(z_vec_front);          % 正面最高点
min_flipped = min(F_flipped(:));       % 翻转后反面的最低点 (当前值)

% 步骤3: 计算反面需要移动到的目标最低点
% 目标: max_front - target_min = m  => target_min = max_front - m
target_min = max_front - m;

% 步骤4: 计算移动距离 (偏移量)
offset = target_min - min_flipped;

% 步骤5: 对翻转后的反面矩阵进行垂直移动
F_coords_back = F_flipped + offset;
z_vec_back = F_coords_back(:);

% === 6. 写入文本文件 (ANSYS APDL 格式) ===
% 正面文件
dlmwrite('DIANYUN_FRONT_X.txt', x_vec, 'delimiter', '\t', 'precision', '%.6f', 'newline', 'pc');
dlmwrite('DIANYUN_FRONT_Y.txt', y_vec, 'delimiter', '\t', 'precision', '%.6f', 'newline', 'pc');
dlmwrite('DIANYUN_FRONT_Z.txt', z_vec_front, 'delimiter', '\t', 'precision', '%.6f', 'newline', 'pc');
fprintf('正面坐标已保存。\n');

% 反面文件
dlmwrite('DIANYUN_BACK_X.txt', x_vec, 'delimiter', '\t', 'precision', '%.6f', 'newline', 'pc');
dlmwrite('DIANYUN_BACK_Y.txt', y_vec, 'delimiter', '\t', 'precision', '%.6f', 'newline', 'pc');
dlmwrite('DIANYUN_BACK_Z.txt', z_vec_back, 'delimiter', '\t', 'precision', '%.6f', 'newline', 'pc');
fprintf('反面坐标已保存 (先扩展→再翻转→再移动)。\n');

% === 7. 验证输出 ===
fprintf('\n--- 厚度验证 ---\n');
fprintf('正面最高点: %.6f\n', max_front);
fprintf('反面最低点: %.6f\n', min(z_vec_back));
fprintf('实际最大厚度: %.6f\n', max_front - min(z_vec_back));

%--------------------------------------------------------------------------
% 可视化部分：验证扩展、翻转和厚度设置是否正确
%--------------------------------------------------------------------------

% === 1. 获取用于绘图的坐标矩阵 (扩展后尺寸) ===
[X_plot, Y_plot] = meshgrid(1:nx, 1:ny);

% === 2. 图1：反面处理全流程验证 (扩展→翻转→移动) ===
figure('Name', '反面处理全流程验证', 'NumberTitle', 'off', 'Position', [100, 100, 1500, 500]);

% 子图1：原始反面 (未扩展、未翻转)
subplot(1, 3, 1);
surf(meshgrid(1:size(grid_matrix_F,2), 1:ny), grid_matrix_F, 'EdgeColor', 'none');
title('原始反面 (未扩展、未翻转)');
xlabel('列索引'); ylabel('行索引'); zlabel('Z');
grid on; box on; view(3); camlight; lighting gouraud;

% 子图2：扩展后反面 (未翻转)
subplot(1, 3, 2);
surf(X_plot, Y_plot, grid_matrix_F_expanded, 'EdgeColor', 'none');
title('反面 (已扩展、未翻转)');
xlabel('列索引'); ylabel('行索引'); zlabel('Z');
grid on; box on; view(3); camlight; lighting gouraud;

% 子图3：处理后反面 (已扩展→翻转→移动)
subplot(1, 3, 3);
surf(X_plot, Y_plot, F_coords_back, 'EdgeColor', 'none');
hold on;
plot3([1 1 nx nx 1], [1 ny ny 1 1], max_front*ones(1,5), 'r--', 'LineWidth', 1);
text(1, 1, max_front, '正面最高点', 'Color', 'r', 'FontSize', 10);
title('反面 (已扩展→翻转→移动)');
xlabel('列索引'); ylabel('行索引'); zlabel('Z');
grid on; box on; view(3); camlight; lighting gouraud;
zlim([min(z_vec_back)-abs(m*0.1) max_front+abs(m*0.1)]);

fprintf('\n图1：验证反面处理流程：原始 → 扩展 → 翻转+移动\n');

% === 3. 图2：正反面叠加视图 (扩展后最终效果) ===
figure('Name', '正反面装配预览 (扩展后)', 'NumberTitle', 'off', 'Position', [200, 200, 800, 600]);

% 绘制正面 (蓝色半透明)
surf(X_plot, Y_plot, Z_coords_front, 'FaceAlpha', 0.7, 'EdgeColor', 'none', 'FaceColor', 'blue');
hold on;

% 绘制反面 (红色半透明)
surf(X_plot, Y_plot, F_coords_back, 'FaceAlpha', 0.7, 'EdgeColor', 'none', 'FaceColor', 'red');

% 绘制厚度参考线
corner_x = [1, 1];
corner_y = [1, 1];
corner_z_front = interp2(X_plot, Y_plot, Z_coords_front, 1, 1);
corner_z_back = interp2(X_plot, Y_plot, F_coords_back, 1, 1);
plot3(corner_x, corner_y, [corner_z_front, corner_z_back], 'k-', 'LineWidth', 2);
text(1, 1, (corner_z_front+corner_z_back)/2, sprintf('厚度 = %.2f', m), ...
    'HorizontalAlignment', 'center', 'VerticalAlignment', 'middle', 'FontSize', 12, 'Color', 'k');

title(sprintf('正反面装配图 (目标厚度 m = %.2f，扩展后列数=%d)', m, nx));
xlabel('X'); ylabel('Y'); zlabel('Z');
legend('正面 (扩展后)', '反面 (扩展→翻转→移动后)');
grid off; box on; view(3); camlight; lighting gouraud;
hold off;

% === 8. 计算极值点 (适配扩展后物理坐标) ===
fprintf('\n--- 极值点计算结果 (物理坐标) ---\n');

% 任务1: X=0, Y=0 处最低Z值
x0 = x_start;
y0 = y_start;
z_front_min = grid_matrix_Z_expanded(1, 1); 
z_back_min = F_coords_back(1, 1); 
z_min_val = min([z_front_min, z_back_min]);
fprintf('点1 (X=0, Y=0): 最低 Z 坐标 = %.6f\n', z_min_val);
fprintf('     物理位置: X=%.3f, Y=%.3f\n', x0, y0);

% 任务2: 扩展后最大物理坐标处最高Z值
x_max_phys = x_start + (nx - 1) * dx;  % 扩展后最大X坐标
y_max_phys = y_start + (ny - 1) * dy;  % 最大Y坐标
z_front_max = grid_matrix_Z_expanded(ny, nx); 
z_back_max = F_coords_back(ny, nx); 
z_max_val = max([z_front_max, z_back_max]);
fprintf('点2 (X=%.3f, Y=%.3f): 最高 Z 坐标 = %.6f\n', x_max_phys, y_max_phys, z_max_val);
fprintf('     物理位置: X=%.3f, Y=%.3f\n', x_max_phys, y_max_phys);
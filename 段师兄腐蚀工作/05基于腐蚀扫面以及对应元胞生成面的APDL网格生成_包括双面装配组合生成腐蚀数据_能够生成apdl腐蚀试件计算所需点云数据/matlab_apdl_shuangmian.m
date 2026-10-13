%--------------------------------------------------------------------------
% MATLAB 代码：根据正反面网格矩阵生成 ANSYS 点云坐标文件
% 输入：Z_filled (正面矩阵), F_filled (反面原始矩阵), m (最大厚度)
% 输出：正面坐标文件 (Z不变), 反面坐标文件 (F已翻转并移动)
%--------------------------------------------------------------------------
%190MM取中间段72mm
%72/0.3=240mm
[nRows, nCols] = size(F_filled);

if ~isequal(size(Z_filled), size(F_filled))
    error('正反面矩阵尺寸不一致，请先进行配准或重采样。');
end

targetCols = 193;

if nCols > targetCols
    % 从中间对称截取 193 列
    c1 = floor((nCols - targetCols) / 2) + 1;
    c2 = c1 + targetCols - 1;

    Z_filled = Z_filled(:, c1:c2);
    F_filled = F_filled(:, c1:c2);

elseif nCols < targetCols
    error(['当前数据只有 ', num2str(nCols), ...
           ' 列，小于目标列数 ', num2str(targetCols), ...
           '，不能直接截取，请先补边或插值。']);

end

if ~isequal(size(Z_filled), [nRows, targetCols])
    error('裁剪后的矩阵尺寸不正确。');
end

grid_matrix_Z = Z_filled;
grid_matrix_F = F_filled;
% === 1. 用户输入部分 ===
% --- 请在这里定义或读取你的矩阵 ---
grid_matrix_Z = Z_filled;    % 正面矩阵 (保持不变)
grid_matrix_F = F_filled;    % 反面原始矩阵 (未翻转)
m = 6;                      % <-- 设置你的最大厚度值
% ----------------------------------

% 网格间距
dx = 0.3;
dy = 0.3;

% 网格起始点 (左下角坐标)
x_start = 0;
y_start = 0;

% === 2. 获取矩阵尺寸 ===
[ny, nx] = size(grid_matrix_Z); 

% === 3. 生成 X, Y 坐标矩阵 (正反面共用同一坐标系) ===
[X, Y] = meshgrid(1:nx, 1:ny);
X_coords = x_start + (X - 1) * dx;
Y_coords = y_start + (Y - 1) * dy;

% 展开坐标向量 (用于写入文件)
x_vec = X_coords(:);
y_vec = Y_coords(:);

% === 4. 处理正面 (Z) - 保持不变 ===
Z_coords_front = grid_matrix_Z;
z_vec_front = Z_coords_front(:);

% === 5. 处理反面 (F) - 翻转 + 移动 ===
% 步骤1: 上下翻转矩阵，使其与正面坐标对应
F_flipped = -grid_matrix_F; 

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
fprintf('反面坐标已保存 (已翻转并移动)。\n');

% === 7. 验证输出 ===
fprintf('\n--- 厚度验证 ---\n');
fprintf('正面最高点: %.6f\n', max_front);
fprintf('反面最低点: %.6f\n', min(z_vec_back));
fprintf('实际最大厚度: %.6f\n', max_front - min(z_vec_back));
%--------------------------------------------------------------------------
% 可视化部分：验证翻转和厚度设置是否正确
%--------------------------------------------------------------------------

% === 1. 获取用于绘图的坐标矩阵 (保持与前面一致) ===
[X_plot, Y_plot] = meshgrid(1:nx, 1:ny);

% === 2. 图1：查看反面处理前后的对比 ===
figure('Name', '反面处理验证', 'NumberTitle', 'off', 'Position', [100, 100, 1200, 500]);

% 子图1：原始反面 (未翻转)
subplot(1, 2, 1);
surf(X_plot, Y_plot, grid_matrix_F, 'EdgeColor', 'none');
hold on;
% 绘制边界框以辅助观察
maxZ = max(grid_matrix_F(:)); minZ = min(grid_matrix_F(:));
plot3([1 1 nx nx 1], [1 ny ny 1 1], [maxZ maxZ maxZ maxZ maxZ], 'r--', 'LineWidth', 1);
title('原始反面数据 (未翻转)');
xlabel('X'); ylabel('Y'); zlabel('Z');
grid on; box on; view(3); camlight; lighting gouraud;

% 子图2：处理后的反面 (已翻转并移动)
subplot(1, 2, 2);
surf(X_plot, Y_plot, F_coords_back, 'EdgeColor', 'none');
hold on;
% 绘制厚度参考线
plot3([1 1 nx nx 1], [1 ny ny 1 1], max_front*ones(1,5), 'r--', 'LineWidth', 1);
text(1, 1, max_front, '正面最高点', 'Color', 'r', 'FontSize', 10);
title('处理后的反面 (已翻转并移动)');
xlabel('X'); ylabel('Y'); zlabel('Z');
grid on; box on; view(3); camlight; lighting gouraud;
zlim([min(z_vec_back)-abs(m*0.1) max_front+abs(m*0.1)]); % 统一Z轴范围便于观察

fprintf('图1：请检查左侧原始反面是否需要“上下翻转”才能与正面匹配。\n');
fprintf('      右侧红色虚线代表正面最高点位置，反面最低点应在下方距离为 m 的位置。\n');

% === 3. 图2：正反面叠加视图 (最终装配效果) ===
figure('Name', '正反面装配预览', 'NumberTitle', 'off', 'Position', [200, 200, 800, 600]);

% 绘制正面 (蓝色半透明)
surf(X_plot, Y_plot, Z_coords_front, 'FaceAlpha', 0.7, 'EdgeColor', 'none', 'FaceColor', 'blue');
hold on;

% 绘制反面 (红色半透明)
surf(X_plot, Y_plot, F_coords_back, 'FaceAlpha', 0.7, 'EdgeColor', 'none', 'FaceColor', 'red');

% 绘制厚度参考线 (在角落画一根线表示厚度 m)
corner_x = [1, 1];
corner_y = [1, 1];
corner_z_front = interp2(X_plot, Y_plot, Z_coords_front, 1, 1); % 获取角落点Z值
corner_z_back = interp2(X_plot, Y_plot, F_coords_back, 1, 1);
plot3(corner_x, corner_y, [corner_z_front, corner_z_back], 'k-', 'LineWidth', 2);
text(1, 1, (corner_z_front+corner_z_back)/2, sprintf('厚度 = %.2f', m), ...
    'HorizontalAlignment', 'center', 'VerticalAlignment', 'middle', 'FontSize', 12, 'Color', 'k');

title(sprintf('正反面装配图 (目标厚度 m = %.2f)', m));
xlabel('X'); ylabel('Y'); zlabel('Z');
legend('正面 (Z_filled)', '反面 (F_filled)');
grid on; box on; view(3); camlight; lighting gouraud;
hold off;

fprintf('图2：正反面叠加视图。蓝色为正面，红色为反面。\n');
fprintf('      请检查两者是否对应，以及黑色线段长度是否符合预期厚度。\n');



% === 8. 计算极值点 (修正物理坐标) ===
fprintf('\n--- 极值点计算结果 (物理坐标) ---\n');

% -------------------------------------------------------------------------
% 任务1: 找出 X=0, Y=0 处线上的 Z 值最低点
% 在矩阵中，X=0, Y=0 对应的是第一个点 (索引 1, 1)

% 获取该位置的物理坐标 (X, Y)
x0 = x_start;          % 因为是从0开始，所以索引1对应x_start
y0 = y_start;

% 获取该位置 (正面和反面) 的 Z 值
z_front_min = grid_matrix_Z(1, 1); 
z_back_min = F_coords_back(1, 1); 

% 找出这条线上的最低点
z_min_val = min([z_front_min, z_back_min]);

fprintf('点1 (X=0, Y=0): 最低 Z 坐标 = %.6f\n', z_min_val);
fprintf('     物理位置: X=%.3f, Y=%.3f\n', x0, y0);

% -------------------------------------------------------------------------
% 任务2: 找出 X=nx, Y=ny 处线上的 Z 值最高点
% 注意：nx 和 ny 是节点数
% 最大索引在 X 方向是 nx, 在 Y 方向是 ny
% 对应的物理坐标是 (nx-1)*dx 和 (ny-1)*dy (因为从0开始)

% 获取该位置的物理坐标
x_max_phys = x_start;
y_max_phys = y_start + (ny - 1) * dy;

% 获取该位置 (正面和反面) 的 Z 值
% 注意矩阵索引是 (行, 列) -> (ny, nx)
z_front_max = grid_matrix_Z(ny, nx); 
z_back_max = F_coords_back(ny, nx); 

% 找出这条线上的最高点
z_max_val = max([z_front_max, z_back_max]);

fprintf('点2 (X=0, Y=ny): 最高 Z 坐标 = %.6f\n', z_max_val);
fprintf('     物理位置: X=%.3f, Y=%.3f\n', x_max_phys, y_max_phys);
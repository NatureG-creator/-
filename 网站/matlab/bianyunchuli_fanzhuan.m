%% 点云边缘点直接删除处理 + z值反转（支持txt文本文件输入）
% 清理工作区
clear; clc; close all;
cfg = step00_corrosion_config();

%% 1. 数据加载与预处理
% 加载txt格式点云数据：要求文件每行是"x y z"格式，数值以空格/制表符/逗号分隔
% 请替换为你的txt文件完整路径（含扩展名）
pc_data = load(cfg.input.edge_processing_file);
x = pc_data(:,1);  % 第一列为x坐标
y = pc_data(:,2);  % 第二列为y坐标
z = pc_data(:,3);  % 第三列为z坐标

% 可视化原始点云
figure; scatter3(x,y,z,cfg.figure.point_cloud_marker_size,z,'filled');
title('原始点云数据');
xlabel('X'); ylabel('Y'); zlabel('Z');
grid on; hold on;

%% 2. 边缘检测（与原逻辑一致，识别需删除的边缘点）
% 定义边缘区域比例：edge_threshold=0.05表示边缘占x/y总范围的5%（可根据需求调整）
x_min = min(x); x_max = max(x);
y_min = min(y); y_max = max(y);
edge_threshold = cfg.preprocessing.remove_edge_ratio;

% 识别x、y方向的边缘点（边缘区域内的点标记为true）
x_edge_mask = (x < x_min + edge_threshold*(x_max - x_min)) | (x > x_max - edge_threshold*(x_max - x_min));
y_edge_mask = (y < y_min + edge_threshold*(y_max - y_min)) | (y > y_max - edge_threshold*(y_max - y_min));
edge_mask = x_edge_mask | y_edge_mask;  % 合并x、y方向的边缘点（需删除的点）

% 分离边缘点与内部点（仅保留内部点，删除边缘点）
inner_points = pc_data(~edge_mask,:);  % ~edge_mask表示取反：保留非边缘点
deleted_edge_points = pc_data(edge_mask,:);  % 被删除的边缘点（用于可视化对比）

% 可视化：原始点云+被删除的边缘点（红色标记）
scatter3(deleted_edge_points(:,1), deleted_edge_points(:,2), ...
    deleted_edge_points(:,3), cfg.figure.deleted_point_marker_size, ...
    'r', 'filled');
title('原始点云与被删除的边缘点（红色）');
hold off;

%% 3. z值反转（核心新增功能：最大值变最小值，最小值变最大值）
% 提取内部点的z坐标
z_inner = inner_points(:,3);
% 计算z的原始范围
z_min = min(z_inner);
z_max = max(z_inner);
% 反转z值：新z = 原始z范围的最大值 + 最小值 - 原始z值
if cfg.preprocessing.reverse_z_after_edge_removal
    z_reversed = z_max + z_min - z_inner;
else
    z_reversed = z_inner;
end
% 更新内部点的z坐标
inner_points_reversed = inner_points;
inner_points_reversed(:,3) = z_reversed;

%% 4. 结果可视化（对比原始点云、删除边缘点后的点云、z值反转后的点云）
figure('Position', cfg.figure.reverse_compare_position);

% 子图1：原始点云
subplot(1,3,1); scatter3(x,y,z, ...
    cfg.figure.point_cloud_marker_size,z,'filled');
title('原始点云');
xlabel('X'); ylabel('Y'); zlabel('Z');
grid on;

% 子图2：删除边缘点后的点云（未反转z）
subplot(1,3,2); scatter3(inner_points(:,1), inner_points(:,2), ...
    inner_points(:,3), cfg.figure.point_cloud_marker_size, ...
    inner_points(:,3), 'filled');
title('删除边缘点后的点云（z未反转）');
xlabel('X'); ylabel('Y'); zlabel('Z');
grid on;

% 子图3：z值反转后的点云（已删除边缘点）
subplot(1,3,3); scatter3(inner_points_reversed(:,1), ...
    inner_points_reversed(:,2), inner_points_reversed(:,3), ...
    cfg.figure.point_cloud_marker_size, inner_points_reversed(:,3), 'filled');
title('删除边缘点 + z值反转后的点云');
xlabel('X'); ylabel('Y'); zlabel('Z（反转后）');
grid on;

%% 5. 保存处理结果为txt文件
% 保存删除边缘点后的点云（未反转z）
save(cfg.output.edge_removed_txt, 'inner_points', '-ascii');
% 保存z值反转后的点云（已删除边缘点）
save(cfg.output.edge_reversed_txt, 'inner_points_reversed', '-ascii');

% 输出处理信息
disp(['边缘点删除完成！共删除 ', num2str(length(deleted_edge_points)), ' 个边缘点']);
disp(['z值反转完成！原始z范围：[', num2str(z_min), ', ', num2str(z_max), ']，反转后z范围：[', num2str(min(z_reversed)), ', ', num2str(max(z_reversed)), ']']);
disp(['处理后的点云已保存至 ', cfg.output.edge_removed_txt, '（未反转z）']);
disp(['z值反转后的点云已保存至 ', cfg.output.edge_reversed_txt]);

%% 点云边缘点直接删除处理（支持txt文本文件输入）
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

%% 3. 结果可视化（对比原始点云与删除边缘点后的点云）
figure; 
subplot(1,2,1); scatter3(x,y,z, ...
    cfg.figure.point_cloud_marker_size,z,'filled');
title('原始点云'); xlabel('X'); ylabel('Y'); zlabel('Z'); grid on;
subplot(1,2,2); scatter3(inner_points(:,1), inner_points(:,2), ...
    inner_points(:,3), cfg.figure.point_cloud_marker_size, ...
    inner_points(:,3), 'filled');
title('删除边缘点后的点云'); xlabel('X'); ylabel('Y'); zlabel('Z'); grid on;

%% 4. 保存处理结果为txt文件
save(cfg.output.edge_removed_txt, 'inner_points', '-ascii');
disp(['边缘点删除完成！共删除 ', num2str(length(deleted_edge_points)), ' 个边缘点']);
disp(['处理后的点云已保存至 ', cfg.output.edge_removed_txt]);

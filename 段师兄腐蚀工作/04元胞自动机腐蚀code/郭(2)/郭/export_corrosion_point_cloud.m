% export_corrosion_point_cloud.m
% 功能：将腐蚀形貌结果导出为点云文件，支持 .csv、.txt、.asc。
%
% 使用方式：
% 1. 先在 MATLAB 中确保工作区已有 a_output、w、l、n、space；
%    或者本脚本会自动尝试加载 Python 导出的 .mat 文件。
% 2. 运行：
%       run('export_corrosion_point_cloud.m')
%
% 输出文件：
% - corrosion_surface_point_cloud.csv  带表头，适合 Excel / CloudCompare 导入
% - corrosion_surface_point_cloud.txt  制表符分隔，带表头
% - corrosion_surface_point_cloud.asc  空格分隔，无表头，常用于点云软件
% - corrosion_raw_depth_point_cloud.csv/txt/asc  原始 depth_map 点云

export_total_timer = tic;
fprintf('=== 开始导出腐蚀点云 ===\n');

% 第一部分：读取或检查基础数据。
% a_output 是腐蚀元胞自动机最终三维矩阵，是生成点云的核心数据。
if ~exist('a_output', 'var')
    default_mat = 'E:\Codex项目文件\python腐蚀代码\outputs\matlab_export\python_to_matlab_plot_data.mat';
    if exist(default_mat, 'file')
        fprintf('工作区未发现 a_output，自动加载: %s\n', default_mat);
        load(default_mat);
    else
        [file_name, file_path] = uigetfile('*.mat', '请选择包含 a_output 的 .mat 文件');
        if isequal(file_name, 0)
            error('未选择 .mat 文件，且工作区没有 a_output，无法导出点云。');
        end
        load(fullfile(file_path, file_name));
    end
end

% 第二部分：自动推断网格尺寸和元胞尺寸。
if ~exist('w', 'var') || isempty(w)
    w = size(a_output, 1);
end
if ~exist('l', 'var') || isempty(l)
    l = size(a_output, 2);
end
if ~exist('n', 'var') || isempty(n)
    n = size(a_output, 3) - 1;
end
if ~exist('space', 'var') || isempty(space)
    space = 25; % 单位：um。若你的元胞尺寸不是 25 um，请在运行前修改工作区变量 space。
end

w = double(w);
l = double(l);
n = double(n);
space = double(space);

fprintf('网格尺寸: w=%d, l=%d, n=%d\n', w, l, n);
fprintf('元胞尺寸: space=%.6g um\n', space);

% 第三部分：计算腐蚀表面。
% MATLAB 原逻辑：
% [baseline, ~,~,depth_map] = moving_avg_3D(a_output, 5, w,l,n);
% baseline 是平滑后的腐蚀表面；depth_map 是原始腐蚀深度层位置。
if ~exist('baseline', 'var') || ~exist('depth_map', 'var')
    [baseline, ~, ~, depth_map] = moving_avg_3D(a_output, 5, w, l, n);
end

% 第四部分：生成点云坐标。
% 坐标定义：
% X_um = X 方向物理坐标，单位 um
% Y_um = Y 方向物理坐标，单位 um
% Z_um = 腐蚀深度，单位 um，Z=0 表示初始未腐蚀参考面
%
% 注意：
% MATLAB meshgrid(1:l,1:w) 生成的是列方向 X、行方向 Y；
% 因此这里 X 对应列号，Y 对应行号。
[X_idx, Y_idx] = meshgrid(1:l, 1:w);
X_um = (X_idx - 1) * space;
Y_um = (Y_idx - 1) * space;

baseline_depth_um = (baseline - min(baseline(:))) * space;
raw_depth_um = (depth_map - min(depth_map(:))) * space;

surface_points = [X_um(:), Y_um(:), baseline_depth_um(:), baseline(:), depth_map(:)];
raw_points = [X_um(:), Y_um(:), raw_depth_um(:), baseline(:), depth_map(:)];

% 第五部分：创建输出文件夹。
output_dir = 'E:\Codex项目文件\python腐蚀代码\outputs\point_cloud_export';
if ~exist(output_dir, 'dir')
    mkdir(output_dir);
end

% 第六部分：保存平滑表面点云。
surface_csv = fullfile(output_dir, 'corrosion_surface_point_cloud.csv');
surface_txt = fullfile(output_dir, 'corrosion_surface_point_cloud.txt');
surface_asc = fullfile(output_dir, 'corrosion_surface_point_cloud.asc');

surface_table = array2table(surface_points, ...
    'VariableNames', {'X_um', 'Y_um', 'Z_um', 'BaselineLayer', 'RawDepthLayer'});
writetable(surface_table, surface_csv);
writetable(surface_table, surface_txt, 'Delimiter', '\t');
writematrix(surface_points(:, 1:3), surface_asc, 'Delimiter', ' ');

% 第七部分：保存原始 depth_map 点云。
raw_csv = fullfile(output_dir, 'corrosion_raw_depth_point_cloud.csv');
raw_txt = fullfile(output_dir, 'corrosion_raw_depth_point_cloud.txt');
raw_asc = fullfile(output_dir, 'corrosion_raw_depth_point_cloud.asc');

raw_table = array2table(raw_points, ...
    'VariableNames', {'X_um', 'Y_um', 'Z_um', 'BaselineLayer', 'RawDepthLayer'});
writetable(raw_table, raw_csv);
writetable(raw_table, raw_txt, 'Delimiter', '\t');
writematrix(raw_points(:, 1:3), raw_asc, 'Delimiter', ' ');

% 第八部分：输出统计信息。
fprintf('平滑表面点数: %d\n', size(surface_points, 1));
fprintf('原始深度点数: %d\n', size(raw_points, 1));
fprintf('平滑表面 Z 范围: %.6g ~ %.6g um\n', min(surface_points(:,3)), max(surface_points(:,3)));
fprintf('原始深度 Z 范围: %.6g ~ %.6g um\n', min(raw_points(:,3)), max(raw_points(:,3)));

fprintf('\n已导出点云文件：\n');
fprintf('- %s\n', surface_csv);
fprintf('- %s\n', surface_txt);
fprintf('- %s\n', surface_asc);
fprintf('- %s\n', raw_csv);
fprintf('- %s\n', raw_txt);
fprintf('- %s\n', raw_asc);

export_total_elapsed = toc(export_total_timer);
export_total_h = floor(export_total_elapsed / 3600);
export_total_m = floor(mod(export_total_elapsed, 3600) / 60);
export_total_s = mod(export_total_elapsed, 60);
fprintf('\n点云导出总耗时: %02d:%02d:%05.2f (%.2f s)\n', ...
    export_total_h, export_total_m, export_total_s, export_total_elapsed);

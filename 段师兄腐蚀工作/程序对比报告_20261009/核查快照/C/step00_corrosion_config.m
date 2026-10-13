function cfg = step00_corrosion_config()
%STEP00_CORROSION_CONFIG 腐蚀点云处理的唯一参数入口。
%
% 使用方法：
%   cfg = step00_corrosion_config();
%
% 修改原则：
%   1. 普通使用只修改“常用参数”；
%   2. “高级参数”会改变腐蚀坑识别或分水岭定义，修改后应重新验证；
%   3. 几何长度单位统一为 mm，坑深输出时可按配置转换为 um。

persistent cached_cfg
if ~isempty(cached_cfg)
    cfg = cached_cfg;
    return;
end

root = fileparts(mfilename('fullpath'));
cfg = struct();
cfg.project_root = root;

%% ==================== 1. 输入文件（常用） ====================
% 190 mm点云：必须同时包含左侧平坦参考区和中间腐蚀区。
cfg.input.point_cloud_190_pattern = fullfile(root, '*190*chongxin*');
% 50 mm点云：用于腐蚀坑识别、深度和深径比统计。
cfg.input.point_cloud_50_file = fullfile(root, 'C17_100d_z_50_chongxin.txt');
% 两个边缘处理脚本默认读取同一份50 mm点云，避免路径不一致。
cfg.input.edge_processing_file = cfg.input.point_cloud_50_file;

%% ==================== 2. 点云预处理（常用） ====================
% 规则网格间距。越小网格越密、运算越慢，坑边界和坑径越精细。
cfg.preprocessing.grid_resolution_mm = 0.3;
% 网格化后删除的边缘行列数。
cfg.preprocessing.trim_edge_rows = 3;
% true保留旧代码前侧删3行、后侧删4行的行为，保证历史结果不变。
cfg.preprocessing.trim_legacy_asymmetric = true;
% 主流程高斯平滑。越大越平滑，小坑和噪声越容易消失。
cfg.preprocessing.main_gaussian_sigma = 2.0;
% 点云四周删除比例；0.05表示每一侧删除总范围的5%。
cfg.preprocessing.remove_edge_ratio = 0.05;
% 读取点云时是否将原始Z坐标取负，对应旧代码 z=-data(:,3)。
cfg.preprocessing.invert_z_on_load = true;
% 反转脚本是否执行 z_new=z_max+z_min-z_old。
cfg.preprocessing.reverse_z_after_edge_removal = true;
% 散乱点网格插值方法：linear、nearest或natural。
cfg.preprocessing.interpolation_method = 'linear';
% NaN填补方法，当前保持nearest。
cfg.preprocessing.missing_fill_method = 'nearest';

%% ==================== 3. 均匀腐蚀参考区（高级） ====================
% 左侧平坦参考区域使用的列数。
cfg.reference.flat_column_count = 200;
% 参考面高度=min+ratio*(max-min)，旧代码取0.2。
cfg.reference.flat_height_ratio = 0.2;
% 中央腐蚀区域列数，旧代码共取168列。
cfg.reference.corrosion_column_count = 168;

%% ==================== 4. 腐蚀坑极值识别（常用） ====================
% 极值相对邻域均值的最低显著度；越小识别的浅小坑越多。
cfg.pit_detection.min_prominence = 0.001;
% 两个坑中心的最小网格距离；越小允许识别更密集的坑。
cfg.pit_detection.min_distance = 15;
% 局部极值搜索邻域；越小越关注局部小坑。
cfg.pit_detection.neighborhood = [12, 12];
% 极值遍历时跳过的最外层网格数量。
cfg.pit_detection.edge_margin = 1;
% 当前坑深参考面和坑径定义，保持原公式。
cfg.pit_detection.depth_reference_mode = 'global_minimum';
cfg.pit_detection.diameter_mode = 'mean_xy_span';

%% ==================== 5. 分水岭边界（高级） ====================
% 距离背景阈值。代码条件是 distance > threshold*max(distance)。
cfg.watershed.threshold = 0.3;
% 分水岭梯度计算前的轻度高斯平滑，不等于主流程sigma。
cfg.watershed.gaussian_sigma = 0.5;
% 局部对比度窗口边长，旧代码为ones(5)。
cfg.watershed.local_contrast_window = 5;
% 局部梯度阈值系数；越大越容易屏蔽平缓小起伏。
cfg.watershed.local_contrast_factor = 0.01;
% 平缓区域被设置的梯度屏障值。
cfg.watershed.gradient_barrier_value = 255;
cfg.watershed.gradient_operator = 'sobel';
cfg.watershed.boundary_holes = 'noholes';

%% ==================== 6. 分布检验（常用） ====================
% mm转um的换算系数。
cfg.distribution.depth_mm_to_um = 1000;
% 深径比使用log(1/sjb)，分子保持1。
cfg.distribution.sjb_reciprocal_numerator = 1.0;
% 直方图柱宽。越小柱子越细，但不会增加原始腐蚀坑样本数。
cfg.distribution.hist_bin_width = 0.1;
cfg.distribution.hist_normalization = 'pdf';
cfg.distribution.hist_face_color = [0.5, 0.8, 1.0];
cfg.distribution.fit_distribution = 'Normal';
cfg.distribution.fit_curve_points = 1000;
cfg.distribution.fit_line_width = 2;

%% ==================== 7. 绘图外观（常用） ====================
cfg.figure.point_cloud_marker_size = 10;
cfg.figure.deleted_point_marker_size = 20;
cfg.figure.extrema_marker_size = 20;
cfg.figure.boundary_marker_size = 5;
cfg.figure.extrema_cross_size = 10;
cfg.figure.extrema_cross_line_width = 2;
cfg.figure.boundary_line_width = 1;
cfg.figure.fit_line_width = 2;
cfg.figure.contour_levels = 20;
cfg.figure.extrema_figure_position = [100, 100, 1200, 500];
cfg.figure.reverse_compare_position = [100, 100, 1200, 400];
cfg.figure.surface_colormap = 'jet';
cfg.figure.processed_surface_colormap = 'turbo';
cfg.figure.watershed_colormap = 'jet';
cfg.figure.surface_view = [-30, 45];
cfg.figure.watershed_view = [-30, 60];
cfg.figure.processed_surface_view = 3;
cfg.figure.font_size = 15;
cfg.figure.font_name = 'Times New Roman';
cfg.figure.surface_clim = [-0.5, 0];

%% ==================== 8. APDL点云导出（常用） ====================
% 默认与点云网格分辨率共用同一物理间距。
cfg.apdl.dx_mm = cfg.preprocessing.grid_resolution_mm;
cfg.apdl.dy_mm = cfg.preprocessing.grid_resolution_mm;
cfg.apdl.grid_matrix_variable = 'Z_filled';
cfg.apdl.x_start_mm = 0;
cfg.apdl.y_start_mm = 0;
cfg.apdl.delimiter = sprintf('\t');
cfg.apdl.precision = '%.6f';
cfg.apdl.newline = 'pc';

%% ==================== 9. 输出文件（常用） ====================
cfg.output.pit_statistics_excel = fullfile(root, '腐蚀坑深度统计.xlsx');
cfg.output.edge_removed_txt = fullfile(root, 'point_cloud_without_edges.txt');
cfg.output.edge_reversed_txt = fullfile(root, 'point_cloud_reversed_z.txt');
cfg.output.apdl_x_txt = fullfile(root, 'DIANYUN_X.txt');
cfg.output.apdl_y_txt = fullfile(root, 'DIANYUN_Y.txt');
cfg.output.apdl_z_txt = fullfile(root, 'DIANYUN_Z.txt');

validate_config(cfg);
cached_cfg = cfg;
end

function validate_config(cfg)
% 在正式运行前尽早发现明显的错误参数。
assert(cfg.preprocessing.grid_resolution_mm > 0, '网格分辨率必须大于0。');
assert(cfg.preprocessing.trim_edge_rows >= 0, '裁边行列数不能为负数。');
assert(cfg.preprocessing.remove_edge_ratio >= 0 && ...
    cfg.preprocessing.remove_edge_ratio < 0.5, ...
    '边缘删除比例必须在[0,0.5)范围内。');
assert(cfg.pit_detection.min_prominence >= 0, 'MinProminence不能为负数。');
assert(cfg.pit_detection.min_distance >= 0, 'MinDistance不能为负数。');
assert(all(cfg.pit_detection.neighborhood >= 1), 'Neighborhood必须为正数。');
assert(cfg.watershed.threshold > 0 && cfg.watershed.threshold < 1, ...
    '分水岭阈值必须在(0,1)范围内。');
assert(cfg.distribution.hist_bin_width > 0, '直方图柱宽必须大于0。');
end

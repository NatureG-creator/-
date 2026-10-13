clear
cfg = step00_corrosion_config();
%mean_distance需要获取两个平面一个参考面，一个腐蚀面
%将会得到腐蚀面的平均腐蚀深度即
%mean_distance=junzhijisuan('N5-60d-cankao.txt','N5-60d-fushi.txt');
%注意此时我所设置的分辨率是0.3，即一个网格代表0.3mm
%但是所用函数得到的是按照1mm来算的，所以对于sjb要乘以2，shengdu不变
grid_resolution = cfg.preprocessing.grid_resolution_mm;

% 由190 mm点云计算均匀腐蚀深度。
% 190 mm数据必须包含左侧平坦参考区和中间约50 mm腐蚀段。
files_190 = dir(cfg.input.point_cloud_190_pattern);
if isempty(files_190)
    error('未找到190 mm点云文件，请确认当前文件夹中存在包含190和chongxin的文件。');
end
file_190 = fullfile(files_190(1).folder, files_190(1).name);
[Z190,~] = shujuguiyi(file_190, grid_resolution, ...
    cfg.preprocessing.trim_edge_rows, cfg);
[junyunfushi,H_flat,H_corroded] = jisuan_190(Z190, cfg);

% 由50 mm点云计算腐蚀坑深度和不均匀腐蚀参数。
[Z,Z_filled] = shujuguiyi(cfg.input.point_cloud_50_file, ...
    grid_resolution, cfg.preprocessing.trim_edge_rows, cfg);
Z_filled_raw_for_export = Z_filled; % 只留存平滑前矩阵，原平滑和计算不改变。
    % 高斯平滑处理
    sigma = cfg.preprocessing.main_gaussian_sigma;
    Z_filled = imgaussfilt(Z_filled, sigma);
 F_filled=Z_filled;
%3jisuan_190(Z)%该函数会统计平坦面20%分位数的高度并和腐蚀面高度相减

params = {'MinProminence', cfg.pit_detection.min_prominence, ...
    'MinDistance', cfg.pit_detection.min_distance, ...
    'Neighborhood', cfg.pit_detection.neighborhood};
[shengdu,sjb,zhijin,max_locs,min_locs,boundaries,boundary_coords] = ...
    jixiantiqu_3D(-Z_filled, params, cfg.watershed.threshold, ...
    grid_resolution, cfg);

% 每个腐蚀坑的深度
pit_depth_mm = shengdu;
pit_depth_um = shengdu .* cfg.distribution.depth_mm_to_um;

disp('各腐蚀坑深度（μm）：');
disp(pit_depth_um);

disp(['平均坑深：', num2str(mean(pit_depth_um)), ' μm']);
disp(['最大坑深：', num2str(max(pit_depth_um)), ' μm']);
disp(['最小坑深：', num2str(min(pit_depth_um)), ' μm']);

% 保存全部腐蚀坑结果
result = table((1:numel(shengdu))', pit_depth_mm, pit_depth_um, ...
    'VariableNames', {'Pit_ID','Depth_mm','Depth_um'});
writetable(result, cfg.output.pit_statistics_excel);

jicha=max(Z(:))-min(Z(:));
bujunyun=mean(-Z_filled(:)-min(-Z_filled(:)));

disp(['不均匀腐蚀深度：',num2str(bujunyun),' mm']);
disp(['均匀腐蚀深度：',num2str(junyunfushi),' mm']);
disp(['均匀腐蚀深度：',num2str(junyunfushi*1000),' μm']);
%% ===== 计算平均总腐蚀深度（参考面高度差法） =====

% 190 mm点云中参考区和腐蚀区的平均高度
H_flat_mean = mean(H_flat(:), 'omitnan');
H_corroded_mean = mean(H_corroded(:), 'omitnan');

% 有符号平均高度差
avg_total_signed_mm = H_flat_mean - H_corroded_mean;

% 高度差的绝对值，先用于核对量级
avg_total_depth_mm = abs(avg_total_signed_mm);
avg_total_depth_um = avg_total_depth_mm * 1000;

fprintf('参考区与腐蚀区平均高度差：%.4f mm\n', ...
    avg_total_signed_mm);

fprintf('平均总腐蚀深度（高差绝对值）：%.4f mm\n', ...
    avg_total_depth_mm);

fprintf('平均总腐蚀深度（高差绝对值）：%.4f μm\n', ...
    avg_total_depth_um);

if avg_total_signed_mm < 0
    warning('平均高差为负，请核对点云Z轴方向后再用于GA校准。');
end
disp(['平均腐蚀坑深度：',num2str(mean(pit_depth_mm,'omitnan')),' mm']);
disp(['平均腐蚀坑深度：',num2str(mean(pit_depth_um,'omitnan')),' μm']);
% jsb=log(1./sjb);
% shengdu2=log(shengdu.*1000);
% fenbujianyan(jsb)
% fenbujianyan(shengdu2) 

% 径深比对数
jsb = log(cfg.distribution.sjb_reciprocal_numerator ./ sjb);
jsb = jsb(isfinite(jsb));
fenbujianyan(jsb, cfg);

% 腐蚀坑深度：mm转为μm后取自然对数
shengdu2 = log(shengdu .* cfg.distribution.depth_mm_to_um);
shengdu2 = shengdu2(isfinite(shengdu2));
fenbujianyan(shengdu2, cfg);

% untitled.m
%   → shujuguiyi.m
%   → jixiantiqu_3D.m
%       → fenshuiling_boundry.m
%       → fushikengtiqu.m
%   → fenbujianyan.m

% 原程序全部计算和出图结束后，仅导出实测目标供代码6读取。
[ca_target_path,ca_target_export] = export_original_ca_target( ...
    Z_filled_raw_for_export,Z_filled,junyunfushi,shengdu,sjb,zhijin, ...
    max_locs,cfg,struct('point_cloud_190',file_190, ...
    'point_cloud_50',cfg.input.point_cloud_50_file));

clear
clear step00_corrosion_config % 修改配置后重新加载，避免persistent缓存。
cfg=step00_corrosion_config();
grid_resolution=cfg.preprocessing.grid_resolution_mm;
figures_before=findall(groot,'Type','figure'); % 只保存本次新图，不动原来已打开的图窗。

%% 第1步：核对190 mm原始扫描与50 mm子集，禁止独立齐平后拼接高度。
files_190=dir(cfg.input.point_cloud_190_pattern);
files_190=files_190(~[files_190.isdir]);
assert(numel(files_190)==1,'input:Ambiguous190','必须指定唯一190 mm扫描文件，不能默选第一份。');
file_190=fullfile(files_190(1).folder,files_190(1).name);
points190=readmatrix(file_190,'FileType','text');
points50=readmatrix(cfg.input.point_cloud_50_file,'FileType','text');
assert(size(points190,2)>=3 && size(points50,2)>=3 && ...
    all(isfinite(points190(:,1:3)),'all') && all(isfinite(points50(:,1:3)),'all'), ...
    'input:InvalidXYZ','扫描前三列XYZ必须为有限数值。');
assert(all(ismember(points50(:,1:3),points190(:,1:3),'rows')), ...
    'input:NotSubset','50 mm文件不是190 mm扫描的同坐标XYZ子集，先核对来源，不自动拼接。');

%% 第2步：只齐平190 mm一次，沿用原插值、补洞、裁边方法。
cfg.figure.show_preprocessing_surface=false; % 此处还是高程，最终才画实际深度。
[Z190,Z190_filled,grid190]=shujuguiyi(file_190,grid_resolution, ...
    cfg.preprocessing.trim_edge_rows,cfg);
[Z_filled,Z_filled_raw_for_export,junyunfushi,H_flat,processing]= ...
    prepare_positive_corrosion_surface(Z190_filled,cfg);
Z=Z190(:,processing.crop_columns)-H_flat; % 带空洞矩阵也使用同一参考零面。
F_filled=Z_filled;
X=grid190.X_mm(:,processing.crop_columns);X=X-X(1,1);
Y=grid190.Y_mm(:,processing.crop_columns);Y=Y-Y(1,1);

%% 第3步：保留原曲面外观，参考面为零、向内深度为正，色标使用实际数值。
h_depth=figure('Name','同参考面正向腐蚀深度');
surf(X,Y,Z_filled,'EdgeColor','none');shading interp;grid off;
colormap(cfg.figure.processed_surface_colormap);colorbar;
set(gca,'FontSize',cfg.figure.font_size,'FontName',cfg.figure.font_name);
xlabel('X / mm');ylabel('Y / mm');zlabel('D / mm'); % 保留Times数字字体，避免中文显示方框。
axis tight;view(cfg.figure.processed_surface_view);

%% 第4步：红点检测正深度极大值，保留原分水岭及全局最小参考坑深规则。
params={'MinProminence',cfg.pit_detection.min_prominence, ...
    'MinDistance',cfg.pit_detection.min_distance,'Neighborhood',cfg.pit_detection.neighborhood};
[shengdu,sjb,zhijin,max_locs,min_locs,boundaries,boundary_coords]= ...
    jixiantiqu_3D(Z_filled,params,cfg.watershed.threshold,grid_resolution,cfg);
pit_depth_mm=shengdu;pit_depth_um=shengdu*1000;
bujunyun=mean(Z_filled(:)-junyunfushi); % 平均总深度-最浅深度。
avg_total_depth_mm=mean(Z_filled(:));avg_total_depth_um=avg_total_depth_mm*1000;
jicha=max(Z_filled(:))-min(Z_filled(:));
fprintf('均匀腐蚀分量（最浅深度）：%.6f mm\n',junyunfushi);
fprintf('不均匀腐蚀深度：%.6f mm\n',bujunyun);
fprintf('平均总腐蚀深度：%.6f mm\n',avg_total_depth_mm);
fprintf('平均局部坑深：%.4f μm（不等于均匀腐蚀深度）\n',mean(pit_depth_um));
fprintf('实际分析范围：%.3f × %.3f mm，矩阵%d×%d\n', ...
    processing.x_span_mm,processing.y_span_mm,size(Z_filled,1),size(Z_filled,2));
if min(Z_filled_raw_for_export(:))<0
    warning('reference:Negative','参考深度含负值；保留原数值，仅诊断，不可校准，请核对参考区。');
end

%% 第5步：坑样本取自然对数，保持直方图、正态拟合及Q-Q图。
jsb=log(1./sjb);jsb=jsb(isfinite(jsb));
shengdu2=log(shengdu*1000);shengdu2=shengdu2(isfinite(shengdu2));
fenbujianyan(jsb,cfg);fenbujianyan(shengdu2,cfg);
%% ============================================================
%% 输出完整腐蚀形貌统计结果
%% ============================================================

fprintf('\n========== 腐蚀形貌统计结果 ==========\n');

% 1. 腐蚀坑深度统计
valid_pit_um = pit_depth_um(isfinite(pit_depth_um) & pit_depth_um > 0);

if ~isempty(valid_pit_um)
    fprintf('腐蚀坑数量：%d\n', numel(valid_pit_um));
    fprintf('各腐蚀坑深度（μm）：\n');
    disp(valid_pit_um(:));

    fprintf('平均坑深：%.4f μm\n', mean(valid_pit_um));
    fprintf('最大坑深：%.4f μm\n', max(valid_pit_um));
    fprintf('最小坑深：%.4f μm\n', min(valid_pit_um));
else
    warning('未识别到有效的正腐蚀坑深度。');
end

% 2. 整体腐蚀深度统计
fprintf('不均匀腐蚀深度：%.5f mm\n', bujunyun);

fprintf('均匀腐蚀分量：%.5f mm\n', junyunfushi);
fprintf('均匀腐蚀分量：%.4f μm\n', junyunfushi*1000);

fprintf('平均总腐蚀深度：%.5f mm\n', avg_total_depth_mm);
fprintf('平均总腐蚀深度：%.4f μm\n', avg_total_depth_um);

% 3. 腐蚀坑径深比对数分布
if numel(jsb) >= 2
    [mu_jsb, sigma_jsb] = normfit(jsb);

    fprintf('径深比对数均值 μ = %.5f\n', mu_jsb);
    fprintf('径深比对数标准差 σ = %.5f\n', sigma_jsb);
end

% 4. 腐蚀坑深度对数分布
if numel(shengdu2) >= 2
    [mu_depth, sigma_depth] = normfit(shengdu2);

    fprintf('坑深对数均值 μ = %.5f\n', mu_depth);
    fprintf('坑深对数标准差 σ = %.5f\n', sigma_depth);
end

fprintf('======================================\n');
%% 第6步：结果单独存放，不覆盖原Excel、MAT和图片。
output_folder=fullfile(cfg.project_root,['正向深度结果_', ...
    char(datetime('now','Format','yyyyMMdd_HHmmss_SSS'))]);
mkdir(output_folder);
result=table((1:numel(shengdu))',pit_depth_mm(:),pit_depth_um(:),zhijin(:),sjb(:), ...
    'VariableNames',{'Pit_ID','Depth_mm','Depth_um','Diameter_mm','Depth_over_diameter'});
writetable(result,fullfile(output_folder,'腐蚀坑深度统计.xlsx'));
save(fullfile(output_folder,'正向腐蚀深度与指标.mat'),'Z','Z_filled','Z_filled_raw_for_export', ...
    'X','Y','H_flat','processing','junyunfushi','bujunyun','avg_total_depth_mm', ...
    'shengdu','sjb','zhijin','jsb','shengdu2','max_locs','cfg');
%% ===== 安全导出图片，避免重复导出无效图窗 =====

figures = setdiff( ...
    findall(groot,'Type','figure'), figures_before);

for k = 1:numel(figures)

    h = figures(k);

    % 检查图窗是否有效
    if ~isgraphics(h,'figure')
        warning('第%d个图窗已关闭，跳过导出。',k);
        continue;
    end

    % 提前判断图窗类型
    is_depth = isequal(h,h_depth);

    is_extrema = strcmp( ...
        get(h,'Name'),'腐蚀深度极值与等高线');

    filename = fullfile(output_folder, ...
        sprintf('图_%02d.png',k));

    try
        % 每张图只导出一次
        exportgraphics(h,filename,'Resolution',180);

        % 直接复制已生成的图片，不再重复导出图窗
        if is_depth
            copyfile(filename,fullfile( ...
                output_folder,'正向三维曲面.png'));
        end

        if is_extrema
            copyfile(filename,fullfile( ...
                output_folder,'红点极值与等高线.png'));
        end

    catch ME
        warning('第%d张图片导出失败：%s',k,ME.message);
    end
end

%% 第7步：把同一矩阵及坑样本导出给代码6，CA-GA使用统一MATLAB评价口径。
sources=struct('point_cloud_190',file_190,'point_cloud_50',cfg.input.point_cloud_50_file, ...
    'processing',processing,'subset_xyz_verified',true);
[ca_target_path,ca_target_export]=export_original_ca_target( ...
    Z_filled_raw_for_export,Z_filled,junyunfushi,shengdu,sjb,zhijin,max_locs,cfg,sources);
fprintf('本次结果：%s\n',output_folder);

clear
clear step00_corrosion_config % 修改配置后重新加载，避免persistent缓存。
cfg=step00_corrosion_config();
grid_resolution=cfg.preprocessing.grid_resolution_mm;
figures_before=findall(groot,'Type','figure'); % 只保存本次新图，不动原来已打开的图窗。

%% 第1步：核对文件来源；来自同一扫描也不代表独立齐平后的高度基准相同。
files_190=dir(cfg.input.point_cloud_190_pattern);
files_190=files_190(~[files_190.isdir]);
assert(isscalar(files_190),'input:Ambiguous190','必须指定唯一190 mm扫描文件，不能默选第一份。');
file_190=fullfile(files_190(1).folder,files_190(1).name);
points190=readmatrix(file_190,'FileType','text');
points50=readmatrix(cfg.input.point_cloud_50_file,'FileType','text');
assert(size(points190,2)>=3 && size(points50,2)>=3 && ...
    all(isfinite(points190(:,1:3)),'all') && all(isfinite(points50(:,1:3)),'all'), ...
    'input:InvalidXYZ','扫描前三列XYZ必须为有限数值。');
assert(all(ismember(points50(:,1:3),points190(:,1:3),'rows')), ...
    'input:NotSubset','50 mm文件不是190 mm扫描的同坐标XYZ子集，先核对来源，不自动拼接。');

%% 第2步：190 mm单独核对参考区；50 mm恢复原独立齐平与平滑流程。
cfg.figure.show_preprocessing_surface=false; % 此处还是高程，稍后画正向相对深度。
[Z190,Z190_filled,grid190]=shujuguiyi(file_190,grid_resolution, ...
    cfg.preprocessing.trim_edge_rows,cfg);
[uniform_190_diagnostic_mm,H_flat,H_corroded,columns190]=jisuan_190(Z190,cfg);
[Z,H_raw,grid50]=shujuguiyi(cfg.input.point_cloud_50_file,grid_resolution, ...
    cfg.preprocessing.trim_edge_rows,cfg);
if cfg.preprocessing.main_gaussian_sigma>0
    H=imgaussfilt(H_raw,cfg.preprocessing.main_gaussian_sigma); % 只平滑一次，保持旧50 mm坑样本。
else
    H=H_raw;
end
components=height_depth_components(H); % 50 mm未腐蚀参考高度未知，不拼接190 mm的H_flat。
Z_filled=H; % 保留原变量含义：齐平后的平滑高程，不是深度。
display_depth_mm=components.relative_depth_mm;
Z_filled_raw_for_export=max(H_raw(:))-H_raw; % 只用于相对起伏诊断，不是绝对总深度。
junyunfushi=components.uniform_depth_mm;
X=grid50.X_mm;X=X-X(1,1);
Y=grid50.Y_mm;Y=Y-Y(1,1);
processing=struct('analysis_input','independently aligned 50 mm scan', ...
    'reference_verified',false,'x_span_mm',max(X(:))-min(X(:)), ...
    'y_span_mm',max(Y(:))-min(Y(:)), ...
    'reference_190_diagnostic_mm',uniform_190_diagnostic_mm,'reference_columns_190',columns190);
F_filled=Z_filled;

%% 第3步：正向显示D_relative=max(H)-H，零点是腐蚀表面最高点，不是未腐蚀面。
h_depth=figure('Name','正向相对腐蚀深度');
surf(X,Y,display_depth_mm,'EdgeColor','none');shading interp;grid off;
colormap(cfg.figure.processed_surface_colormap);colorbar;
set(gca,'FontSize',cfg.figure.font_size,'FontName',cfg.figure.font_name);
xlabel('X / mm');ylabel('Y / mm');zlabel('D_{relative} / mm'); % 相对深度标签避免与总深度混淆。
axis tight;view(cfg.figure.processed_surface_view);

%% 第4步：恢复-H找极大值，即H坑底；第六参数仅平移显示，检测矩阵绝不改。
params={'MinProminence',cfg.pit_detection.min_prominence, ...
    'MinDistance',cfg.pit_detection.min_distance,'Neighborhood',cfg.pit_detection.neighborhood};
[shengdu,sjb,zhijin,max_locs,min_locs,boundaries,boundary_coords]= ...
    jixiantiqu_3D(-H,params,cfg.watershed.threshold,grid_resolution,cfg,display_depth_mm);
pit_depth_mm=shengdu;pit_depth_um=shengdu*1000;
bujunyun=components.nonuniform_depth_mm; % 原公式max(H)-mean(H)，与整体高程平移无关。
avg_total_depth_mm=components.mean_total_depth_mm;avg_total_depth_um=avg_total_depth_mm*1000;
jicha=max(Z_filled(:))-min(Z_filled(:));
fprintf('均匀腐蚀分量（同基准参考未确认）：%.6f mm\n',junyunfushi);
fprintf('不均匀腐蚀深度：%.6f mm\n',bujunyun);
fprintf('平均总腐蚀深度：%.6f mm\n',avg_total_depth_mm);
fprintf('平均坑深（表面最高点到坑底）：%.4f μm\n',mean(pit_depth_um));
fprintf('实际分析范围：%.3f × %.3f mm，矩阵%d×%d\n', ...
    processing.x_span_mm,processing.y_span_mm,size(Z_filled,1),size(Z_filled,2));
fprintf('190 mm原规则参考诊断：%.6f mm（有符号，不拼接50 mm基准）\n',uniform_190_diagnostic_mm);
warning('reference:Unverified','均匀/平均总深度NaN表示参考面未确认，不是0；坑样本可用，暂不提交完整CA-GA目标。');

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
    'shengdu','sjb','zhijin','jsb','shengdu2','max_locs','cfg', ...
    'H_raw','H','display_depth_mm','components','uniform_190_diagnostic_mm', ...
    'Z190','Z190_filled','grid190','grid50','H_corroded');
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

%% 第7步：导出高程、相对深度和原坑样本；参考面未确认时明确禁止完整CA-GA校准。
sources=struct('point_cloud_190',file_190,'point_cloud_50',cfg.input.point_cloud_50_file, ...
    'processing',processing,'subset_xyz_verified',true,'depth_kind','relative_to_surface_top', ...
    'height_raw_mm',H_raw,'height_smoothed_mm',H);
[ca_target_path,ca_target_export]=export_original_ca_target( ...
    Z_filled_raw_for_export,display_depth_mm,junyunfushi,shengdu,sjb,zhijin,max_locs,cfg,sources);
fprintf('本次结果：%s\n',output_folder);

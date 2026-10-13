function result=extract_original_ca_metrics(depth_um,spacing_um,analysis_config,valid_mask,cfg)
% 模拟评价适配：仅做单位转换，实际检测/分割/坑深调用原函数链。
if nargin<5||isempty(cfg),cfg=step00_corrosion_config();end
assert(all(isfinite(depth_um(:)))&&ismatrix(depth_um),'original:Depth','需要完整有限深度矩阵。');
assert(isequal(size(valid_mask),size(depth_um))&&all(valid_mask(:)), ...
    'original:Mask','原算法统计全部补齐格点，不能擅自换有效掩膜口径。');
assert(abs(spacing_um-cfg.preprocessing.grid_resolution_mm*1000)<1e-9,'original:Spacing','网格间距不匹配。');
expected=[cfg.preprocessing.main_gaussian_sigma,cfg.pit_detection.min_prominence*1000, ...
    cfg.pit_detection.min_distance,cfg.pit_detection.neighborhood(1),cfg.watershed.threshold, ...
    cfg.watershed.gaussian_sigma,cfg.pit_detection.edge_margin];
keys={'gaussian_sigma','min_prominence_um','min_distance','neighborhood','watershed_threshold','watershed_sigma','edge_margin'};
actual=cellfun(@(s)analysis_config.(s),keys);
assert(all(abs(actual-expected)<1e-10)&&all(cfg.pit_detection.neighborhood==analysis_config.neighborhood), ...
    'original:Config','MATLAB与Python识别设置不同，不替换原配置。');
% 第1步：um转mm正深度；实测与模拟均输入未平滑D，仅在这里平滑一次。
sigma=cfg.preprocessing.main_gaussian_sigma;
assert(isscalar(sigma)&&isfinite(sigma)&&sigma>=0,'original:Sigma','主平滑sigma必须为非负有限标量。');
data=double(depth_um)/1000;
if sigma>0,data=imgaussfilt(data,sigma);end % sigma=0时实测与模拟都关闭主平滑。
params={'MinProminence',cfg.pit_detection.min_prominence,'MinDistance',cfg.pit_detection.min_distance, ...
    'Neighborhood',cfg.pit_detection.neighborhood};
% 第2步：原函数会创建图；后台评价只隐藏并清理新图，不改原绘图语句。
old_visible=get(groot,'defaultFigureVisible');old_figs=findall(groot,'Type','figure');
cleanup=onCleanup(@()restore_figures(old_visible,old_figs)); %#ok<NASGU>
set(groot,'defaultFigureVisible','off');
[h,sjb,diameter,peaks,~,boundaries,coords]=jixiantiqu_3D(data,params,cfg.watershed.threshold,spacing_um/1000,cfg);
% 第3步：遵循原log过滤；有效坑必须同时有正深度和正直径。
ld=log(h(:)*1000);lr=log(1./sjb(:));good=isfinite(ld)&isfinite(lr)&diameter(:)>0;
ld=ld(good);lr=lr(good);processed=data*1000;reference=min(processed(:));
result=struct('depth_um',double(depth_um),'processed_depth_um',processed,'valid_mask',logical(valid_mask), ...
    'spacing_um',double(spacing_um),'analysis_config',analysis_config, ...
    'target_data',[mean(processed(:)),mean(processed(:)-reference),sample_mean(lr),sample_mean(ld),sample_sd(lr),sample_sd(ld)], ...
    'uniform_depth_um',reference,'max_depth_um',max(processed(:)), ...
    'pit_count',nnz(good),'pit_density_per_mm2',nnz(good)/(numel(data)*(spacing_um/1000)^2), ...
    'log_ratio',lr,'log_depth',ld,'pit_depth_um',h(good)*1000,'pit_diameter_um',diameter(good)*1000, ...
    'pit_centers_rc_matlab',peaks(good,:),'peaks_rc_matlab',peaks,'labels',zeros(size(data)), ...
    'boundaries',boundaries,'boundary_coords',{coords},'label_semantics','region labels not exported by original function', ...
    'extraction_backend','MATLAB_native','extraction_method','original_matlab_positive_depth_v2', ...
    'negative_fraction',mean(processed(:)<0),'raw_min_depth_um',min(depth_um(:)), ...
    'depth_quantiles_um',quantile(processed(:),[.05 .25 .5 .75 .95]));
end

function restore_figures(visible,old_figs)
set(groot,'defaultFigureVisible',visible);
new_figs=setdiff(findall(groot,'Type','figure'),old_figs);delete(new_figs);
end
function value=sample_mean(x)
if isempty(x),value=NaN;else,value=mean(x);end
end
function value=sample_sd(x)
if numel(x)<2,value=NaN;else,value=std(x,0);end
end

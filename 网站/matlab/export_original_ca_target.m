function [target_path,result]=export_original_ca_target(raw_filled,smooth_filled,uniform_mm, ...
    pit_depth_mm,sjb,diameter_mm,max_locs,cfg,sources,output_base)
% 导出原程序已经算出的数据；不重新识别坑、不改图形、不修饰负值。
if nargin<10
	output_base='D:/research/files/腐蚀代码7_高速版_MATLAB实测接口/01_MATLAB实测目标接口/实测目标';
end
task_output = getenv('CORROSION_OUTPUT_BASE');
if ~isempty(task_output), output_base = task_output; end
% 每次导出由使用者手动命名，避免不同试件或腐蚀时间混在时间戳目录中。
task_name = getenv('CORROSION_DATA_NAME');
if ~isempty(task_name)
    name_answer = {task_name};
else
    name_answer=inputdlg({'本次数据名称（例如 C17_100d_z_100d）：'},'保存MATLAB目标数据',[1 50], ...
        {['C17_',char(datetime('now','Format','yyyyMMdd_HHmmss'))]});
end
if isempty(name_answer)
    error('export:NameCancelled','已取消本次MATLAB目标保存。');
end
data_name=strtrim(name_answer{1});
data_name=regexprep(data_name,'[\\/:*?"<>|]','_');
assert(~isempty(data_name),'export:EmptyName','数据名称不能为空。');
assert(isequal(size(raw_filled),size(smooth_filled))&&all(isfinite(raw_filled(:)))&& ...
    all(isfinite(smooth_filled(:))),'export:InvalidSurface','原矩阵必须同尺寸、完整且有限。');
relative_only=isfield(sources,'depth_kind')&&strcmp(sources.depth_kind,'relative_to_surface_top');
legacy_combined=isfield(sources,'legacy_combined_total')&&logical(sources.legacy_combined_total);
assert(isscalar(uniform_mm)&&(isfinite(uniform_mm)||(relative_only&&isnan(uniform_mm))), ...
    'export:InvalidUniform','均匀深度必须为有限标量；仅相对深度诊断允许未知NaN。');
% 第1步：分清相对显示深度与已确认参考面的总深度，绝不自动补均匀分量。
reference=min(smooth_filled(:));
depth_um=raw_filled*1000;
processed=smooth_filled*1000;
nonuniform=mean(smooth_filled(:)-reference)*1000;
ld_all=log(pit_depth_mm(:)*1000);lr_all=log(1./sjb(:));
valid_depth=isfinite(ld_all);valid_ratio=isfinite(lr_all);
assert(numel(valid_depth)==numel(valid_ratio)&&numel(valid_depth)==numel(diameter_mm)&& ...
    size(max_locs,1)==numel(valid_depth),'export:CountMismatch','坑样本与中心数量不对应。');
% 第2步：保留原过滤后的完整样本；不悄悄删掉其中一类样本来凑一致。
ld=ld_all(valid_depth);lr=lr_all(valid_ratio);
joint=valid_depth&valid_ratio&diameter_mm(:)>0;
uniform_um=uniform_mm*1000;
issues={};
if relative_only && ~legacy_combined
    issues{end+1}='50 mm仅有相对深度；未确认同高程基准的未腐蚀参考面，均匀/平均总深度未知。';
elseif ~relative_only && abs(reference-uniform_mm)>1e-10
    issues{end+1}='均匀深度必须等于同一平滑矩阵最小值，不得从另一坐标系拼接。';
end
if min(depth_um(:))<0,issues{end+1}='原始参考深度含负值，请核对参考区与方向，不自动平移。';end
if uniform_um<0,issues{end+1}='原均匀深度为负，请核对190mm参考区和Z方向，不自动取绝对值。';end
if ~isequal(valid_depth,valid_ratio)||nnz(joint)~=nnz(valid_depth)
    issues{end+1}='两类原对数样本的有效坑不一一对应。';
end
if numel(ld)<2||numel(lr)<2,issues{end+1}='有效坑少于两个，无法提供样本标准差。';end
if mean(processed(:))<0,issues{end+1}='平均总深度为负，不能用于CA校准。';end
% 第3步：六值固定顺序；均匀深度与平均坑深另存，避免混为一谈。
vector=[mean(processed(:)),nonuniform,mean(lr),mean(ld),std(lr,0),std(ld,0)];
if relative_only && ~legacy_combined,vector(1)=NaN;end % 仅相对起伏时不能冒充平均总腐蚀深度。
if legacy_combined
    vector(1)=(uniform_mm+nonuniform/1000)*1000; % 明确采用旧程序：均匀分量+不均匀分量。
end
if any(~isfinite(vector)),issues{end+1}='六指标含非有限值。';end
names={'mean_depth_um','nonuniform_depth_um','mu_log_ratio','mu_log_depth','sigma_log_ratio','sigma_log_depth'};
analysis=struct('gaussian_sigma',cfg.preprocessing.main_gaussian_sigma, ...
    'min_prominence_um',cfg.pit_detection.min_prominence*1000, ...
    'min_distance',cfg.pit_detection.min_distance,'neighborhood',cfg.pit_detection.neighborhood(1), ...
    'watershed_threshold',cfg.watershed.threshold,'watershed_sigma',cfg.watershed.gaussian_sigma, ...
    'edge_margin',cfg.pit_detection.edge_margin);
assert(numel(cfg.pit_detection.neighborhood)==2&& ...
    cfg.pit_detection.neighborhood(1)==cfg.pit_detection.neighborhood(2), ...
    'export:Neighborhood','当前Python接口要求方形邻域；不自动改参数。');
assert(cfg.distribution.depth_mm_to_um==1000&&cfg.distribution.sjb_reciprocal_numerator==1, ...
    'export:Units','后续接口要求mm转um=1000，ln径深比=log(1/sjb)。');
% 第4步：原文件与配置成为来源合同，模拟评价必须使用同一原算法。
root=fileparts(mfilename('fullpath'));
files={'untitled.m','shujuguiyi.m','jisuan_190.m','jixiantiqu_3D.m', ...
    'fenshuiling_boundry.m','fushikengtiqu.m','fenbujianyan.m','step00_corrosion_config.m', ...
    'extract_original_ca_metrics.m','export_original_ca_target.m','height_depth_components.m'};
paths=cellfun(@(s)fullfile(root,s),files,'UniformOutput',false);
paths=[paths,{sources.point_cloud_190,sources.point_cloud_50}];
hashes=cellfun(@sha256_file,paths,'UniformOutput',false);
result=struct('extraction_backend','MATLAB_native','extraction_method','original_matlab_positive_depth_v2', ...
    'calibration_ready',isempty(issues),'calibration_issues',{issues}, ...
    'depth_um',depth_um,'processed_depth_um',processed,'valid_mask',true(size(processed)), ...
    'spacing_um',cfg.preprocessing.grid_resolution_mm*1000,'analysis_config',analysis, ...
    'original_config',cfg,'original_Z_filled_raw',raw_filled,'original_Z_filled_smoothed',smooth_filled, ...
    'original_shengdu_mm',pit_depth_mm,'original_sjb',sjb,'original_zhijin_mm',diameter_mm, ...
    'original_max_locs',max_locs,'original_jsb',lr,'original_shengdu2',ld, ...
    'original_uniform_mm',uniform_mm,'original_source_paths',{paths},'original_source_sha256',{hashes}, ...
    'target_data',vector,'metric_names',{names},'uniform_depth_um',uniform_um, ...
    'max_depth_um',max(processed(:)),'log_depth',ld,'log_ratio',lr, ...
    'pit_depth_um',pit_depth_mm(joint)*1000,'pit_diameter_um',diameter_mm(joint)*1000, ...
    'pit_centers_rc_matlab',max_locs(joint,:),'peaks_rc_matlab',max_locs, ...
    'pit_count',nnz(joint),'pit_density_per_mm2',nnz(joint)/(numel(processed)*cfg.preprocessing.grid_resolution_mm^2), ...
    'labels',zeros(size(processed)),'negative_fraction',mean(processed(:)<0), ...
    'raw_min_depth_um',min(depth_um(:)),'depth_quantiles_um',quantile(processed(:),[.05 .25 .5 .75 .95]));
result.reference_metadata=struct('depth_unit','um','depth_positive_direction','inward', ...
    'formula','D=(Z190_central-H_flat)*1000; smooth once; uniform=min(smoothed D)', ...
    'reference',cfg.reference,'sources',sources, ...
    'separate_190_and_50_scans',false,'physical_reference_verified',false, ...
    'uniform_origin','minimum of smoothed common-reference depth; no abs', ...
    'filled_cells_included_like_original',true);
if relative_only
    % 相对矩阵单独命名；绝对深度字段用NaN，避免被后续软件误当作总深度。
    assert(isfield(sources,'height_raw_mm')&&isfield(sources,'height_smoothed_mm'), ...
        'export:MissingHeight','相对诊断必须保留原高程矩阵。');
    assert(isequal(size(sources.height_raw_mm),size(raw_filled))&& ...
        isequal(size(sources.height_smoothed_mm),size(smooth_filled)), ...
        'export:HeightSize','原高程和相对显示必须同尺寸。');
    assert(all(isfinite(sources.height_raw_mm(:)))&&all(isfinite(sources.height_smoothed_mm(:)))&& ...
        max(abs(raw_filled-(max(sources.height_raw_mm(:))-sources.height_raw_mm)),[],'all')<1e-10&& ...
        max(abs(smooth_filled-(max(sources.height_smoothed_mm(:))-sources.height_smoothed_mm)),[],'all')<1e-10, ...
        'export:HeightMismatch','相对矩阵必须为原高程max(H)-H，不得改变形貌或符号。');
    result.extraction_method='original_matlab_height_relative_v3';
    result.height_raw_mm=sources.height_raw_mm;
    result.height_smoothed_mm=sources.height_smoothed_mm;
    result.relative_depth_raw_um=depth_um;
    result.relative_depth_um=processed;
    result.depth_um=NaN(size(depth_um));
    result.processed_depth_um=NaN(size(processed));
    result.uniform_depth_um=NaN;
    result.max_depth_um=NaN;
    result.raw_min_depth_um=NaN;
    result.depth_quantiles_um=NaN(1,5);
    result.negative_fraction=NaN;
    result.original_Z_filled_raw=sources.height_raw_mm;
    result.original_Z_filled_smoothed=sources.height_smoothed_mm;
    result.reference_metadata.formula='H: original 50 mm height; D_relative=max(H)-H; total=H0-H only with verified H0';
    result.reference_metadata.separate_190_and_50_scans=true;
    result.reference_metadata.uniform_origin='unknown; separate 190 mm diagnostic is not a verified 50 mm baseline';
end
if legacy_combined
    result.extraction_method='original_matlab_legacy_combined_v4';
    result.calibration_ready=isempty(issues);
    result.target_data=vector;
    result.depth_um=result.relative_depth_raw_um;
    result.processed_depth_um=result.relative_depth_um;
    result.uniform_depth_um=uniform_um;
    result.mean_total_depth_um=vector(1);
    result.reference_metadata.legacy_combined_assumption=true;
    result.reference_metadata.physical_reference_verified=false;
    result.reference_metadata.formula='mean_total_depth_um = uniform_190_mm + mean(relative_50mm_depth_mm); legacy user-approved combination';
    result.reference_metadata.uniform_origin='190 mm old formula; combined with independently aligned 50 mm relative nonuniform depth by explicit legacy assumption';
end
result.source_provenance=struct('source_type','measured_pointcloud', ...
    'extraction_function','original untitled.m + export_original_ca_target', ...
    'original_program_root',root,'original_scan_unchanged',true);
% 第5步：每次独立目录，保存诊断即使不可校准；后端会拒绝不成立的目标。
if ~isfolder(output_base),mkdir(output_base);end
folder=fullfile(output_base,data_name);
assert(~isfolder(folder),'export:Exists','不覆盖已有结果。');mkdir(folder);
target_path=fullfile(folder,'matlab_target.mat');save(target_path,'-struct','result','-v7');
writetable(array2table(vector,'VariableNames',names),fullfile(folder,'six_metrics.csv'));
writetable(table((1:numel(pit_depth_mm))',pit_depth_mm(:),diameter_mm(:),sjb(:),lr_all,ld_all, ...
    'VariableNames',{'pit_id','depth_mm','diameter_mm','depth_over_diameter','ln_diameter_over_depth','ln_depth_um'}), ...
    fullfile(folder,'original_pit_samples.csv'));
fid=fopen(fullfile(folder,'导出说明.txt'),'w','n','UTF-8');assert(fid>=0);cleanup=onCleanup(@()fclose(fid)); %#ok<NASGU>
fprintf(fid,'原算法不改；六值由原样本计算。calibration_ready=%d\n',result.calibration_ready);
for k=1:numel(issues),fprintf(fid,'%s\n',issues{k});end
fid2=fopen(fullfile(output_base,'latest_original_target.txt'),'w','n','UTF-8');assert(fid2>=0);
fprintf(fid2,'%s',target_path);fclose(fid2);
disp(['原程序CA目标导出：',target_path]);
if ~result.calibration_ready
    % 这是预期的安全拦截，不是MATLAB运行失败；保留calibration_ready=false供Python严格拒绝。
    fprintf('[提示] 已导出诊断目标，暂不进入CA-GA：%s\n',strjoin(issues,'；'));
end
end

function hash=sha256_file(path)
fid=fopen(path,'rb');assert(fid>=0,'export:SourceMissing','来源不存在：%s',path);
cleanup=onCleanup(@()fclose(fid)); %#ok<NASGU>
bytes=fread(fid,Inf,'*uint8');engine=java.security.MessageDigest.getInstance('SHA-256');
engine.update(bytes);digest=typecast(engine.digest(),'uint8');
hash=lower(reshape(dec2hex(digest,2)',1,[]));
end

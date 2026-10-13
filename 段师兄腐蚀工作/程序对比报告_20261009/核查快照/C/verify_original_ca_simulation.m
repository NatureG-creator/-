function reports=verify_original_ca_simulation(input_file)
% 使用同一原MATLAB函数复核已保存模拟；只读输入，输出在新时间戳目录。
if nargin<1
    [file,folder]=uigetfile('*.mat','选择simulation_raw_for_matlab.mat');
    assert(~isequal(file,0),'verify:Cancelled','已取消。');input_file=fullfile(folder,file);
end
s=load(input_file);assert(isfield(s,'measured_target_paths'),'verify:MissingTarget','缺少原目标路径。');
output=fullfile(fileparts(input_file),['原MATLAB复核_',char(datetime('now','Format','yyyyMMdd_HHmmss_SSS'))]);
assert(~isfolder(output),'verify:Exists','不覆盖已有结果。');mkdir(output);
reports=cell(size(s.depth_um_sd,1),1);
for k=1:numel(reports)
    t=load(s.measured_target_paths{k});
    assert(strcmp(t.extraction_method,'original_matlab_v1')&&t.calibration_ready,'verify:Target','不是可校准原目标。');
    result=extract_original_ca_metrics(squeeze(s.depth_um_sd(k,:,:)),s.spacing_um, ...
        s.analysis_config,s.valid_mask,t.original_config);
    stored=s.python_metrics(k,:);
    assert(all(abs(result.target_data-stored)<=1e-8+1e-9*abs(stored)), ...
        'verify:Mismatch','原MATLAB复核与保存值不一致。');
    result.physical_relative_errors=abs(result.target_data-s.target_data(k,:))./max(abs(s.target_data(k,:)),1e-12);
    save(fullfile(output,sprintf('stage_%d_verification.mat',k)),'-struct','result','-v7');
    reports{k}=result;disp(result.target_data);disp(result.physical_relative_errors);
end
disp(['复核输出：',output]);
end

function verify_c17_height_depth
% 真实数据回归检查；不运行CA-GA，也不修改原始扫描。
root=fileparts(mfilename('fullpath'));
run(fullfile(root,'untitled.m'));
assert(isequal(size(H),[66 162]),'regression:Grid','50 mm原网格尺寸不一致。');
assert(numel(shengdu)==16,'regression:Pits','原流程应恢复16个坑。');
expected_um=[345.4278;252.1856;401.3421;551.6437;544.1925;265.6459; ...
    287.1560;301.6663;357.9068;266.6894;322.0131;296.3869;310.6103;288.5441;280.3502;290.8086];
assert(max(abs(shengdu(:)*1000-expected_um))<1e-4,'regression:Samples','坑深与旧样本不一致。');
actual=[bujunyun*1000,mean(jsb),mean(shengdu2),std(jsb,0),std(shengdu2,0)];
expected=[262.439686,2.00484918,5.78613670,.629311019,.234813418];
assert(max(abs(actual-expected))<1e-5,'regression:Metrics','旧五项可确定指标未恢复。');
assert(abs(uniform_190_diagnostic_mm-(-.696670317877))<1e-8, ...
    'regression:Reference','190 mm有符号诊断不一致。');
assert(isnan(junyunfushi)&&isnan(avg_total_depth_mm)&&~ca_target_export.calibration_ready, ...
    'regression:NotReady','未确认参考面的总深度不得用于校准。');
fprintf('C17_REGRESSION_OK pits=%d mean_pit_um=%.10f nonuniform_um=%.10f\n', ...
    numel(shengdu),mean(shengdu)*1000,bujunyun*1000);
fprintf('OUTPUT_FOLDER=%s\nTARGET_PATH=%s\n',output_folder,ca_target_path);
close all force;
end

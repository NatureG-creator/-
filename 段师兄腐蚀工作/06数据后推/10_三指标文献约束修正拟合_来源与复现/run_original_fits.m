function run_original_fits(material)
% run_original_fits('Q370NH')
% run_original_fits('Q355')
% 自动加载确定的变量，隔离输出；原始拟合脚本逐字保留。
root_dir = fileparts(mfilename('fullpath'));
assert(any(strcmp(material, {'Q355','Q370NH'})), '材料选项不正确');
scripts = {'Copy_of_shujunihe6_bjf.m', ...
    'Copy_of_shujunihe5_sd.m', 'Copy_of_shujunihe5_jsb.m'};
labels = {'01_不均匀腐蚀深度','02_坑深对数均值','03_径深比对数均值'};
for metric_index = 1:3
    run_one(root_dir, material, scripts{metric_index}, labels{metric_index});
end
end

function run_one(root_dir, material, script_name, metric_name)
% 每个脚本使用独立函数工作区，避免 sd_5/jsb_5 同名变量载入冲突。
input_dir = fullfile(root_dir, '输入数据');
load(fullfile(input_dir, 'sj1.mat'));
load(fullfile(input_dir, 'sj7.mat'));
load(fullfile(input_dir, 'gq2.mat'));
% 原目录同时有镀锌钢与裸钢版本；明确固定裸钢，不让载入顺序决定数据。
load(fullfile(input_dir, 'sj5_bare_steel_sd.mat'));
load(fullfile(input_dir, 'sj5_bare_steel_jsb.mat'));
load(fullfile(input_dir, 'sj2_bjf.mat'));
load(fullfile(input_dir, 'sj3_bjf.mat'));
own = load(fullfile(input_dir, 'drf.mat'));
if strcmp(material, 'Q355')
    drfbjf2 = own.drfbjf2;
    drfsd2 = own.drfsd2;
    drf_jsb2 = own.drf_jsb2;
else
    % 只适配原脚本输入变量名：第1组为 Q370NH，不改求解与权重逻辑。
    drfbjf2 = own.drfbjf1;
    drfsd2 = own.drfsd1;
    drf_jsb2 = own.drf_jsb1;
end
work_dir = fullfile(root_dir, '重新计算结果', material, metric_name);
if ~exist(work_dir, 'dir'), mkdir(work_dir); end
% run 会切换至脚本所在目录，因此在各材料输出目录放完全一致的运行副本。
copyfile(fullfile(root_dir, '原始程序', script_name), fullfile(work_dir, script_name));
old_dir = pwd;
restore_dir = onCleanup(@() cd(old_dir)); %#ok<NASGU>
cd(work_dir);
diary(fullfile(work_dir, '运行日志.txt'));
stop_diary = onCleanup(@() diary('off')); %#ok<NASGU>
timer_value = tic;
fprintf('材料：%s；指标：%s；自身输入来源：drf.mat\n', material, metric_name);
run(fullfile(work_dir, script_name));
elapsed_seconds = toc(timer_value);
% 保存实际计算值，而不是使用截图舍入系数作替代。
save(fullfile(work_dir, '完整拟合结果.mat'), 'material', 'script_name', ...
    'your', 'x', 'y', 'p_opt_final', 'beta_opt', 'beta_list', ...
    'MSE_in_save', 'MSE_k_save', 'AIC_save', 'elapsed_seconds');
writetable(array2table(your, 'VariableNames', {'mass_loss_percent','response'}), ...
    fullfile(work_dir, '自身实际输入.csv'));
fprintf('完成 %s / %s，总耗时 %.2f s\n', material, metric_name, elapsed_seconds);
end

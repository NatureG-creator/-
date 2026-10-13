function run_pit_depth_fits(dataset_id)
% Run all four datasets, or select one: run_pit_depth_fits(3).
if nargin < 1
    dataset_id = 1:4;
end
validateattributes(dataset_id,{'numeric'},{'vector','integer','>=',1,'<=',4});
base_dir = fileparts(mfilename('fullpath'));
for dataset_index = dataset_id(:)'
    execute_one(base_dir,dataset_index);
end
end

function execute_one(base_dir,dataset_index)
source_files = {'sj1.mat','sj7.mat','gq2.mat','sj5_bare_steel_sd.mat'};
source_variables = {'xiaosiy_sd2','wzy_sd','gq_sd2','sd_5'};
source_file = source_files{dataset_index};
source_variable = source_variables{dataset_index};
source_path = fullfile(base_dir,'输入数据',source_file);
loaded = load(source_path,source_variable);
input_matrix = loaded.(source_variable);
output_dir = fullfile(base_dir,'重新计算结果',sprintf('数据%d',dataset_index));
if ~isfolder(output_dir)
    mkdir(output_dir);
end
previous_dir = pwd;
restore_dir = onCleanup(@() cd(previous_dir)); %#ok<NASGU>
cd(output_dir);
writetable(array2table(input_matrix,'VariableNames',{'EtaPercent','LogMean'}), ...
    '原始输入数据.csv');
sd_5 = input_matrix; %#ok<NASGU>
local_script = fullfile(output_dir,'shujunihe_sd.m');
copyfile(fullfile(base_dir,'程序','shujunihe_sd.m'),local_script);
run(local_script);
save('完整拟合工作区.mat','params_cell','results','formula_cell', ...
    'x','y','x_train','y_train','x_test','y_test','x_fit', ...
    'y_fit_cell','y_pred_cell','y_ext_cell','train_ratio','x_extrap', ...
    'source_file','source_variable','source_path','input_matrix','dataset_index');
close(fig1);
close(fig2);
fprintf('COMPLETE_DATASET_%d\n',dataset_index);
end


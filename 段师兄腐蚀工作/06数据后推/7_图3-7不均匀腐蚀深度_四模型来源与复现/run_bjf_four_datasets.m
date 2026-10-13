function run_bjf_four_datasets(dataset_id)
% RUN_BJF_FOUR_DATASETS Reproduce each dataset with the original four-model script.
% run_bjf_four_datasets() runs all four; run_bjf_four_datasets(3) runs dataset 3.
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
source_files = {'sj1.mat','sj7.mat','sj3_bjf.mat','sj2_bjf.mat'};
source_variables = {'xiaosiy_bjf2','wzy_bjf','bjf3','bjf2'};
source_path = fullfile(base_dir,'输入数据',source_files{dataset_index});
source_data = load(source_path,source_variables{dataset_index});
bjf2 = source_data.(source_variables{dataset_index});
output_dir = fullfile(base_dir,'重新计算结果',sprintf('数据%d',dataset_index));
if ~isfolder(output_dir)
    mkdir(output_dir);
end
previous_dir = pwd;
restore_dir = onCleanup(@() cd(previous_dir)); %#ok<NASGU>
cd(output_dir);
writetable(array2table(bjf2,'VariableNames',{'EtaPercent','DepthMicrometers'}), ...
    '原始输入数据.csv');
fprintf('\nDATASET=%d SOURCE=%s VARIABLE=%s\n', ...
    dataset_index,source_files{dataset_index},source_variables{dataset_index});
script_path = fullfile(base_dir,'程序','shujunihe_bjf.m');
% Evaluate the unchanged script here so its relative exports stay in this dataset folder.
eval(fileread(script_path));
save('完整拟合结果.mat','params_cell','results','x','y','x_train','y_train', ...
    'x_test','y_test','x_fit','y_ext_cell','y_fit_cell','train_ratio','x_extrap', ...
    'source_path','source_variables','dataset_index');
close(fig1);
close(fig2);
fprintf('DATASET_%d_COMPLETE\n',dataset_index);
end

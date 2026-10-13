% 引入不同阶段对应参数
% data_x 为目标平均腐蚀深度控制值，单位与 space 一致
% data1、data2、data3、data4 为适应度对比用的试验统计指标
% 建议从本文件启动计算：run('stage_moni.m')

clearvars

script_dir = fileparts(mfilename('fullpath'));
if isempty(script_dir)
    script_dir = pwd;
end
output_dir = fullfile(script_dir, 'outputs_matlab');
if ~exist(output_dir, 'dir')
    mkdir(output_dir);
end
run_stamp = datestr(now, 'yyyymmdd_HHMMSS');
log_file = fullfile(output_dir, ['stage_moni_' run_stamp '.log']);
diary(log_file);
diary on;
cleanup_diary = onCleanup(@() diary('off'));
fprintf('========== stage_moni 开始：%s ==========\n', datestr(now));
fprintf('结果目录: %s\n', output_dir);
%初始元胞尺寸
%长宽高
w=100;
l=100;
n=100;
data_x=1063;
data_y=459;
data1=1.23;
data2=6.23;
data3=0.55;
data4=0.29;
data=[data_x' data_y' data1' data2' data3' data4'];
parameter_single=10;%参数个数
%即每代元胞自动机质量损失率不超过F次/整个腐蚀模拟最多更新 F 轮
        space=25;
        F=2000;
        stage_number=1;
        a_input=[];
        d_input=[];
        cl_input=[];
        %a_input=a_output;
        %d_input=d_output;
        %cl_input=cl_output;
        perfect_result_sd=zeros(size(data_x,2),size(data,2)-2);
        perfect_parameter_sd=zeros(size(data_x,2),parameter_single);
        a_sd=cell(size(data_x,2),1);

        d_sd=cell(size(data_x,2),1);
        cl_sd=cell(size(data_x,2),1);
        stage_numbers=zeros(size(data_x,2),1);
        result_file_latest = fullfile(output_dir, 'stage_moni_latest.mat');
        result_file_stamped = fullfile(output_dir, ['stage_moni_' run_stamp '.mat']);

try
for i=1:size(data_x,2)
        fprintf('\n========== 阶段 %d/%d 开始 ==========\n', i, size(data_x,2));
        fprintf('目标 data_x = %.4f, 当前 stage_number = %d\n', data_x(i), stage_number);
        tic_stage = tic;
        [perfect_result,perfect_parameter,a_output,d_output,cl_output]=GA(w,l,n,data_x(i),data(i,:),a_input,F,stage_number,space,d_input,cl_input);
        perfect_result_sd(i,:)=perfect_result;
        perfect_parameter_sd(i,:)=perfect_parameter;
        a_sd{i}=a_output;
        d_sd{i}=d_output;
        cl_sd{i}=cl_output;
        stage_numbers(i)=stage_number;
        a_input=a_output;
        d_input=d_output;
        cl_input=cl_output;
        fprintf('阶段 %d 完成，用时 %.2f 秒。\n', i, toc(tic_stage));
        fprintf('阶段 %d 最优误差: [%s]\n', i, num2str(perfect_result, '%.6f '));
        fprintf('阶段 %d 最优参数: [%s]\n', i, num2str(perfect_parameter, '%.6f '));
        save(result_file_latest, 'perfect_result_sd', 'perfect_parameter_sd', 'a_sd', 'd_sd', 'cl_sd', ...
            'stage_numbers', 'data', 'data_x', 'w', 'l', 'n', 'space', 'F', 'i', '-v7.3');
        save(result_file_stamped, 'perfect_result_sd', 'perfect_parameter_sd', 'a_sd', 'd_sd', 'cl_sd', ...
            'stage_numbers', 'data', 'data_x', 'w', 'l', 'n', 'space', 'F', 'i', '-v7.3');
        fprintf('阶段 %d 结果已保存到: %s\n', i, result_file_latest);
        stage_number=stage_number+1;
end
catch ME
        fprintf(2, '\n!!!!!! stage_moni 运行出错 !!!!!!\n');
        fprintf(2, '错误信息: %s\n', ME.message);
        for s = 1:numel(ME.stack)
            fprintf(2, '位置: %s 第 %d 行\n', ME.stack(s).file, ME.stack(s).line);
        end
        save(result_file_latest, 'perfect_result_sd', 'perfect_parameter_sd', 'a_sd', 'd_sd', 'cl_sd', ...
            'stage_numbers', 'data', 'data_x', 'w', 'l', 'n', 'space', 'F', '-v7.3');
        rethrow(ME);
end

fprintf('\n========== stage_moni 正常结束：%s ==========\n', datestr(now));
fprintf('最终结果文件: %s\n', result_file_stamped);

%% Q370NH与Q355蚀坑参数-质量损失率拟合
% 运行后分别生成：
% 1. 蚀坑深度-质量损失率拟合图
% 2. 径深比-质量损失率拟合图
%
% fit_target可选：'Q370NH'、'Q355'或'both'

clear;
clc;
close all;

fit_target = 'Q355';
model_choices = "auto"; % auto自动选择最优函数，prompt逐项弹窗选择
formula_digits = 4;      % 公式参数保留的小数位数

script_dir = fileparts(mfilename('fullpath'));
if isempty(script_dir)
    script_dir = pwd;
end

generate_separate_pit_parameter_fits( ...
    fit_target,script_dir,true,model_choices,formula_digits);

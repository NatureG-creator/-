%% Q370NH与Q355蚀坑参数-质量损失率关系图
% fit_target：'Q370NH'、'Q355'或'both'
% mass_loss_mode：
%   'original_figure' 复现Word原图，Q355使用1号试件质量损失率
%   'mean'            两种钢材均使用1、2号试件平均质量损失率

clear;
clc;
close all;

fit_target = 'both';
mass_loss_mode = 'original_figure';
model_choices = "auto"; % auto自动选择最优函数，prompt逐项弹窗选择
formula_digits = 4;      % 公式参数保留的小数位数

script_dir = fileparts(mfilename('fullpath'));
if isempty(script_dir)
    script_dir = pwd;
end

generate_pit_parameter_mass_loss_figure( ...
    fit_target,mass_loss_mode,script_dir,true, ...
    model_choices,formula_digits);

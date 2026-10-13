%% 腐蚀率-时间关系拟合图
% 修改下面的fit_target即可选择拟合对象：
%   'Q370NH'：只拟合Q370NH（默认）
%   'Q355'  ：只拟合Q355
%   'both'  ：同时拟合Q370NH和Q355并绘制对比图

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

generate_corrosion_time_fit( ...
    fit_target,script_dir,true,model_choices,formula_digits);

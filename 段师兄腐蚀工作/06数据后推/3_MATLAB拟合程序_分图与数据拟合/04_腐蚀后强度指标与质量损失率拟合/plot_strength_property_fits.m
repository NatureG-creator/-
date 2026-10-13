%% 腐蚀后强度指标与质量损失率拟合
% fit_target可选：
%   'Q370NH' 或 'Q370'：只生成Q370NH
%   'Q355'             ：只生成Q355
%   'both'             ：生成两种钢材对比图

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

result = generate_strength_property_fits( ...
    fit_target,script_dir,true,model_choices,formula_digits);

fprintf('\n强度指标结果已保存到：%s\n\n',script_dir);
disp(result.fit_parameters);

%% ANSYS滞回数据处理与绘图（修复数字粘连问题 + 力学修正）
clear; clc; close all;

%% ========== 1. 读取原始txt文件，过滤表头 ==========
filename = '1.txt';
fid = fopen(filename, 'r');
valid_lines = {};

tline = fgetl(fid);
while ischar(tline)
    % 过滤标题行、表头行、空行
    if ~contains(tline, '*') ...
            && ~contains(tline, 'TIME') ...
            && ~contains(tline, 'ROT_END') ...
            && ~isempty(strtrim(tline))
        valid_lines{end+1} = tline; %#ok<AGROW>
    end
    tline = fgetl(fid);
end
fclose(fid);

%% ========== 2. 解析数值数据（核心修复：拆分粘连的负数） ==========
data_num = [];
for i = 1:length(valid_lines)
    line_str = valid_lines{i};
    
    % -------------------------- 关键修复 --------------------------
    % 正则替换：给所有「不是跟在E/e后面的负号」前面加空格，拆分粘连数字
    % 保留科学计数法的 E-001 不被拆分，只拆分数值间的负号
    line_str = regexprep(line_str, '(?<![Ee])-', ' -');
    % -------------------------------------------------------------
    
    % 转成数值数组
    num_row = str2num(line_str); %#ok<ST2NM>
    
    % 容错：只保留长度为6的有效行（对应6列数据）
    if length(num_row) == 6
        data_num(end+1, :) = num_row; %#ok<AGROW>
    else
        warning('第%d行数据解析异常，已跳过，解析到%d列', i, length(num_row));
    end
end

%% ========== 3. 提取变量 + 力学修正 ==========
% 列顺序：TIME | ROT_END1 | ROT_END2 | MOM_END1 | MOM_END2 | MOM_AVG(原错误值，弃用)
TIME    = data_num(:,1);
rot_1   = data_num(:,2);
rot_2   = data_num(:,3);
mom_1   = data_num(:,4);
mom_2   = data_num(:,5);

% 横坐标：相对转角（两端反向转动，总弯曲变形）
theta = rot_1 - rot_2;
% 纵坐标：截面平均弯矩（消除两端符号差异，取真实弯矩值）
M = (mom_1 - mom_2) / 2;

%% ========== 4. 绘制规范滞回曲线 ==========
figure('Color','w', 'Position', [150 120 750 550]);

plot(theta, M, 'Color', '#0072BD', 'LineWidth', 1.2);
hold on;
scatter(theta, M, 12, 'k', 'filled');

xlabel('Rotation (rad)', 'FontName', 'Times New Roman', 'FontSize', 13);
ylabel('Moment (N·mm)', 'FontName', 'Times New Roman', 'FontSize', 13);
title('Hysteresis Curve', 'FontName', 'Times New Roman', 'FontSize', 15);

grid on;
box on;
set(gca, 'FontName', 'Times New Roman', 'FontSize', 11);
set(gca, 'GridAlpha', 0.3);

%% 可选：导出修正后数据
% result_table = table(theta, M, 'VariableNames', {'Rotation_rad', 'Moment_Nmm'});
% writetable(result_table, '修正后滞回数据.csv');
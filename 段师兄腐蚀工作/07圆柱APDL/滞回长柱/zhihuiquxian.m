clc; clear; close all;

filename = '2.txt';

%% ==============================
% 1. 读取整个文件为字符串
%% ==============================
txt = fileread(filename);

%% ==============================
% 2. 提取所有数字行
%% ==============================
lines = splitlines(txt);

data = [];

for i = 1:length(lines)
    line = strtrim(lines{i});
    
    % 跳过空行/标题行
    if isempty(line)
        continue;
    end
    
    % 判断是否以数字开头
    if ~isempty(regexp(line(1), '[0-9\-]', 'once'))
        
        nums = sscanf(line, '%f');
        
        if length(nums) >= 6
            data = [data; nums(1:6)'];
        end
    end
end

%% ==============================
% 3. 分列
%% ==============================
time   = data(:,1);
rot1   = data(:,2);
rot2   = data(:,3);
momAvg = data(:,6);

%% ==============================
% 4. 构造滞回变量
%% ==============================
rot = (rot1 - rot2)/2;
mom = momAvg;

%% ==============================
% 5. 画滞回曲线
%% ==============================
figure;
plot(rot, mom, 'c-', 'LineWidth', 1.8);
grid on;

xlabel('Rotation (rad)');
ylabel('Moment (N·mm)');
title('Hysteresis Curve');

hold on;
plot(rot, mom, 'k.', 'MarkerSize', 6);
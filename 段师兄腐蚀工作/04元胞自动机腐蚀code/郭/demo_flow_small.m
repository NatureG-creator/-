%% demo_flow_small.m
% 小规模演示：stage_moni -> GA生成XY -> fitness调用CA -> CA执行腐蚀模拟
% 目的：用于课堂/组会演示流程，不替代正式GA.m大规模计算。

clc;
clear;
close all;
show_figures = false;  % 演示默认只看命令行输出，避免无界面运行时图形崩溃
set(0, 'DefaultFigureVisible', 'off');

fprintf('================ 小规模腐蚀模拟流程演示 ================\n');

%% 1. 对应 stage_moni.m：设置初始数据
w = 30;
l = 30;
n = 30;
space = 25;
F = 40;
stage_number = 1;

% 目标统计数据，格式与CA.m输出CS保持一致：
% [平均腐蚀深度, 不均匀腐蚀深度, mean(jsb), mean(shengdu), sigma1, sigma2]
data_x = 120;
data = [120, 45, 1.20, 3.00, 0.50, 0.30];

a_begin = ones(w, l, n+1);
a_begin(:,:,1) = 0;
d_begin = ones(size(a_begin)) * 3;
CL_begin = zeros(w, l);

fprintf('\n[1] stage_moni.m 思想：初始数据设置完成\n');
fprintf('    网格尺寸: w=%d, l=%d, n=%d, 最大迭代 F=%d\n', w, l, n, F);
fprintf('    目标data: [%s]\n', num2str(data, '%.4f '));

%% 2. 对应 GA.m：生成一小批参数XY
NIND = 3;
LIND = 10;
bits_per_param = 11;
lb = [0   0  0     5  1  0    1  0    0   1];
ub = [0.3 1  0.005 35 35 0.1 35 0.5 0.5 15];

Chrom = latin_begin(NIND, LIND, bits_per_param);
XY = er2shi(Chrom, lb, ub, bits_per_param);

fprintf('\n[2] GA.m 思想：生成候选腐蚀参数 XY\n');
disp(array2table(XY, 'VariableNames', ...
    {'p_uniform','p_passive','p_break','CL_threshold','alpha_corr', ...
     'sensitive','alpha_break','p_h','p_v','p_o'}));

%% 3. 对应 fitness.m：调用CA.m计算每组参数误差
fprintf('\n[3] fitness.m 思想：逐个参数调用 CA.m\n');
OBJV = zeros(NIND, numel(data));
sd_a = cell(NIND, 1);
sd_d = cell(NIND, 1);
sd_cl = cell(NIND, 1);

for i = 1:NIND
    fprintf('\n    ---- 个体 %d/%d 开始 CA 腐蚀模拟 ----\n', i, NIND);
    [CS, a_out, d_out, CL_out] = CA(XY(i,:), F, a_begin, data, data_x, ...
        n, w, l, space, d_begin, stage_number, CL_begin);

    OBJV(i,:) = abs(CS);
    sd_a{i} = a_out;
    sd_d{i} = d_out;
    sd_cl{i} = CL_out;

    fprintf('    个体%d相对误差 abs(CS): [%s]\n', i, num2str(OBJV(i,:), '%.4f '));
end

%% 4. 选择本次演示中的最优个体
weighted_error = 0.1*OBJV(:,1) + 0.3*OBJV(:,2) + 0.2*OBJV(:,3) + 0.2*OBJV(:,4) + 0.1*OBJV(:,5) + 0.1*OBJV(:,6);
[best_error, best_idx] = min(weighted_error);

perfect_parameter_demo = XY(best_idx,:);
perfect_result_demo = OBJV(best_idx,:);
a_output_demo = sd_a{best_idx};
d_output_demo = sd_d{best_idx};
cl_output_demo = sd_cl{best_idx};

fprintf('\n[4] 本次小演示最优结果\n');
fprintf('    最优个体编号: %d\n', best_idx);
fprintf('    加权误差: %.6f\n', best_error);
fprintf('    perfect_parameter_demo: [%s]\n', num2str(perfect_parameter_demo, '%.6f '));
fprintf('    perfect_result_demo:    [%s]\n', num2str(perfect_result_demo, '%.6f '));

%% 5. 简单显示腐蚀深度场
[baseline, ~, ~, depth_map] = moving_avg_3D(a_output_demo, 5, w, l, n);
Average_depth_demo = (w*l*n - sum(a_output_demo(:) == 1)) / (w*l*n) * n * space;

fprintf('\n[5] CA.m 输出腐蚀形貌\n');
fprintf('    平均腐蚀深度 Average_depth_demo = %.4f\n', Average_depth_demo);
fprintf('    depth_map尺寸: %d x %d\n', size(depth_map,1), size(depth_map,2));

if show_figures
    figure('Name','demo_flow_small 腐蚀深度场');
    subplot(1,2,1);
    imagesc(depth_map);
    axis image;
    colorbar;
    title('depth\_map 原始腐蚀深度层号');

    subplot(1,2,2);
    surf(baseline, 'EdgeColor', 'none');
    axis tight;
    colorbar;
    title('baseline 平滑腐蚀表面');
    view(45, 35);
end

fprintf('\n演示完成：stage_moni -> GA/XY -> fitness -> CA 流程已经跑通。\n');

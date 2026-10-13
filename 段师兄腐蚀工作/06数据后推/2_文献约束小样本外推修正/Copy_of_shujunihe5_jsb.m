%% ============================================================
% 质量损失率 - 腐蚀坑径深比对数均值 修正拟合函数求解
% 模型形式：y = A*exp(B*x) + C
%
% 修正逻辑：
% 1. 4 组文献数据分别拟合完整模型 y = A*exp(B*x) + C；
% 2. 文献参考曲线采用各文献拟合曲线等权平均，仅用于绘图；
% 3. 文献参考斜率采用各文献斜率等权平均，用于外区趋势约束；
% 4. 自身数据先完整拟合得到 C_ori；
% 5. 修正阶段固定 C = C_ori，仅优化 A 和 B；
% 6. beta = 0 时直接采用自身原始拟合；
% 7. 设置内区误差上限，避免过度牺牲自身数据拟合质量；
% 8. 输出论文风格 tif/png/pdf 图片和参数表。
%% ============================================================

clc; close all;

%% ========== 0. 数据输入 ==========
% 第 1 列：质量损失率 eta / %
% 第 2 列：腐蚀坑径深比对数均值 lambda_q

lit1 = xsy_jsb2;    % 文献1
lit2 = wzy_jsb;     % 文献2
lit3 = gq_jsb2;     % 文献3
lit4 = jsb_5;       % 文献4
your = drf_jsb2;    % 自身小样本数据

% 坐标缩放系数，按厚度修正或数据统一处理结果修改
scale1 = 0.62;
scale2 = 1.195;
scale3 = 0.6333;
scale4 = 0.8333;
scale_your = 1.00;

x_lits = {};
y_lits = {};
lit_names = {};

if ~isempty(lit1)
    x_lits{end+1} = lit1(:,1) * scale1;
    y_lits{end+1} = lit1(:,2);
    lit_names{end+1} = '文献1';
end

if ~isempty(lit2)
    x_lits{end+1} = lit2(:,1) * scale2;
    y_lits{end+1} = lit2(:,2);
    lit_names{end+1} = '文献2';
end

if ~isempty(lit3)
    x_lits{end+1} = lit3(:,1) * scale3;
    y_lits{end+1} = lit3(:,2);
    lit_names{end+1} = '文献3';
end

if ~isempty(lit4)
    x_lits{end+1} = lit4(:,1) * scale4;
    y_lits{end+1} = lit4(:,2);
    lit_names{end+1} = '文献4';
end

N_lit = length(x_lits);

if N_lit < 1
    error('至少需要 1 组有效文献数据。');
end

% 清洗文献数据
for i = 1:N_lit
    [x_lits{i}, y_lits{i}] = clean_xy(x_lits{i}, y_lits{i});
end

% 自身数据
x = your(:,1) * scale_your;
y = your(:,2);
[x, y] = clean_xy(x, y);

if numel(x) < 3
    error('自身数据点少于 3 个，不建议进行指数模型修正拟合。');
end

x_max = max(x);
x_outer_end = max(x) * 1.40;
x_outer_end = max(x_outer_end, x_max * 1.05);

% 汇总文献数据，用于画图范围和 y 轴范围
all_x_lit = [];
all_y_lit = [];
for i = 1:N_lit
    all_x_lit = [all_x_lit; x_lits{i}(:)];
    all_y_lit = [all_y_lit; y_lits{i}(:)];
end

x_fit  = linspace(min(x), x_outer_end, 400)';
x_plot = linspace(min([all_x_lit; x]), x_outer_end, 400)';
x_temp = linspace(x_max, x_outer_end, 50)';

x_end_for_slope = 30;
if x_end_for_slope <= x_max
    x_end_for_slope = x_outer_end;
end

%% ========== 1. 图像输出设置 ==========
out_dir = '腐蚀坑径深比对数均值_AexpBx固定C修正拟合输出';
if ~exist(out_dir,'dir')
    mkdir(out_dir);
end

fig_w = 13;
fig_h = 8.5;
ax_pos = [0.16 0.17 0.78 0.72];

x_label_text = '质量损失率 \eta / %';
y_label_text = '腐蚀坑径深比对数均值 \lambda_q';

colors = [
    0.000 0.447 0.741;
    0.850 0.325 0.098;
    0.466 0.674 0.188;
    0.494 0.184 0.556;
];

markers = {'o','s','^','d'};

Ccolor.black     = [0.000 0.000 0.000];
Ccolor.gray      = [0.450 0.450 0.450];
Ccolor.lightgray = [0.700 0.700 0.700];
Ccolor.red       = [0.635 0.078 0.184];

%% ========== 2. 文献数据分别拟合 y = A*exp(B*x) + C ==========
% 模型：y = A*exp(B*x) + C
% 斜率：k = A*B*exp(B*x)

p_lit = zeros(N_lit, 3);   % A, B, C
mse_lit = zeros(N_lit, 1);

for i = 1:N_lit
    [p_lit(i,:), mse_lit(i)] = fit_exp_amp(x_lits{i}, y_lits{i});
end

A_lit = p_lit(:,1);
B_lit = p_lit(:,2);
C_lit = p_lit(:,3);

% 文献参考曲线：曲线等权融合，仅用于展示
Y_ref_all = zeros(length(x_plot), N_lit);
for i = 1:N_lit
    Y_ref_all(:,i) = exp_amp_eval(p_lit(i,:), x_plot);
end
y_ref_fit = mean(Y_ref_all, 2);

% 文献参考斜率：斜率等权融合，用于外区约束
K_ref_all = zeros(length(x_temp), N_lit);
for i = 1:N_lit
    K_ref_all(:,i) = exp_amp_slope(p_lit(i,:), x_temp);
end
dy_ref = mean(K_ref_all, 2);

%% ========== 3. 自身数据原始完整拟合 ==========
[p_ori, mse_ori] = fit_exp_amp(x, y);

A_ori = p_ori(1);
B_ori = p_ori(2);
C_ori = p_ori(3);

% 修正阶段固定 C，不参与优化
C_fix = C_ori;

%% ========== 4. 基础客观权重计算 ==========
MSE_in_base = mean((exp_amp_eval(p_ori, x) - y).^2);
win_base = 1 / (MSE_in_base + eps);

dy_ori = exp_amp_slope(p_ori, x_temp);
MSE_k_base = mean((dy_ori - dy_ref).^2);
wout_base = 1 / (MSE_k_base + eps);

%% ========== 5. 遍历 beta，求解最优修正模型 ==========
beta_list = linspace(0, 30, 150);
N_beta = numel(beta_list);

MSE_in_save = inf(1,N_beta);
MSE_k_save  = inf(1,N_beta);
AIC_save    = inf(1,N_beta);
k_end_save  = inf(1,N_beta);
A_save      = nan(1,N_beta);
B_save      = nan(1,N_beta);
C_save      = nan(1,N_beta);

ALLOW_MULTIPLE = 1.30;
MSE_IN_LIMIT = MSE_in_base * ALLOW_MULTIPLE;

opt = optimset('Display','off', ...
               'MaxIter', 5000, ...
               'MaxFunEvals', 20000, ...
               'TolX', 1e-10, ...
               'TolFun', 1e-10);

for i = 1:N_beta
    beta_now = beta_list(i);

    win  = win_base;
    wout = beta_now * wout_base;

    % beta = 0 时直接采用自身原始拟合，保证至少存在一个满足内区误差约束的模型
    if abs(beta_now) < 1e-12
        p_opt = p_ori;
    else
        p0_AB = [A_ori, B_ori];

        p_AB_opt = fminsearch(@(p_AB) obj_fun_exp_amp_fix_C( ...
            p_AB, C_fix, x_fit, win, wout, x, y, x_max, x_temp, dy_ref), ...
            p0_AB, opt);

        p_opt = [p_AB_opt(1), p_AB_opt(2), C_fix];
    end

    y_in_fit = exp_amp_eval(p_opt, x);
    MSE_in = mean((y_in_fit - y).^2);

    % 内区误差上限控制
    if MSE_in > MSE_IN_LIMIT || any(~isfinite(p_opt))
        continue;
    end

    dy_pre = exp_amp_slope(p_opt, x_temp);
    MSE_k = mean((dy_pre - dy_ref).^2);

    n_data = numel(x);
    m_out = numel(x_temp);
    p_num = 2;   % 修正阶段只优化 A 和 B

    AIC_star = n_data * log(MSE_in + eps) + ...
               m_out  * log(MSE_k + eps) + ...
               2 * p_num;

    k_end = exp_amp_slope(p_opt, x_end_for_slope);

    MSE_in_save(i) = MSE_in;
    MSE_k_save(i)  = MSE_k;
    AIC_save(i)    = AIC_star;
    k_end_save(i)  = k_end;
    A_save(i)      = p_opt(1);
    B_save(i)      = p_opt(2);
    C_save(i)      = p_opt(3);
end

%% ========== 6. 确定最优 beta 和最终修正模型 ==========
[~, idx_opt] = min(AIC_save);

if isinf(AIC_save(idx_opt)) || isnan(AIC_save(idx_opt))
    error('未找到满足内区误差限制的修正模型。可适当增大 ALLOW_MULTIPLE 或检查数据质量。');
end

beta_opt = beta_list(idx_opt);

p_opt_final = [A_save(idx_opt), B_save(idx_opt), C_save(idx_opt)];
A_opt = p_opt_final(1);
B_opt = p_opt_final(2);
C_opt = p_opt_final(3);

final_mse = MSE_in_save(idx_opt);
mse_ratio = final_mse / MSE_in_base;

y_ori_fit = exp_amp_eval(p_ori, x_plot);
y_opt_fit = exp_amp_eval(p_opt_final, x_plot);

%% ========== 7. 命令行输出最终结果 ==========
fprintf('\n');
fprintf('===========================================================\n');
fprintf('      质量损失率 - 腐蚀坑径深比对数均值 修正拟合结果\n');
fprintf('===========================================================\n\n');

fprintf('【文献数据拟合：y = A*exp(B*x) + C】\n');
for i = 1:N_lit
    fprintf('%s：y = %.6f*exp(%.6f*x) + %.6f，MSE = %.6g\n', ...
        lit_names{i}, p_lit(i,1), p_lit(i,2), p_lit(i,3), mse_lit(i));
end
fprintf('\n');

fprintf('【文献融合说明】\n');
fprintf('参考曲线采用各文献拟合曲线等权平均；参考斜率采用各文献斜率等权平均。\n\n');

fprintf('【自身数据原始无约束拟合】\n');
fprintf('y_ori = %.6f*exp(%.6f*x) + %.6f\n', A_ori, B_ori, C_ori);
fprintf('原始内区 MSE = %.6g\n', MSE_in_base);
fprintf('外区基础斜率 MSE = %.6g\n\n', MSE_k_base);

fprintf('【修正阶段说明】\n');
fprintf('固定 C = %.6f，仅优化 A 和 B。\n\n', C_fix);

fprintf('===========================================================\n');
fprintf('最终最优修正拟合公式：\n');
fprintf('y = %.6f*exp(%.6f*x) + %.6f\n', A_opt, B_opt, C_opt);
fprintf('===========================================================\n');
fprintf('最优权重放大系数 beta = %.4f\n', beta_opt);
fprintf('修正后内区 MSE = %.6g\n', final_mse);
fprintf('当前误差相对原始误差倍数 = %.4f\n', mse_ratio);
fprintf('允许上限倍数 = %.2f\n', ALLOW_MULTIPLE);
fprintf('内区误差允许上限 MSE_IN_LIMIT = %.6g\n', MSE_IN_LIMIT);
fprintf('最优 AIC* = %.6f\n', AIC_save(idx_opt));
fprintf('外区斜率 MSE = %.6g\n', MSE_k_save(idx_opt));
fprintf('末端斜率 k(x=%.2f) = %.6g\n\n', x_end_for_slope, k_end_save(idx_opt));

%% ========== 8. 输出结果表 ==========
model_name = cell(N_lit + 3, 1);
formula_col = strings(N_lit + 3, 1);
A_col = zeros(N_lit + 3, 1);
B_col = zeros(N_lit + 3, 1);
C_col = zeros(N_lit + 3, 1);

for i = 1:N_lit
    model_name{i} = lit_names{i};
    A_col(i) = p_lit(i,1);
    B_col(i) = p_lit(i,2);
    C_col(i) = p_lit(i,3);
    formula_col(i) = sprintf('y = %.6f*exp(%.6f*x) + %.6f', ...
        A_col(i), B_col(i), C_col(i));
end

model_name{N_lit+1} = '文献融合参考';
A_col(N_lit+1) = NaN;
B_col(N_lit+1) = NaN;
C_col(N_lit+1) = NaN;
formula_col(N_lit+1) = "参考曲线为各文献拟合曲线等权平均；参考斜率为各文献斜率等权平均";

model_name{N_lit+2} = '自身原始拟合';
A_col(N_lit+2) = A_ori;
B_col(N_lit+2) = B_ori;
C_col(N_lit+2) = C_ori;
formula_col(N_lit+2) = sprintf('y = %.6f*exp(%.6f*x) + %.6f', A_ori, B_ori, C_ori);

model_name{N_lit+3} = '最终修正拟合';
A_col(N_lit+3) = A_opt;
B_col(N_lit+3) = B_opt;
C_col(N_lit+3) = C_opt;
formula_col(N_lit+3) = sprintf('y = %.6f*exp(%.6f*x) + %.6f', A_opt, B_opt, C_opt);

T_param = table(model_name, formula_col, A_col, B_col, C_col, ...
    'VariableNames', {'ModelName','Formula','A','B','C'});

T_metric = table(beta_opt, C_fix, MSE_in_base, final_mse, mse_ratio, MSE_IN_LIMIT, MSE_k_base, ...
    MSE_k_save(idx_opt), AIC_save(idx_opt), k_end_save(idx_opt), ...
    'VariableNames', {'BetaOpt','FixedC','MSEInBase','MSEInFinal','MSERatio','MSEInLimit','MSEKBase','MSEKFinal','AICStar','EndSlope'});

writetable(T_param, fullfile(out_dir,'腐蚀坑径深比对数均值_AexpBx固定C修正拟合参数表.xlsx'), 'Sheet','模型参数');
writetable(T_metric, fullfile(out_dir,'腐蚀坑径深比对数均值_AexpBx固定C修正拟合参数表.xlsx'), 'Sheet','评价指标');
writetable(T_param, fullfile(out_dir,'腐蚀坑径深比对数均值_AexpBx固定C修正拟合参数表.csv'));

%% ========== 9. 论文风格图 1：最终修正拟合图 ==========
fig1 = figure('Units','centimeters','Position',[4,4,fig_w,fig_h]);
set(fig1,'Color','w');

ax1 = axes('Parent',fig1,'Position',ax_pos);
hold(ax1,'on');
grid(ax1,'off');
box(ax1,'off');
set_nature_axis(ax1);

h_lit = gobjects(N_lit,1);

for i = 1:N_lit
    ci = colors(mod(i-1,size(colors,1))+1,:);
    mi = markers{mod(i-1,length(markers))+1};

    h_lit(i) = plot(ax1, x_lits{i}, y_lits{i}, mi, ...
        'MarkerSize',4.5, ...
        'MarkerFaceColor','none', ...
        'MarkerEdgeColor',ci, ...
        'LineWidth',0.8);

    plot(ax1, x_plot, exp_amp_eval(p_lit(i,:), x_plot), '-', ...
        'Color',ci, ...
        'LineWidth',1.0);
end

h_ref = plot(ax1, x_plot, y_ref_fit, '-.', ...
    'Color',Ccolor.gray, ...
    'LineWidth',1.5);

h_ori = plot(ax1, x_plot, y_ori_fit, '--', ...
    'Color',Ccolor.lightgray, ...
    'LineWidth',1.5);

h_opt = plot(ax1, x_plot, y_opt_fit, '-', ...
    'Color',Ccolor.red, ...
    'LineWidth',2.2);

h_your = plot(ax1, x, y, 'o', ...
    'MarkerSize',5.2, ...
    'MarkerFaceColor',Ccolor.black, ...
    'MarkerEdgeColor','k', ...
    'LineWidth',0.7);

h_xmax = xline(ax1, x_max, '--', ...
    'Color',[0.25 0.25 0.25], ...
    'LineWidth',0.9);

xlabel(ax1, x_label_text, ...
    'FontName','Microsoft YaHei', ...
    'FontSize',9.5);

ylabel(ax1, y_label_text, ...
    'FontName','Microsoft YaHei', ...
    'FontSize',9.5);

legend_names = [lit_names, {'文献融合参考','自身原始拟合','最终修正拟合','自身数据','自身数据终点'}];

legend(ax1, [h_lit(:); h_ref; h_ori; h_opt; h_your; h_xmax], ...
    legend_names, ...
    'Location','best', ...
    'Box','off', ...
    'FontName','Microsoft YaHei', ...
    'FontSize',6.8);

xlim(ax1, [min(x_plot), max(x_plot)]);

y_all = [all_y_lit; y; y_ref_fit(:); y_ori_fit(:); y_opt_fit(:)];
yr = range(y_all);
if yr <= 0
    yr = 1;
end
ylim(ax1, [min(y_all)-0.05*yr, max(y_all)+0.08*yr]);

save_nature_figure(fig1, fullfile(out_dir,'腐蚀坑径深比对数均值_AexpBx固定C最终修正拟合图'));

%% ========== 10. 论文风格图 2：beta 多指标验证图 ==========
fig2 = figure('Units','centimeters','Position',[4,4,fig_w,fig_h]);
set(fig2,'Color','w');

tiledlayout(fig2, 2, 2, ...
    'Padding','compact', ...
    'TileSpacing','compact');

ax = nexttile;
hold(ax,'on'); grid(ax,'off'); box(ax,'off'); set_nature_axis(ax);
plot(ax, beta_list, MSE_in_save, '-', 'Color',colors(1,:), 'LineWidth',1.2);
xline(ax, beta_opt, '--', 'Color',Ccolor.red, 'LineWidth',0.9);
yline(ax, MSE_IN_LIMIT, ':', 'Color',Ccolor.gray, 'LineWidth',0.9);
xlabel(ax,'\beta','FontSize',8.5);
ylabel(ax,'内区 MSE','FontName','Microsoft YaHei','FontSize',8.5);
text(ax,0.04,0.90,'(a)','Units','normalized','FontName','Times New Roman','FontSize',9);

ax = nexttile;
hold(ax,'on'); grid(ax,'off'); box(ax,'off'); set_nature_axis(ax);
plot(ax, beta_list, MSE_k_save, '-', 'Color',colors(3,:), 'LineWidth',1.2);
xline(ax, beta_opt, '--', 'Color',Ccolor.red, 'LineWidth',0.9);
xlabel(ax,'\beta','FontSize',8.5);
ylabel(ax,'外区斜率 MSE','FontName','Microsoft YaHei','FontSize',8.5);
text(ax,0.04,0.90,'(b)','Units','normalized','FontName','Times New Roman','FontSize',9);

ax = nexttile;
hold(ax,'on'); grid(ax,'off'); box(ax,'off'); set_nature_axis(ax);
plot(ax, beta_list, AIC_save, '-', 'Color',colors(2,:), 'LineWidth',1.2);
xline(ax, beta_opt, '--', 'Color',Ccolor.red, 'LineWidth',0.9);
xlabel(ax,'\beta','FontSize',8.5);
ylabel(ax,'AIC^*','FontName','Times New Roman','FontSize',8.5);
text(ax,0.04,0.90,'(c)','Units','normalized','FontName','Times New Roman','FontSize',9);

ax = nexttile;
hold(ax,'on'); grid(ax,'off'); box(ax,'off'); set_nature_axis(ax);
plot(ax, beta_list, k_end_save, '-', 'Color',Ccolor.black, 'LineWidth',1.2);
xline(ax, beta_opt, '--', 'Color',Ccolor.red, 'LineWidth',0.9);

for i = 1:N_lit
    ci = colors(mod(i-1,size(colors,1))+1,:);
    yline(ax, exp_amp_slope(p_lit(i,:), x_end_for_slope), ':', ...
        'Color',ci, ...
        'LineWidth',0.9);
end

dy_ref_end_value = 0;
for i = 1:N_lit
    dy_ref_end_value = dy_ref_end_value + exp_amp_slope(p_lit(i,:), x_end_for_slope);
end
dy_ref_end_value = dy_ref_end_value / N_lit;

yline(ax, dy_ref_end_value, '--', 'Color',Ccolor.gray, 'LineWidth',1.0);

xlabel(ax,'\beta','FontSize',8.5);
ylabel(ax,'末端斜率','FontName','Microsoft YaHei','FontSize',8.5);
text(ax,0.04,0.90,'(d)','Units','normalized','FontName','Times New Roman','FontSize',9);

save_nature_figure(fig2, fullfile(out_dir,'腐蚀坑径深比对数均值_AexpBx固定C_beta多指标验证图'));

fprintf('\n已生成输出文件夹：%s\n', out_dir);
fprintf('图像文件：tif / png / pdf 均已导出，可直接插入 Word。\n');

%% ============================================================
%% 局部函数
%% ============================================================

function [x_clean, y_clean] = clean_xy(x, y)
    x = x(:);
    y = y(:);

    valid = isfinite(x) & isfinite(y) & x > 0;
    x = x(valid);
    y = y(valid);

    [x, idx] = sort(x);
    y = y(idx);

    [x_unique, ~, ic] = unique(x);
    y_mean = accumarray(ic, y, [], @mean);

    x_clean = x_unique;
    y_clean = y_mean;
end

function y = exp_amp_eval(p, x)
    A = p(1);
    B = p(2);
    C = p(3);

    x = x(:);
    y = A .* exp(B .* x) + C;
end

function k = exp_amp_slope(p, x)
    A = p(1);
    B = p(2);

    x = x(:);
    k = A .* B .* exp(B .* x);
end

function [p_best, mse_best] = fit_exp_amp(x, y)
    x = x(:);
    y = y(:);

    valid = isfinite(x) & isfinite(y) & x > 0;
    x = x(valid);
    y = y(valid);

    yr = max(y) - min(y);
    if yr <= 0
        yr = max(abs(y));
    end
    if yr <= 0
        yr = 1;
    end

    xr = max(x) - min(x);
    if xr <= 0
        xr = max(x);
    end
    if xr <= 0
        xr = 1;
    end

    % 多组 C 初值，提高稳定性
    C0_list = [
        min(y) - 0.05 * yr;
        min(y) - 0.20 * yr;
        min(y) - 0.50 * yr;
        max(y) + 0.05 * yr;
        max(y) + 0.20 * yr;
        max(y) + 0.50 * yr
    ];

    p0_all = [];

    for ii = 1:length(C0_list)
        C0 = C0_list(ii);

        % 情况1：A 为正
        yy1 = y - C0;
        if all(yy1 > 0)
            pp = polyfit(x, log(yy1), 1);
            B0 = pp(1);
            A0 = exp(pp(2));
            if isfinite(A0) && isfinite(B0)
                p0_all = [p0_all; A0, B0, C0];
            end
        end

        % 情况2：A 为负
        yy2 = C0 - y;
        if all(yy2 > 0)
            pp = polyfit(x, log(yy2), 1);
            B0 = pp(1);
            A0 = -exp(pp(2));
            if isfinite(A0) && isfinite(B0)
                p0_all = [p0_all; A0, B0, C0];
            end
        end
    end

    % 通用初值，避免 p0_all 为空
    p0_extra = [
        yr,  -1/xr,   min(y);
        yr,  -0.2/xr, min(y);
       -yr,  -1/xr,   max(y);
       -yr,  -0.2/xr, max(y);
        yr,   1/xr,   min(y);
        yr,   0.2/xr, min(y);
       -yr,   1/xr,   max(y);
       -yr,   0.2/xr, max(y)
    ];

    p0_all = [p0_all; p0_extra];

    opt = optimset('Display','off', ...
                   'MaxIter', 5000, ...
                   'MaxFunEvals', 20000, ...
                   'TolX', 1e-10, ...
                   'TolFun', 1e-10);

    best_loss = inf;
    p_best = p0_all(1,:);

    for ii = 1:size(p0_all,1)
        p0 = p0_all(ii,:);

        obj = @(p) mean((exp_amp_eval(p,x) - y).^2) + penalty_exp_amp(p,x,y);

        p_try = fminsearch(obj, p0, opt);
        loss_try = mean((exp_amp_eval(p_try,x) - y).^2) + penalty_exp_amp(p_try,x,y);

        if loss_try < best_loss
            best_loss = loss_try;
            p_best = p_try;
        end
    end

    mse_best = mean((exp_amp_eval(p_best,x) - y).^2);
end

function pen = penalty_exp_amp(p, x, y)
    pen = 0;

    if any(~isfinite(p))
        pen = 1e30;
        return;
    end

    A = p(1);
    B = p(2);
    C = p(3);

    yr = max(y) - min(y);
    if yr <= 0
        yr = max(abs(y));
    end
    if yr <= 0
        yr = 1;
    end

    xr = max(x) - min(x);
    if xr <= 0
        xr = max(x);
    end
    if xr <= 0
        xr = 1;
    end

    A_lim = 50 * yr;
    B_lim = 10 / xr;

    if abs(A) > A_lim
        pen = pen + 1e10 * (abs(A) - A_lim)^2;
    end

    if abs(B) > B_lim
        pen = pen + 1e10 * (abs(B) - B_lim)^2;
    end

    C_low = min(y) - 20 * yr;
    C_high = max(y) + 20 * yr;

    if C < C_low
        pen = pen + 1e10 * (C - C_low)^2;
    end

    if C > C_high
        pen = pen + 1e10 * (C - C_high)^2;
    end

    y_test = exp_amp_eval(p, x);

    if any(~isfinite(y_test)) || any(abs(y_test) > 1e8)
        pen = pen + 1e20;
    end
end

function loss = obj_fun_exp_amp_fix_C(p_AB, C_fix, x_fit, w_in, w_out, x, y, x_max, x_temp, dy_ref)

    if any(~isfinite(p_AB))
        loss = 1e30;
        return;
    end

    A = p_AB(1);
    B = p_AB(2);

    yr = max(y) - min(y);
    if yr <= 0
        yr = max(abs(y));
    end
    if yr <= 0
        yr = 1;
    end

    xr = max(x) - min(x);
    if xr <= 0
        xr = max(x);
    end
    if xr <= 0
        xr = 1;
    end

    A_lim = 50 * yr;
    B_lim = 10 / xr;

    if abs(A) > A_lim || abs(B) > B_lim
        loss = 1e30;
        return;
    end

    p = [A, B, C_fix];

    y_pre = exp_amp_eval(p, x_fit);

    if any(~isfinite(y_pre)) || any(abs(y_pre) > 1e8)
        loss = 1e30;
        return;
    end

    % 内区拟合误差
    idx_inner = x_fit <= x_max;
    x_inner = x_fit(idx_inner);

    y_interp = interp1(x, y, x_inner, 'linear', 'extrap');

    loss_in = sum(w_in .* (exp_amp_eval(p, x_inner) - y_interp).^2);

    % 外区斜率误差
    idx_outer = x_fit > x_max;
    x_outer = x_fit(idx_outer);

    dy_pre = exp_amp_slope(p, x_outer);
    dy_ref_outer = interp1(x_temp, dy_ref, x_outer, 'linear', 'extrap');

    loss_out = sum(w_out .* (dy_pre - dy_ref_outer).^2);

    loss = loss_in + loss_out;
end

function set_nature_axis(ax)
    set(ax, ...
        'FontName','Microsoft YaHei', ...
        'FontSize',8.2, ...
        'LineWidth',0.8, ...
        'TickDir','out', ...
        'TickLength',[0.018 0.018], ...
        'XMinorTick','off', ...
        'YMinorTick','off', ...
        'Layer','top');
end

function save_nature_figure(fig, base_name)
    try
        exportgraphics(fig, [base_name '.tif'], 'Resolution', 600);
        exportgraphics(fig, [base_name '.png'], 'Resolution', 600);
        exportgraphics(fig, [base_name '.pdf'], 'ContentType','vector');
    catch
        print(fig, [base_name '.tif'], '-dtiff', '-r600');
        print(fig, [base_name '.png'], '-dpng', '-r600');
        print(fig, [base_name '.pdf'], '-dpdf', '-painters');
    end
end
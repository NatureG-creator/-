%% ============================================================
% 质量损失率 - 不均匀腐蚀深度 修正拟合函数求解
% 模型形式：y = a*(1-exp(-b*x)) + c
%
% 修正逻辑：
% 1. 文献数据分别拟合完整指数饱和模型 y = a*(1-exp(-b*x)) + c；
% 2. 文献融合参考曲线采用各文献拟合曲线等权平均，仅用于绘图；
% 3. 文献融合参考斜率采用各文献斜率等权平均，用于外区趋势约束；
% 4. 自身数据先完整拟合，得到 c_ori；
% 5. 修正阶段固定 c = c_ori，仅优化 a 和 b；
% 6. 通过 beta 遍历，在内区拟合精度和外区斜率趋势之间取得平衡；
% 7. 输出论文风格 tif/png/pdf 图片，可直接插入 Word。
%% ============================================================

clc; close all;

%% ====================== 0. 输入文献数据 + 自身数据 ======================
% 数据格式：
% 第 1 列：质量损失率 eta / %
% 第 2 列：不均匀腐蚀深度 t_ave / μm

lit1 = xiaosiy_bjf2;   % 文献1
lit2 = wzy_bjf;        % 文献2
lit3 = bjf3;           % 文献3
lit4 = bjf2;           % 文献4
your = drfbjf2;        % 自身小样本数据

% 质量损失率尺度修正系数
scale1 = 0.625;
scale2 = 1.195;
scale3 = 0.1667;
scale4 = 0.6667;
scale_your = 1.00;

% 读取并缩放质量损失率
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
    error('自身数据点少于 3 个，不建议进行指数饱和模型修正拟合。');
end

x_max = max(x);                  % 内外区分界点：自身数据终点
x_outer_end = max(x) * 1.40;     % 外推终点，可按需要修改
x_outer_end = max(x_outer_end, x_max * 1.05);

x_fit = linspace(min(x), x_outer_end, 400)';
x_plot = linspace(min([cell2mat(x_lits(:)); x]), x_outer_end, 400)';
x_temp = linspace(x_max, x_outer_end, 50)';     % 外区斜率采样点

x_end_for_slope = 30;
if x_end_for_slope <= x_max
    x_end_for_slope = x_outer_end;
end

%% ====================== 1. 图像输出设置 ======================
out_dir = '不均匀腐蚀深度_固定C修正拟合输出';
if ~exist(out_dir, 'dir')
    mkdir(out_dir);
end

fig_w = 13;       % cm
fig_h = 8.5;      % cm
ax_pos = [0.16 0.17 0.78 0.72];

x_label_text = '质量损失率 \eta / %';
y_label_text = '不均匀腐蚀深度 t_{ave} / μm';

colors = [
    0.000 0.447 0.741;
    0.850 0.325 0.098;
    0.466 0.674 0.188;
    0.494 0.184 0.556;
];

C.black     = [0.000 0.000 0.000];
C.gray      = [0.450 0.450 0.450];
C.lightgray = [0.700 0.700 0.700];
C.red       = [0.635 0.078 0.184];

markers = {'o','s','^','d'};

%% ====================== 2. 文献数据分别拟合完整指数饱和模型 ======================
% 模型：y = a*(1-exp(-b*x)) + c
% 斜率：k = a*b*exp(-b*x)

p_lit = zeros(N_lit, 3);
mse_lit = zeros(N_lit, 1);

for i = 1:N_lit
    [p_lit(i,:), mse_lit(i)] = fit_exp_sat(x_lits{i}, y_lits{i});
end

a_lit = p_lit(:,1);
b_lit = p_lit(:,2);
c_lit = p_lit(:,3);

% 文献参考曲线：曲线等权融合，仅用于展示
Y_ref_all = zeros(length(x_plot), N_lit);
for i = 1:N_lit
    Y_ref_all(:,i) = exp_sat_eval(p_lit(i,:), x_plot);
end
y_ref_fit = mean(Y_ref_all, 2);

% 文献参考斜率：斜率等权融合，用于外区约束
K_ref_all = zeros(length(x_temp), N_lit);
for i = 1:N_lit
    K_ref_all(:,i) = exp_sat_slope(p_lit(i,:), x_temp);
end
dy_ref = mean(K_ref_all, 2);

%% ====================== 3. 自身数据原始完整拟合 ======================
[p_ori, mse_ori] = fit_exp_sat(x, y);

a_ori = p_ori(1);
b_ori = p_ori(2);
c_ori = p_ori(3);

% 修正阶段固定 c，不参与优化
c_fix = c_ori;

%% ====================== 4. 基础客观权重计算 ======================
MSE_in_base = mean((exp_sat_eval(p_ori, x) - y).^2);
win_base = 1 / (MSE_in_base + eps);

dy_ori = exp_sat_slope(p_ori, x_temp);
MSE_k_base = mean((dy_ori - dy_ref).^2);
wout_base = 1 / (MSE_k_base + eps);

%% ====================== 5. 遍历 beta，求解最优修正模型 ======================
beta_list = linspace(1, 30, 150);
N_beta = numel(beta_list);

MSE_in_save = inf(1,N_beta);
MSE_k_save  = inf(1,N_beta);
AIC_save    = inf(1,N_beta);
k_end_save  = inf(1,N_beta);
a_save      = nan(1,N_beta);
b_save      = nan(1,N_beta);
c_save      = nan(1,N_beta);

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

    p0_ab = [a_ori, b_ori];

    p_ab_opt = fminsearch(@(p_ab) obj_fun_exp_sat_fix_c( ...
        p_ab, c_fix, x_fit, win, wout, x, y, x_max, x_temp, dy_ref), ...
        p0_ab, opt);

    p_opt = [p_ab_opt(1), p_ab_opt(2), c_fix];

    y_in_fit = exp_sat_eval(p_opt, x);
    MSE_in = mean((y_in_fit - y).^2);

    if MSE_in > MSE_IN_LIMIT || any(~isfinite(p_opt)) || p_opt(1) <= 0 || p_opt(2) <= 0
        continue;
    end

    dy_pre = exp_sat_slope(p_opt, x_temp);
    MSE_k = mean((dy_pre - dy_ref).^2);

    n_data = numel(x);
    m_out = numel(x_temp);
    p_num = 2;

    AIC_star = n_data * log(MSE_in + eps) + ...
               m_out  * log(MSE_k + eps) + ...
               2 * p_num;

    k_end = exp_sat_slope(p_opt, x_end_for_slope);

    MSE_in_save(i) = MSE_in;
    MSE_k_save(i)  = MSE_k;
    AIC_save(i)    = AIC_star;
    k_end_save(i)  = k_end;
    a_save(i)      = p_opt(1);
    b_save(i)      = p_opt(2);
    c_save(i)      = p_opt(3);
end

%% ====================== 6. 确定最优 beta 和最终修正模型 ======================
[~, idx_opt] = min(AIC_save);

if isinf(AIC_save(idx_opt)) || isnan(AIC_save(idx_opt))
    error('未找到满足内区误差限制的修正模型。可适当增大 ALLOW_MULTIPLE 或检查数据质量。');
end

beta_opt = beta_list(idx_opt);

p_opt_final = [a_save(idx_opt), b_save(idx_opt), c_save(idx_opt)];
a_opt = p_opt_final(1);
b_opt = p_opt_final(2);
c_opt = p_opt_final(3);

final_mse = MSE_in_save(idx_opt);
mse_ratio = final_mse / MSE_in_base;

y_ori_fit = exp_sat_eval(p_ori, x_plot);
y_opt_fit = exp_sat_eval(p_opt_final, x_plot);

%% ====================== 7. 命令行输出最终结果 ======================
fprintf('\n');
fprintf('===========================================================\n');
fprintf('        质量损失率 - 不均匀腐蚀深度 修正拟合结果\n');
fprintf('===========================================================\n\n');

fprintf('【文献数据拟合：y = a(1-exp(-b*x)) + c】\n');
for i = 1:N_lit
    fprintf('%s：y = %.6f(1-exp(-%.6f*x)) + %.6f，MSE = %.6g\n', ...
        lit_names{i}, p_lit(i,1), p_lit(i,2), p_lit(i,3), mse_lit(i));
end
fprintf('\n');

fprintf('【文献融合说明】\n');
fprintf('参考曲线采用各文献拟合曲线等权平均；参考斜率采用各文献斜率等权平均。\n\n');

fprintf('【自身数据原始无约束拟合】\n');
fprintf('y_ori = %.6f(1-exp(-%.6f*x)) + %.6f\n', a_ori, b_ori, c_ori);
fprintf('原始内区 MSE = %.6g\n', MSE_in_base);
fprintf('外区基础斜率 MSE = %.6g\n\n', MSE_k_base);

fprintf('【修正阶段说明】\n');
fprintf('固定 c = %.6f，仅优化 a 和 b。\n\n', c_fix);

fprintf('===========================================================\n');
fprintf('最终最优修正拟合公式：\n');
fprintf('y = %.6f(1-exp(-%.6f*x)) + %.6f\n', a_opt, b_opt, c_opt);
fprintf('===========================================================\n');
fprintf('最优权重放大系数 beta = %.4f\n', beta_opt);
fprintf('修正后内区 MSE = %.6g\n', final_mse);
fprintf('当前误差相对原始误差倍数 = %.4f\n', mse_ratio);
fprintf('允许上限倍数 = %.2f\n', ALLOW_MULTIPLE);
fprintf('最优 AIC* = %.6f\n', AIC_save(idx_opt));
fprintf('外区斜率 MSE = %.6g\n', MSE_k_save(idx_opt));
fprintf('末端斜率 k(x=%.2f) = %.6g\n\n', x_end_for_slope, k_end_save(idx_opt));

%% ====================== 8. 输出结果表 ======================
model_name = cell(N_lit + 3, 1);
formula_col = strings(N_lit + 3, 1);
a_col = zeros(N_lit + 3, 1);
b_col = zeros(N_lit + 3, 1);
c_col = zeros(N_lit + 3, 1);

for i = 1:N_lit
    model_name{i} = lit_names{i};
    a_col(i) = p_lit(i,1);
    b_col(i) = p_lit(i,2);
    c_col(i) = p_lit(i,3);
    formula_col(i) = sprintf('y = %.6f(1-exp(-%.6f*x)) + %.6f', ...
        a_col(i), b_col(i), c_col(i));
end

model_name{N_lit+1} = '文献融合参考';
a_col(N_lit+1) = NaN;
b_col(N_lit+1) = NaN;
c_col(N_lit+1) = NaN;
formula_col(N_lit+1) = "参考曲线为各文献拟合曲线等权平均；参考斜率为各文献斜率等权平均";

model_name{N_lit+2} = '自身原始拟合';
a_col(N_lit+2) = a_ori;
b_col(N_lit+2) = b_ori;
c_col(N_lit+2) = c_ori;
formula_col(N_lit+2) = sprintf('y = %.6f(1-exp(-%.6f*x)) + %.6f', ...
    a_ori, b_ori, c_ori);

model_name{N_lit+3} = '最终修正拟合';
a_col(N_lit+3) = a_opt;
b_col(N_lit+3) = b_opt;
c_col(N_lit+3) = c_opt;
formula_col(N_lit+3) = sprintf('y = %.6f(1-exp(-%.6f*x)) + %.6f', ...
    a_opt, b_opt, c_opt);

T_param = table(model_name, formula_col, a_col, b_col, c_col, ...
    'VariableNames', {'模型名称','拟合函数','a','b','c'});

T_metric = table(beta_opt, c_fix, MSE_in_base, final_mse, mse_ratio, MSE_k_base, ...
    MSE_k_save(idx_opt), AIC_save(idx_opt), k_end_save(idx_opt), ...
    'VariableNames', {'最优beta','固定c','原始内区MSE','修正内区MSE','内区MSE倍数','原始外区斜率MSE','修正外区斜率MSE','AIC_star','末端斜率'});

writetable(T_param, fullfile(out_dir,'不均匀腐蚀深度_固定C修正拟合参数表.xlsx'), 'Sheet','模型参数');
writetable(T_metric, fullfile(out_dir,'不均匀腐蚀深度_固定C修正拟合参数表.xlsx'), 'Sheet','评价指标');
writetable(T_param, fullfile(out_dir,'不均匀腐蚀深度_固定C修正拟合参数表.csv'));

%% ====================== 9. 论文风格图 1：最终修正拟合图 ======================
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

    plot(ax1, x_plot, exp_sat_eval(p_lit(i,:), x_plot), '-', ...
        'Color',ci, ...
        'LineWidth',1.0);
end

h_ref = plot(ax1, x_plot, y_ref_fit, '-.', ...
    'Color',C.gray, ...
    'LineWidth',1.5);

h_ori = plot(ax1, x_plot, y_ori_fit, '--', ...
    'Color',C.lightgray, ...
    'LineWidth',1.5);

h_opt = plot(ax1, x_plot, y_opt_fit, '-', ...
    'Color',C.red, ...
    'LineWidth',2.2);

h_your = plot(ax1, x, y, 'o', ...
    'MarkerSize',5.2, ...
    'MarkerFaceColor',C.black, ...
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

y_all = [cell2mat(y_lits(:)); y; y_ref_fit(:); y_ori_fit(:); y_opt_fit(:)];
yr = range(y_all);
if yr <= 0
    yr = 1;
end
ylim(ax1, [min(y_all)-0.05*yr, max(y_all)+0.08*yr]);

save_nature_figure(fig1, fullfile(out_dir,'不均匀腐蚀深度_固定C最终修正拟合图'));

%% ====================== 10. 论文风格图 2：beta 多指标验证图 ======================
fig2 = figure('Units','centimeters','Position',[4,4,fig_w,fig_h]);
set(fig2,'Color','w');

tiledlayout(fig2, 2, 2, ...
    'Padding','compact', ...
    'TileSpacing','compact');

ax = nexttile;
hold(ax,'on'); grid(ax,'off'); box(ax,'off'); set_nature_axis(ax);
plot(ax, beta_list, MSE_in_save, '-', 'Color',colors(1,:), 'LineWidth',1.2);
xline(ax, beta_opt, '--', 'Color',C.red, 'LineWidth',0.9);
yline(ax, MSE_IN_LIMIT, ':', 'Color',C.gray, 'LineWidth',0.9);
xlabel(ax,'\beta','FontSize',8.5);
ylabel(ax,'内区 MSE','FontName','Microsoft YaHei','FontSize',8.5);
text(ax,0.04,0.90,'(a)','Units','normalized','FontName','Times New Roman','FontSize',9);

ax = nexttile;
hold(ax,'on'); grid(ax,'off'); box(ax,'off'); set_nature_axis(ax);
plot(ax, beta_list, MSE_k_save, '-', 'Color',colors(3,:), 'LineWidth',1.2);
xline(ax, beta_opt, '--', 'Color',C.red, 'LineWidth',0.9);
xlabel(ax,'\beta','FontSize',8.5);
ylabel(ax,'外区斜率 MSE','FontName','Microsoft YaHei','FontSize',8.5);
text(ax,0.04,0.90,'(b)','Units','normalized','FontName','Times New Roman','FontSize',9);

ax = nexttile;
hold(ax,'on'); grid(ax,'off'); box(ax,'off'); set_nature_axis(ax);
plot(ax, beta_list, AIC_save, '-', 'Color',colors(2,:), 'LineWidth',1.2);
xline(ax, beta_opt, '--', 'Color',C.red, 'LineWidth',0.9);
xlabel(ax,'\beta','FontSize',8.5);
ylabel(ax,'AIC^*','FontName','Times New Roman','FontSize',8.5);
text(ax,0.04,0.90,'(c)','Units','normalized','FontName','Times New Roman','FontSize',9);

ax = nexttile;
hold(ax,'on'); grid(ax,'off'); box(ax,'off'); set_nature_axis(ax);
plot(ax, beta_list, k_end_save, '-', 'Color',C.black, 'LineWidth',1.2);
xline(ax, beta_opt, '--', 'Color',C.red, 'LineWidth',0.9);

for i = 1:N_lit
    ci = colors(mod(i-1,size(colors,1))+1,:);
    yline(ax, exp_sat_slope(p_lit(i,:), x_end_for_slope), ':', ...
        'Color',ci, ...
        'LineWidth',0.9);
end

dy_ref_end = mean(arrayfun(@(ii) exp_sat_slope(p_lit(ii,:), x_end_for_slope), 1:N_lit));
yline(ax, dy_ref_end, '--', 'Color',C.gray, 'LineWidth',1.0);

xlabel(ax,'\beta','FontSize',8.5);
ylabel(ax,'末端斜率','FontName','Microsoft YaHei','FontSize',8.5);
text(ax,0.04,0.90,'(d)','Units','normalized','FontName','Times New Roman','FontSize',9);

save_nature_figure(fig2, fullfile(out_dir,'不均匀腐蚀深度_固定C_beta多指标验证图'));

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

function y = exp_sat_eval(p, x)
    a = p(1);
    b = p(2);
    c = p(3);

    x = x(:);
    y = a .* (1 - exp(-b .* x)) + c;
end

function k = exp_sat_slope(p, x)
    a = p(1);
    b = p(2);

    x = x(:);
    k = a .* b .* exp(-b .* x);
end

function [p_best, mse_best] = fit_exp_sat(x, y)
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

    c0 = min(y) - 0.05 * yr;
    a0 = max(y) - c0;

    if a0 <= 0 || ~isfinite(a0)
        a0 = yr;
    end

    b0 = 1 / (max(x) - min(x) + eps);
    if ~isfinite(b0) || b0 <= 0
        b0 = 0.1;
    end

    p0 = [a0, b0, c0];

    opt = optimset('Display','off', ...
                   'MaxIter', 5000, ...
                   'MaxFunEvals', 20000, ...
                   'TolX', 1e-10, ...
                   'TolFun', 1e-10);

    obj = @(p) mean((exp_sat_eval(p,x) - y).^2) + penalty_exp_sat(p,x,y);
    p_best = fminsearch(obj, p0, opt);

    mse_best = mean((exp_sat_eval(p_best,x) - y).^2);
end

function pen = penalty_exp_sat(p, x, y)
    pen = 0;

    if any(~isfinite(p))
        pen = 1e30;
        return;
    end

    a = p(1);
    b = p(2);
    c = p(3);

    yr = max(y) - min(y);
    if yr <= 0
        yr = 1;
    end

    if a < 0
        pen = pen + 1e12 * abs(a)^2;
    end

    if b < 0
        pen = pen + 1e12 * abs(b)^2;
    end

    if b > 10
        pen = pen + 1e10 * (b - 10)^2;
    end

    a_high = max(5 * yr, max(y) - min(y) + eps);
    if a > a_high
        pen = pen + 1e8 * (a - a_high)^2;
    end

    c_low = min(y) - 2 * yr;
    c_high = max(y) + 2 * yr;

    if c < c_low
        pen = pen + 1e10 * (c - c_low)^2;
    end

    if c > c_high
        pen = pen + 1e10 * (c - c_high)^2;
    end

    y_test = exp_sat_eval(p, x);

    if any(~isfinite(y_test)) || any(abs(y_test) > 1e8)
        pen = pen + 1e20;
    end
end

function loss = obj_fun_exp_sat_fix_c(p_ab, c_fix, x_fit, w_in, w_out, x, y, x_max, x_temp, dy_ref)

    if any(~isfinite(p_ab))
        loss = 1e30;
        return;
    end

    a = p_ab(1);
    b = p_ab(2);

    if a <= 0 || b <= 0 || b > 10
        loss = 1e30;
        return;
    end

    p = [a, b, c_fix];

    y_pre = exp_sat_eval(p, x_fit);

    if any(~isfinite(y_pre)) || any(abs(y_pre) > 1e8)
        loss = 1e30;
        return;
    end

    idx_inner = x_fit <= x_max;
    x_inner = x_fit(idx_inner);

    y_interp = interp1(x, y, x_inner, 'linear', 'extrap');

    loss_in = sum(w_in .* (exp_sat_eval(p, x_inner) - y_interp).^2);

    idx_outer = x_fit > x_max;
    x_outer = x_fit(idx_outer);

    dy_pre = exp_sat_slope(p, x_outer);
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
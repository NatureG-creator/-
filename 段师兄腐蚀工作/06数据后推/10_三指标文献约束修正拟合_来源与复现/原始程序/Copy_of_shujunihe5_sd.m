%% ============================================================
% 质量损失率 - 腐蚀坑深度对数均值 修正拟合函数求解
% 模型形式：y = a*x^b + c
%
% 修正逻辑：
% 1. 4 组文献数据分别拟合完整模型 y = a*x^b + c；
% 2. 文献参考曲线采用各文献拟合曲线等权平均，仅用于绘图；
% 3. 文献参考斜率采用各文献斜率等权平均，用于外区趋势约束；
% 4. 自身数据先完整拟合得到 c_ori；
% 5. 修正阶段固定 c = c_ori，仅优化 a 和 b；
% 6. 通过 beta 遍历，在内区拟合精度和外区斜率趋势之间取得平衡；
% 7. 输出论文风格 tif/png/pdf 图片，可直接插入 Word。
%% ============================================================

clc; close all;

%% ========== 0. 数据输入 ==========
% 数据格式要求：
% 第 1 列：质量损失率 eta / %
% 第 2 列：腐蚀坑深度对数均值 mu_Hq

lit1 = xiaosiy_sd2;    % 文献1
lit2 = wzy_sd;         % 文献2
lit3 = gq_sd2;           % 文献3
lit4 = sd_5;           % 文献4
your = drfsd2;         % 自身小样本数据

% 坐标缩放系数，按厚度修正或数据统一处理结果修改
scale1 = 0.6250;
scale2 = 1.195;
scale3 = 0.6333;
scale4 = 1.2917;
scale_your = 1.00;

x1 = lit1(:,1) * scale1;      y1 = lit1(:,2);
x2 = lit2(:,1) * scale2;      y2 = lit2(:,2);
x3 = lit3(:,1) * scale3;      y3 = lit3(:,2);
x4 = lit4(:,1) * scale4;      y4 = lit4(:,2);
x  = your(:,1) * scale_your;  y  = your(:,2);

% 数据清洗、排序、重复 x 合并
[x1,y1] = clean_xy(x1,y1);
[x2,y2] = clean_xy(x2,y2);
[x3,y3] = clean_xy(x3,y3);
[x4,y4] = clean_xy(x4,y4);
[x,y]   = clean_xy(x,y);

if numel(x) < 3
    error('自身数据点少于 3 个，不建议进行带 C 项幂函数修正拟合。');
end

x_max = max(x);                         % 内外区分界点：自身数据终点
x_outer_end = max(x) * 1.40;            % 外推区终点，可按需要修改
x_outer_end = max(x_outer_end, x_max*1.05);

x_fit  = linspace(min(x), x_outer_end, 400)';
x_plot = linspace(min([x1;x2;x3;x4;x]), x_outer_end, 400)';
x_temp = linspace(x_max, x_outer_end, 50)';   % 外区斜率采样点

% 末端斜率检查位置，若 30 小于自身终点，则自动改为外推终点
x_end_for_slope = 30;
if x_end_for_slope <= x_max
    x_end_for_slope = x_outer_end;
end

%% ========== 1. 图像输出设置 ==========
out_dir = '腐蚀坑深度对数均值_固定C修正拟合输出';
if ~exist(out_dir,'dir')
    mkdir(out_dir);
end

fig_w = 13;       % cm
fig_h = 8.5;      % cm
ax_pos = [0.16 0.17 0.78 0.72];

x_label_text = '质量损失率 η / %';
y_label_text = '腐蚀坑深度对数均值 μ_Hq';

% 论文图配色
C.blue      = [0.000 0.447 0.741];
C.orange    = [0.850 0.325 0.098];
C.green     = [0.466 0.674 0.188];
C.purple    = [0.494 0.184 0.556];
C.black     = [0.000 0.000 0.000];
C.gray      = [0.450 0.450 0.450];
C.lightgray = [0.700 0.700 0.700];
C.red       = [0.635 0.078 0.184];

%% ========== 2. 4组文献数据分别拟合：y = a*x^b + c ==========
[p1, mse1] = fit_power_c(x1,y1);
[p2, mse2] = fit_power_c(x2,y2);
[p3, mse3] = fit_power_c(x3,y3);
[p4, mse4] = fit_power_c(x4,y4);

p_lit = [p1; p2; p3; p4];

a1 = p1(1); b1 = p1(2); c1 = p1(3);
a2 = p2(1); b2 = p2(2); c2 = p2(3);
a3 = p3(1); b3 = p3(2); c3 = p3(3);
a4 = p4(1); b4 = p4(2); c4 = p4(3);

% 文献参考曲线：各文献拟合曲线等权平均，仅用于画图
Y_ref_all = [
    power_c_eval(p1, x_plot), ...
    power_c_eval(p2, x_plot), ...
    power_c_eval(p3, x_plot), ...
    power_c_eval(p4, x_plot)
];

y_ref_fit = mean(Y_ref_all, 2);

% 文献参考斜率：各文献拟合斜率等权平均，用于外区约束
K_ref_all = [
    power_c_slope(p1, x_temp), ...
    power_c_slope(p2, x_temp), ...
    power_c_slope(p3, x_temp), ...
    power_c_slope(p4, x_temp)
];

dy_ref = mean(K_ref_all, 2);

%% ========== 3. 自身数据原始完整拟合 ==========
[p_ori, mse_ori] = fit_power_c(x,y);

a_ori = p_ori(1);
b_ori = p_ori(2);
c_ori = p_ori(3);

% 修正阶段固定 c，不参与优化
c_fix = c_ori;

%% ========== 4. 基础客观权重计算 ==========
% 内区基础权重：自身原始拟合误差的倒数
MSE_in_base = mean((power_c_eval(p_ori,x) - y).^2);
win_base = 1 / (MSE_in_base + eps);

% 外区基础权重：自身原始拟合斜率与文献融合参考斜率的 MSE 反比
dy_ori = power_c_slope(p_ori, x_temp);
MSE_k_base = mean((dy_ori - dy_ref).^2);
wout_base = 1 / (MSE_k_base + eps);

%% ========== 5. 遍历 beta，求解最优修正模型 ==========
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

    % 修正阶段只优化 a 和 b
    p0_ab = [a_ori, b_ori];

    p_ab_opt = fminsearch(@(p_ab) obj_fun_power_c_fix_c( ...
        p_ab, c_fix, x_fit, win, wout, x, y, x_max, x_temp, dy_ref), ...
        p0_ab, opt);

    p_opt = [p_ab_opt(1), p_ab_opt(2), c_fix];

    % 内区误差：修正曲线在自身样本点处的拟合误差
    y_in_fit = power_c_eval(p_opt, x);
    MSE_in = mean((y_in_fit - y).^2);

    % 若过度牺牲自身数据拟合质量，则不参与筛选
    if MSE_in > MSE_IN_LIMIT || any(~isfinite(p_opt)) || p_opt(1) <= 0
        continue;
    end

    % 外区斜率误差
    dy_pre = power_c_slope(p_opt, x_temp);
    MSE_k = mean((dy_pre - dy_ref).^2);

    % 综合信息评价指标 AIC*
    n_data = numel(x);
    m_out = numel(x_temp);
    p_num = 2;   % 修正阶段只优化 a 和 b

    AIC_star = n_data*log(MSE_in + eps) + ...
               m_out*log(MSE_k + eps) + ...
               2*p_num;

    % 末端斜率
    k_end = power_c_slope(p_opt, x_end_for_slope);

    MSE_in_save(i) = MSE_in;
    MSE_k_save(i)  = MSE_k;
    AIC_save(i)    = AIC_star;
    k_end_save(i)  = k_end;
    a_save(i)      = p_opt(1);
    b_save(i)      = p_opt(2);
    c_save(i)      = p_opt(3);
end

%% ========== 6. 确定最优 beta 和最终修正模型 ==========
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

% 拟合曲线
y_ori_fit = power_c_eval(p_ori, x_plot);
y_opt_fit = power_c_eval(p_opt_final, x_plot);

%% ========== 7. 命令行输出最终结果 ==========
disp(' ');
disp('===========================================================');
disp('      质量损失率 - 腐蚀坑深度对数均值 修正拟合结果');
disp('===========================================================');
disp(' ');

disp('【文献数据拟合：y = a*x^b + c】');
fprintf('文献1：y = %.6f*x^{%.6f} + %.6f，MSE = %.6g', a1,b1,c1,mse1); disp(' ');
fprintf('文献2：y = %.6f*x^{%.6f} + %.6f，MSE = %.6g', a2,b2,c2,mse2); disp(' ');
fprintf('文献3：y = %.6f*x^{%.6f} + %.6f，MSE = %.6g', a3,b3,c3,mse3); disp(' ');
fprintf('文献4：y = %.6f*x^{%.6f} + %.6f，MSE = %.6g', a4,b4,c4,mse4); disp(' ');
disp(' ');

disp('【文献融合说明】');
disp('参考曲线采用各文献拟合曲线等权平均；参考斜率采用各文献斜率等权平均。');
disp(' ');

disp('【自身数据原始无约束拟合】');
fprintf('y_ori = %.6f*x^{%.6f} + %.6f', a_ori,b_ori,c_ori); disp(' ');
fprintf('原始内区 MSE = %.6g', MSE_in_base); disp(' ');
fprintf('外区基础斜率 MSE = %.6g', MSE_k_base); disp(' '); disp(' ');

disp('【修正阶段说明】');
fprintf('固定 c = %.6f，仅优化 a 和 b。', c_fix); disp(' '); disp(' ');

disp('===========================================================');
disp('最终最优修正拟合公式：');
fprintf('y = %.6f*x^{%.6f} + %.6f', a_opt,b_opt,c_opt); disp(' ');
disp('===========================================================');
fprintf('最优权重放大系数 beta = %.4f', beta_opt); disp(' ');
fprintf('修正后内区 MSE = %.6g', final_mse); disp(' ');
fprintf('当前误差相对原始误差倍数 = %.4f', mse_ratio); disp(' ');
fprintf('允许上限倍数 = %.2f', ALLOW_MULTIPLE); disp(' ');
fprintf('最优 AIC* = %.6f', AIC_save(idx_opt)); disp(' ');
fprintf('外区斜率 MSE = %.6g', MSE_k_save(idx_opt)); disp(' ');
fprintf('末端斜率 k(x=%.2f) = %.6g', x_end_for_slope, k_end_save(idx_opt)); disp(' ');
disp(' ');

%% ========== 8. 输出结果表 ==========
model_name = {
    '文献1';
    '文献2';
    '文献3';
    '文献4';
    '文献融合参考';
    '自身原始拟合';
    '最终修正拟合'
};

a_col = [a1; a2; a3; a4; NaN; a_ori; a_opt];
b_col = [b1; b2; b3; b4; NaN; b_ori; b_opt];
c_col = [c1; c2; c3; c4; NaN; c_ori; c_opt];

formula_col = strings(numel(model_name),1);

formula_col(1) = sprintf('y = %.6f*x^{%.6f} + %.6f', a1,b1,c1);
formula_col(2) = sprintf('y = %.6f*x^{%.6f} + %.6f', a2,b2,c2);
formula_col(3) = sprintf('y = %.6f*x^{%.6f} + %.6f', a3,b3,c3);
formula_col(4) = sprintf('y = %.6f*x^{%.6f} + %.6f', a4,b4,c4);
formula_col(5) = "参考曲线为各文献拟合曲线等权平均；参考斜率为各文献斜率等权平均";
formula_col(6) = sprintf('y = %.6f*x^{%.6f} + %.6f', a_ori,b_ori,c_ori);
formula_col(7) = sprintf('y = %.6f*x^{%.6f} + %.6f', a_opt,b_opt,c_opt);

T_param = table(model_name, formula_col, a_col, b_col, c_col, ...
    'VariableNames', {'模型名称','拟合函数','a','b','c'});

T_metric = table(beta_opt, c_fix, MSE_in_base, final_mse, mse_ratio, MSE_k_base, ...
    MSE_k_save(idx_opt), AIC_save(idx_opt), k_end_save(idx_opt), ...
    'VariableNames', {'最优beta','固定c','原始内区MSE','修正内区MSE','内区MSE倍数','原始外区斜率MSE','修正外区斜率MSE','AIC_star','末端斜率'});

writetable(T_param, fullfile(out_dir,'腐蚀坑深度对数均值_固定C修正拟合参数表.xlsx'), 'Sheet','模型参数');
writetable(T_metric, fullfile(out_dir,'腐蚀坑深度对数均值_固定C修正拟合参数表.xlsx'), 'Sheet','评价指标');
writetable(T_param, fullfile(out_dir,'腐蚀坑深度对数均值_固定C修正拟合参数表.csv'));

%% ========== 9. 论文风格图 1：最终修正拟合图 ==========
fig1 = figure('Units','centimeters','Position',[4,4,fig_w,fig_h]);
set(fig1,'Color','w');

ax1 = axes('Parent',fig1,'Position',ax_pos);
hold(ax1,'on');
grid(ax1,'off');
box(ax1,'off');
set_nature_axis(ax1);

% 文献数据和拟合曲线
h_lit1 = plot(ax1, x1,y1,'o','MarkerSize',4.2,'MarkerFaceColor','none','MarkerEdgeColor',C.blue,'LineWidth',0.8);
plot(ax1, x_plot, power_c_eval(p1,x_plot), '-', 'Color',C.blue, 'LineWidth',1.0);

h_lit2 = plot(ax1, x2,y2,'s','MarkerSize',4.2,'MarkerFaceColor','none','MarkerEdgeColor',C.orange,'LineWidth',0.8);
plot(ax1, x_plot, power_c_eval(p2,x_plot), '-', 'Color',C.orange, 'LineWidth',1.0);

h_lit3 = plot(ax1, x3,y3,'^','MarkerSize',4.4,'MarkerFaceColor','none','MarkerEdgeColor',C.green,'LineWidth',0.8);
plot(ax1, x_plot, power_c_eval(p3,x_plot), '-', 'Color',C.green, 'LineWidth',1.0);

h_lit4 = plot(ax1, x4,y4,'d','MarkerSize',4.4,'MarkerFaceColor','none','MarkerEdgeColor',C.purple,'LineWidth',0.8);
plot(ax1, x_plot, power_c_eval(p4,x_plot), '-', 'Color',C.purple, 'LineWidth',1.0);

% 文献融合参考、自身原始拟合、最终修正拟合
h_ref = plot(ax1, x_plot, y_ref_fit, '-.', 'Color',C.gray, 'LineWidth',1.5);
h_ori = plot(ax1, x_plot, y_ori_fit, '--', 'Color',C.lightgray, 'LineWidth',1.5);
h_opt = plot(ax1, x_plot, y_opt_fit, '-', 'Color',C.red, 'LineWidth',2.2);

% 自身数据
h_your = plot(ax1, x,y,'o','MarkerSize',5.2,'MarkerFaceColor',C.black,'MarkerEdgeColor','k','LineWidth',0.7);

% 内外区分界线
h_xmax = xline(ax1, x_max, '--', 'Color',[0.25 0.25 0.25], 'LineWidth',0.9);

xlabel(ax1, x_label_text, 'FontName','Microsoft YaHei', 'FontSize',9.5);
ylabel(ax1, y_label_text, 'FontName','Microsoft YaHei', 'FontSize',9.5);

legend(ax1, [h_lit1,h_lit2,h_lit3,h_lit4,h_ref,h_ori,h_opt,h_your,h_xmax], ...
    {'文献1','文献2','文献3','文献4','文献融合参考','自身原始拟合','最终修正拟合','自身数据','自身数据终点'}, ...
    'Location','best', 'Box','off', 'FontName','Microsoft YaHei', 'FontSize',6.8);

xlim(ax1, [min(x_plot), max(x_plot)]);

y_all = [y1; y2; y3; y4; y; y_ref_fit(:); y_ori_fit(:); y_opt_fit(:)];
yr = range(y_all);
if yr <= 0
    yr = 1;
end
ylim(ax1, [min(y_all)-0.05*yr, max(y_all)+0.08*yr]);

save_nature_figure(fig1, fullfile(out_dir,'腐蚀坑深度对数均值_固定C最终修正拟合图'));

%% ========== 10. 论文风格图 2：beta 多指标验证图 ==========
fig2 = figure('Units','centimeters','Position',[4,4,fig_w,fig_h]);
set(fig2,'Color','w');

tiledlayout(fig2, 2, 2, 'Padding','compact', 'TileSpacing','compact');

ax = nexttile; hold(ax,'on'); grid(ax,'off'); box(ax,'off'); set_nature_axis(ax);
plot(ax, beta_list, MSE_in_save, '-', 'Color',C.blue, 'LineWidth',1.2);
xline(ax, beta_opt, '--', 'Color',C.red, 'LineWidth',0.9);
yline(ax, MSE_IN_LIMIT, ':', 'Color',C.gray, 'LineWidth',0.9);
xlabel(ax,'\beta','FontSize',8.5);
ylabel(ax,'内区 MSE','FontName','Microsoft YaHei','FontSize',8.5);
text(ax,0.04,0.90,'(a)','Units','normalized','FontName','Times New Roman','FontSize',9);

ax = nexttile; hold(ax,'on'); grid(ax,'off'); box(ax,'off'); set_nature_axis(ax);
plot(ax, beta_list, MSE_k_save, '-', 'Color',C.green, 'LineWidth',1.2);
xline(ax, beta_opt, '--', 'Color',C.red, 'LineWidth',0.9);
xlabel(ax,'\beta','FontSize',8.5);
ylabel(ax,'外区斜率 MSE','FontName','Microsoft YaHei','FontSize',8.5);
text(ax,0.04,0.90,'(b)','Units','normalized','FontName','Times New Roman','FontSize',9);

ax = nexttile; hold(ax,'on'); grid(ax,'off'); box(ax,'off'); set_nature_axis(ax);
plot(ax, beta_list, AIC_save, '-', 'Color',C.orange, 'LineWidth',1.2);
xline(ax, beta_opt, '--', 'Color',C.red, 'LineWidth',0.9);
xlabel(ax,'\beta','FontSize',8.5);
ylabel(ax,'AIC*','FontName','Times New Roman','FontSize',8.5);
text(ax,0.04,0.90,'(c)','Units','normalized','FontName','Times New Roman','FontSize',9);

ax = nexttile; hold(ax,'on'); grid(ax,'off'); box(ax,'off'); set_nature_axis(ax);
plot(ax, beta_list, k_end_save, '-', 'Color',C.black, 'LineWidth',1.2);
xline(ax, beta_opt, '--', 'Color',C.red, 'LineWidth',0.9);

yline(ax, power_c_slope(p1,x_end_for_slope), ':', 'Color',C.blue, 'LineWidth',0.9);
yline(ax, power_c_slope(p2,x_end_for_slope), ':', 'Color',C.orange, 'LineWidth',0.9);
yline(ax, power_c_slope(p3,x_end_for_slope), ':', 'Color',C.green, 'LineWidth',0.9);
yline(ax, power_c_slope(p4,x_end_for_slope), ':', 'Color',C.purple, 'LineWidth',0.9);

% 文献融合参考末端斜率
dy_ref_end = mean([ ...
    power_c_slope(p1,x_end_for_slope), ...
    power_c_slope(p2,x_end_for_slope), ...
    power_c_slope(p3,x_end_for_slope), ...
    power_c_slope(p4,x_end_for_slope) ...
]);

yline(ax, dy_ref_end, '--', 'Color',C.gray, 'LineWidth',1.0);

xlabel(ax,'\beta','FontSize',8.5);
ylabel(ax,'末端斜率','FontName','Microsoft YaHei','FontSize',8.5);
text(ax,0.04,0.90,'(d)','Units','normalized','FontName','Times New Roman','FontSize',9);

save_nature_figure(fig2, fullfile(out_dir,'腐蚀坑深度对数均值_固定C_beta多指标验证图'));

fprintf('已生成输出文件夹：%s', out_dir); disp(' ');
disp('图像文件：tif / png / pdf 均已导出，可直接插入 Word。');

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

    % 合并重复 x，取对应 y 的平均值
    [x_unique, ~, ic] = unique(x);
    y_mean = accumarray(ic, y, [], @mean);

    x_clean = x_unique;
    y_clean = y_mean;
end

function y = power_c_eval(p, x)
    a = p(1);
    b = p(2);
    c = p(3);

    x = x(:);
    y = a .* x.^b + c;
end

function k = power_c_slope(p, x)
    a = p(1);
    b = p(2);

    x = x(:);
    k = a .* b .* x.^(b - 1);
end

function [p_best, mse_best] = fit_power_c(x, y)
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

    % 初值：先给 c 一个略低于最小 y 的值，再对 y-c 做对数线性回归
    c0 = min(y) - 0.05 * yr;
    yy = y - c0;

    if any(yy <= 0)
        yy = yy - min(yy) + 0.01 * yr;
    end

    pp = polyfit(log(x), log(yy), 1);
    b0 = pp(1);
    a0 = exp(pp(2));

    if ~isfinite(a0) || ~isfinite(b0) || a0 <= 0
        a0 = yr / (mean(x)^0.5 + eps);
        b0 = 0.5;
    end

    p0 = [a0, b0, c0];

    opt = optimset('Display','off', ...
                   'MaxIter', 5000, ...
                   'MaxFunEvals', 20000, ...
                   'TolX', 1e-10, ...
                   'TolFun', 1e-10);

    obj = @(p) mean((power_c_eval(p,x) - y).^2) + penalty_power_c(p,x,y);
    p_best = fminsearch(obj, p0, opt);

    mse_best = mean((power_c_eval(p_best,x) - y).^2);
end

function pen = penalty_power_c(p, x, y)
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

    % a 应为正，b 约束在合理范围内，避免外推异常发散
    if a <= 0
        pen = pen + 1e20 + 1e12 * abs(a)^2;
    end

    if b < -5
        pen = pen + 1e10 * (b + 5)^2;
    end

    if b > 5
        pen = pen + 1e10 * (b - 5)^2;
    end

    % c 不应远离数据范围过多
    c_low = min(y) - 2 * yr;
    c_high = max(y) + 2 * yr;

    if c < c_low
        pen = pen + 1e10 * (c - c_low)^2;
    end

    if c > c_high
        pen = pen + 1e10 * (c - c_high)^2;
    end

    y_test = power_c_eval(p, x);

    if any(~isfinite(y_test)) || any(abs(y_test) > 1e8)
        pen = pen + 1e20;
    end
end

function loss = obj_fun_power_c_fix_c(p_ab, c_fix, x_fit, w_in, w_out, x, y, x_max, x_temp, dy_ref)
    if any(~isfinite(p_ab))
        loss = 1e30;
        return;
    end

    a = p_ab(1);
    b = p_ab(2);

    if a <= 0 || b < -5 || b > 5
        loss = 1e30;
        return;
    end

    p = [a, b, c_fix];

    y_pre = power_c_eval(p, x_fit);

    if any(~isfinite(y_pre)) || any(abs(y_pre) > 1e8)
        loss = 1e30;
        return;
    end

    % 内区拟合误差
    idx_inner = x_fit <= x_max;
    x_inner = x_fit(idx_inner);

    y_interp = interp1(x, y, x_inner, 'linear', 'extrap');

    loss_in = sum(w_in .* (power_c_eval(p, x_inner) - y_interp).^2);

    % 外区斜率误差
    idx_outer = x_fit > x_max;
    x_outer = x_fit(idx_outer);

    dy_pre = power_c_slope(p, x_outer);
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
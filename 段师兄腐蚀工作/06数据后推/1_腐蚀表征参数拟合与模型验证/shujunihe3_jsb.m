%% ============================================================
%% 质量损失率 - 腐蚀坑径深比对数均值 拟合函数验证
%% 线性模型 / 幂函数模型 / 指数模型 / 两阶段对数模型
%%
%% 功能：
%% 1. 按质量损失率升序排序
%% 2. 前 90% 数据作为拟合集，后 10% 数据作为外推验证集
%% 3. 小样本数据自动跳过两阶段对数模型
%% 4. 两阶段对数模型加入截距项，并通过候选分段点搜索确定分段点
%% 5. 输出 R2、RMSE、测试集RMSE、平均绝对相对误差 AARE
%% 6. 输出无 title、无网格、论文风格拟合图和残差图
%% ============================================================

clc;

%% ========== 1. 数据输入 ==========
% 数据要求：
% 第 1 列：质量损失率 eta / %
% 第 2 列：腐蚀坑径深比对数均值 mu_Rq
data = jsb_5;

x = data(:,1);     % 质量损失率
y = data(:,2);     % 腐蚀坑径深比对数均值

% 删除无效数据；对数模型要求 x > 0 且 y > 0
valid = isfinite(x) & isfinite(y) & x > 0 & y > 0;

if sum(~valid) > 0
    fprintf('提示：已剔除 %d 个非正值、NaN 或 Inf 数据点。\n', sum(~valid));
end

x = x(valid);
y = y(valid);

% 按质量损失率从小到大排序
[x, idx] = sort(x(:));
y = y(idx);

n = length(x);

if n < 4
    error('有效数据点数量过少，不建议进行模型拟合。');
end

%% ========== 2. 基本参数设置 ==========
x_extrap = 12;          % 外推上限，可按数据范围修改
train_ratio = 0.90;    % 前 90% 作为拟合集，后 10% 作为外推验证集

% 两阶段对数模型左右两侧最少数据点数
min_pts_each_side = 2;

% 若外推上限小于数据最大值，则自动修正
if x_extrap < max(x)
    x_extrap = max(x) * 1.05;
    fprintf('提示：原外推上限小于数据最大值，已自动调整为 %.4f。\n', x_extrap);
end

% 拟合集 / 验证集划分
n_train = round(n * train_ratio);

% 保证验证集至少有 1 个点
n_train = min(n_train, n - 1);

% 保证拟合集至少有 3 个点
n_train = max(n_train, 3);

x_train = x(1:n_train);
y_train = y(1:n_train);

x_test  = x(n_train+1:end);
y_test  = y(n_train+1:end);

x_fit = linspace(min(x), x_extrap, 400)';

%% ========== 3. 图像统一设置 ==========
fig_w = 13;      % 图宽，单位 cm
fig_h = 8.5;     % 图高，单位 cm

% 坐标轴位置，保证拟合图和残差图尺寸一致
ax_pos = [0.16 0.17 0.78 0.72];

% 图中文字
% 图中文字
x_label_text = '质量损失率 \eta / %';
y_label_text = '腐蚀坑径深比对数均值 \lambda_q';

%% ========== 4. 模型名称与颜色 ==========
% 颜色顺序与前面图保持一致：
% 线性：蓝色；幂函数：橙红色；指数：绿色；两阶段：紫色
model_names = {
    '线性模型', ...
    '幂函数模型', ...
    '指数模型', ...
    '两阶段对数模型'
};

colors_all = [
    0.000, 0.447, 0.741;   % 蓝色
    0.850, 0.325, 0.098;   % 橙红色
    0.466, 0.674, 0.188;   % 绿色
    0.494, 0.184, 0.556;   % 紫色
];

%% ========== 5. 初始化 ==========
results = [];                 % R2, RMSE, 测试集RMSE, AARE
params_cell = {};
formula_cell = {};
y_fit_cell = {};
y_pred_cell = {};
y_ext_cell = {};
used_model_names = {};
used_colors = [];

opts = optimoptions('lsqcurvefit', ...
    'Display','off', ...
    'MaxFunctionEvaluations',5000, ...
    'MaxIterations',2000);

range_y = max(y_train) - min(y_train);

if range_y <= 0
    range_y = max(abs(y_train));
end

if range_y <= 0
    range_y = 1;
end

%% ============================================================
%% 6. 线性模型： y = a*x + b
%% ============================================================
linear_fun = @(p,x) p(1).*x + p(2);

x0 = polyfit(x_train, y_train, 1);
lb = [-Inf, -Inf];
ub = [ Inf,  Inf];

p = lsqcurvefit(linear_fun, x0, x_train, y_train, lb, ub, opts);

y_fit  = linear_fun(p, x);
y_pred = linear_fun(p, x_test);
y_ext  = linear_fun(p, x_fit);

[results, used_model_names, used_colors, params_cell, formula_cell, ...
    y_fit_cell, y_pred_cell, y_ext_cell] = add_model_result( ...
    results, used_model_names, used_colors, params_cell, formula_cell, ...
    y_fit_cell, y_pred_cell, y_ext_cell, ...
    model_names{1}, colors_all(1,:), p, y, y_fit, y_test, y_pred, y_ext, ...
    sprintf('y = %.6f x + %.6f', p(1), p(2)));

%% ============================================================
%% 7. 幂函数模型： y = a*x^b + c
%% ============================================================
power_fun = @(p,x) p(1).*x.^p(2) + p(3);

x0 = [range_y, 0.5, min(y_train)];
lb = [-Inf, -10, -Inf];
ub = [ Inf,  10,  Inf];

p = lsqcurvefit(power_fun, x0, x_train, y_train, lb, ub, opts);

y_fit  = power_fun(p, x);
y_pred = power_fun(p, x_test);
y_ext  = power_fun(p, x_fit);

[results, used_model_names, used_colors, params_cell, formula_cell, ...
    y_fit_cell, y_pred_cell, y_ext_cell] = add_model_result( ...
    results, used_model_names, used_colors, params_cell, formula_cell, ...
    y_fit_cell, y_pred_cell, y_ext_cell, ...
    model_names{2}, colors_all(2,:), p, y, y_fit, y_test, y_pred, y_ext, ...
    sprintf('y = %.6f x^{%.6f} + %.6f', p(1), p(2), p(3)));

%% ============================================================
%% 8. 指数模型： y = a*exp(-k*x) + b
%% ============================================================
exp_fun = @(p,x) p(1).*exp(-p(2).*x) + p(3);

x0 = [range_y, 0.1, min(y_train)];
lb = [-Inf, -Inf, -Inf];
ub = [ Inf,  Inf,  Inf];

p = lsqcurvefit(exp_fun, x0, x_train, y_train, lb, ub, opts);

y_fit  = exp_fun(p, x);
y_pred = exp_fun(p, x_test);
y_ext  = exp_fun(p, x_fit);

[results, used_model_names, used_colors, params_cell, formula_cell, ...
    y_fit_cell, y_pred_cell, y_ext_cell] = add_model_result( ...
    results, used_model_names, used_colors, params_cell, formula_cell, ...
    y_fit_cell, y_pred_cell, y_ext_cell, ...
    model_names{3}, colors_all(3,:), p, y, y_fit, y_test, y_pred, y_ext, ...
    sprintf('y = %.6f exp(-%.6f x) + %.6f', p(1), p(2), p(3)));

%% ============================================================
%% 9. 两阶段对数模型
%% log(y)=A+n1*log(x), x<x1
%% log(y)=A+n1*log(x)+n2*log(x/x1), x>=x1
%% ============================================================
use_two_stage = true;

if n_train < 2 * min_pts_each_side
    use_two_stage = false;
    fprintf('\n提示：拟合集数据点数量为 %d，少于两阶段对数模型所需的最小数量 %d。\n', ...
        n_train, 2 * min_pts_each_side);
    fprintf('因此本次跳过两阶段对数模型。\n\n');
end

if use_two_stage
    [p, ok] = fit_two_stage_log_model(x_train, y_train, min_pts_each_side);

    if ok
        y_fit  = two_stage_log_predict(p, x);
        y_pred = two_stage_log_predict(p, x_test);
        y_ext  = two_stage_log_predict(p, x_fit);

        formula_str = sprintf(['ln(y)=%.6f + %.6f ln(x), x < %.6f; ', ...
                               'ln(y)=%.6f + %.6f ln(x) + %.6f ln(x/%.6f), x >= %.6f'], ...
                               p(1), p(2), p(4), ...
                               p(1), p(2), p(3), p(4), p(4));

        [results, used_model_names, used_colors, params_cell, formula_cell, ...
            y_fit_cell, y_pred_cell, y_ext_cell] = add_model_result( ...
            results, used_model_names, used_colors, params_cell, formula_cell, ...
            y_fit_cell, y_pred_cell, y_ext_cell, ...
            model_names{4}, colors_all(4,:), p, y, y_fit, y_test, y_pred, y_ext, ...
            formula_str);
    else
        use_two_stage = false;
        fprintf('\n提示：未找到满足左右数据点数量要求的合理分段点。\n');
        fprintf('因此本次跳过两阶段对数模型。\n\n');
    end
end

n_models = length(used_model_names);

%% ============================================================
%% 10. 主图：模型拟合与外推对比
%% ============================================================
fig1 = figure('Units','centimeters','Position',[4,4,fig_w,fig_h]);
set(gcf,'Color','w');

ax1 = axes('Parent',fig1,'Position',ax_pos);
hold(ax1,'on');
grid(ax1,'off');
box(ax1,'off');

set(ax1, ...
    'FontName','Microsoft YaHei', ...
    'FontSize',8.5, ...
    'LineWidth',0.8, ...
    'TickDir','out', ...
    'TickLength',[0.018 0.018], ...
    'XMinorTick','off', ...
    'YMinorTick','off', ...
    'Layer','top');

% 绘制拟合曲线
h_fit = gobjects(n_models,1);

for m = 1:n_models
    h_fit(m) = plot(ax1, x_fit, y_ext_cell{m}, '-', ...
        'Color', used_colors(m,:), ...
        'LineWidth',1.6);
end

% 原始数据点：黑色实心圆
h_data = plot(ax1, x, y, 'o', ...
    'MarkerSize',4.8, ...
    'MarkerEdgeColor','k', ...
    'MarkerFaceColor',[0.15 0.15 0.15], ...
    'LineWidth',0.6);

% 测试集：黑边空心方块
h_test = plot(ax1, x_test, y_test, 's', ...
    'MarkerSize',5.2, ...
    'MarkerEdgeColor','k', ...
    'MarkerFaceColor',[1 1 1], ...
    'LineWidth',0.8);

xlabel(ax1, x_label_text, ...
    'FontName','Microsoft YaHei', ...
    'FontSize',9.5);

ylabel(ax1, y_label_text, ...
    'FontName','Microsoft YaHei', ...
    'FontSize',9.5);

legend(ax1, [h_fit; h_data; h_test], ...
    [used_model_names(:); {'原始数据'; '测试集'}], ...
    'Location','northwest', ...
    'Box','off', ...
    'FontName','Microsoft YaHei', ...
    'FontSize',7.5);

xlim(ax1, [min(x)*0.95, x_extrap]);

y_all = y;
for m = 1:n_models
    y_all = [y_all; y_ext_cell{m}];
end

ylim(ax1, [min(y_all)*0.98, max(y_all)*1.02]);

% 注意：不加 title，保持论文图格式一致

exportgraphics(fig1, '径深比_模型拟合图.pdf', 'ContentType','vector');
exportgraphics(fig1, '径深比_模型拟合图.png', 'Resolution',600);
exportgraphics(fig1, '径深比_模型拟合图.tif', 'Resolution',600);

%% ============================================================
%% 11. 残差图
%% ============================================================
fig2 = figure('Units','centimeters','Position',[4,4,fig_w,fig_h]);
set(gcf,'Color','w');

ax2 = axes('Parent',fig2,'Position',ax_pos);
hold(ax2,'on');
grid(ax2,'off');
box(ax2,'off');

set(ax2, ...
    'FontName','Microsoft YaHei', ...
    'FontSize',8.5, ...
    'LineWidth',0.8, ...
    'TickDir','out', ...
    'TickLength',[0.018 0.018], ...
    'XMinorTick','off', ...
    'YMinorTick','off', ...
    'Layer','top');

h_res = gobjects(n_models,1);

for m = 1:n_models
    residual = y - y_fit_cell{m};
    h_res(m) = plot(ax2, x, residual, '-', ...
        'Color', used_colors(m,:), ...
        'LineWidth',1.3);
end

yline(ax2, 0, '--k', 'LineWidth',0.8);

xlabel(ax2, x_label_text, ...
    'FontName','Microsoft YaHei', ...
    'FontSize',9.5);

ylabel(ax2, '残差', ...
    'FontName','Microsoft YaHei', ...
    'FontSize',9.5);

legend(ax2, h_res, used_model_names(:), ...
    'Location','best', ...
    'Box','off', ...
    'FontName','Microsoft YaHei', ...
    'FontSize',7.5);

% 注意：不加 title，保持论文图格式一致

exportgraphics(fig2, '径深比_模型残差图.pdf', 'ContentType','vector');
exportgraphics(fig2, '径深比_模型残差图.png', 'Resolution',600);
exportgraphics(fig2, '径深比_模型残差图.tif', 'Resolution',600);

%% ============================================================
%% 12. 命令行输出拟合公式与评价指标
%% ============================================================
fprintf('\n');
fprintf('=============================================================\n');
fprintf('       质量损失率 - 腐蚀坑径深比对数均值 模型拟合结果\n');
fprintf('=============================================================\n\n');

fprintf('数据点总数：%d\n', n);
fprintf('拟合集数据点数：%d\n', length(x_train));
fprintf('验证集数据点数：%d\n\n', length(x_test));

for m = 1:n_models
    fprintf('【%d. %s】\n', m, used_model_names{m});
    fprintf('   %s\n', formula_cell{m});
    fprintf('   R² = %.4f, RMSE = %.4f, 测试集RMSE = %.4f, 平均绝对相对误差 = %.2f%%\n\n', ...
        results(m,1), results(m,2), results(m,3), results(m,4));
end

fprintf('模型评价表：\n');
fprintf('--------------------------------------------------------------------------\n');
fprintf('模型名称\t\tR²\t\tRMSE\t\t测试集RMSE\t平均绝对相对误差(%%)\n');
fprintf('--------------------------------------------------------------------------\n');

for m = 1:n_models
    fprintf('%-16s\t%.4f\t%.4f\t%.4f\t\t%.2f\n', ...
        used_model_names{m}, results(m,1), results(m,2), results(m,3), results(m,4));
end

fprintf('--------------------------------------------------------------------------\n');

if use_two_stage && n_models == 4
    p4 = params_cell{4};
    fprintf('\n两阶段对数模型分段点检查：\n');
    fprintf('分段点 x1 = %.6f\n', p4(4));
    fprintf('分段点左侧数据点数量 = %d\n', sum(x < p4(4)));
    fprintf('分段点右侧数据点数量 = %d\n', sum(x >= p4(4)));
else
    fprintf('\n两阶段对数模型未启用或未成功拟合。\n');
end

%% ============================================================
%% 13. 输出 Excel 和 CSV 评价表
%% ============================================================
T = table( ...
    used_model_names(:), ...
    formula_cell(:), ...
    results(:,1), ...
    results(:,2), ...
    results(:,3), ...
    results(:,4), ...
    'VariableNames', {'模型名称','最终拟合模型表达式','R2','RMSE','测试集RMSE','平均绝对相对误差_百分比'} ...
);

writetable(T, '径深比_模型评价表.xlsx', 'Sheet', '模型评价');
writetable(T, '径深比_模型评价表.csv');

fprintf('\n已生成文件：\n');
fprintf('1. 径深比_模型拟合图.pdf / png / tif\n');
fprintf('2. 径深比_模型残差图.pdf / png / tif\n');
fprintf('3. 径深比_模型评价表.xlsx\n');
fprintf('4. 径深比_模型评价表.csv\n');

%% ============================================================
%% 局部函数
%% ============================================================

function [results, used_model_names, used_colors, params_cell, formula_cell, ...
          y_fit_cell, y_pred_cell, y_ext_cell] = add_model_result( ...
          results, used_model_names, used_colors, params_cell, formula_cell, ...
          y_fit_cell, y_pred_cell, y_ext_cell, ...
          model_name, color, p, y, y_fit, y_test, y_pred, y_ext, formula_str)

    R2 = 1 - sum((y - y_fit).^2) / sum((y - mean(y)).^2);
    RMSE = sqrt(mean((y - y_fit).^2));

    if isempty(y_test)
        Test_RMSE = NaN;
        AARE = NaN;
    else
        Test_RMSE = sqrt(mean((y_test - y_pred).^2));
        AARE = mean(abs((y_test - y_pred) ./ y_test)) * 100;
    end

    results(end+1,:) = [R2, RMSE, Test_RMSE, AARE];

    used_model_names{end+1,1} = model_name;
    used_colors(end+1,:) = color;

    params_cell{end+1,1} = p;
    formula_cell{end+1,1} = formula_str;

    y_fit_cell{end+1,1} = y_fit;
    y_pred_cell{end+1,1} = y_pred;
    y_ext_cell{end+1,1} = y_ext;
end

function [p_best, ok] = fit_two_stage_log_model(x_train, y_train, min_pts_each_side)
    % 模型：
    % ln(y)=A+n1*ln(x), x<x1
    % ln(y)=A+n1*ln(x)+n2*ln(x/x1), x>=x1

    x_train = x_train(:);
    y_train = y_train(:);

    log_y = log(y_train);
    log_x = log(x_train);

    n = length(x_train);

    % 分段点候选范围取训练集 25% 到 75% 分位数
    x1_candidates = linspace(quantile(x_train,0.25), quantile(x_train,0.75), 80);

    best_sse = Inf;
    p_best = [];
    ok = false;

    for i = 1:length(x1_candidates)
        x1 = x1_candidates(i);

        left_num = sum(x_train < x1);
        right_num = sum(x_train >= x1);

        if left_num < min_pts_each_side || right_num < min_pts_each_side
            continue;
        end

        H = double(x_train >= x1);

        % 设计矩阵：
        % ln(y)=A+n1*ln(x)+n2*H*ln(x/x1)
        Xmat = [ones(size(x_train)), log_x, H .* log(x_train ./ x1)];

        beta = Xmat \ log_y;

        log_y_fit = Xmat * beta;
        sse = sum((log_y - log_y_fit).^2);

        if sse < best_sse
            best_sse = sse;
            p_best = [beta(1), beta(2), beta(3), x1];
            ok = true;
        end
    end
end

function y = two_stage_log_predict(p, x)
    A  = p(1);
    n1 = p(2);
    n2 = p(3);
    x1 = p(4);

    x = x(:);

    log_y = A + n1 .* log(x);

    right_idx = x >= x1;
    log_y(right_idx) = log_y(right_idx) + n2 .* log(x(right_idx) ./ x1);

    y = exp(log_y);
end
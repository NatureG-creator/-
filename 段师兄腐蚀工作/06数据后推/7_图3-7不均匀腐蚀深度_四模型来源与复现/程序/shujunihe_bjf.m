%% ============================================================
%% 四种模型拟合对比 + 稳定两阶段对数模型
%% 中文输出 + 无网格线 + 论文级科研绘图风格
%% 两张图尺寸一致，便于插入 Word
%% 自动输出：模型表达式 + 参数 + 评价指标表格
%% ============================================================

clc;

%% ========== 1. 数据输入 ==========
% x：质量损失率
% y：不均匀腐蚀深度
x = bjf2(:,1);
y = bjf2(:,2);

% 删除无效数据；对数模型要求 x > 0 且 y > 0
valid = isfinite(x) & isfinite(y) & x > 0 & y > 0;
x = x(valid);
y = y(valid);

% 按质量损失率从小到大排序
% 这样后 20% 数据可作为伪外推测试集
[x, idx] = sort(x);
y = y(idx);

n = length(x);

if n < 2
    error('数据点数量过少，不建议进行四模型对比和两阶段拟合。');
end

%% ========== 2. 基本参数设置 ==========
x_extrap = 25;       % 外推上限，可按需要修改
train_ratio = 0.9;   % 前 80% 作为训练集，后 20% 作为测试集

n_train = round(n * train_ratio);

% 保证测试集至少有 2 个点
n_train = min(n_train, n-1);

x_train = x(1:n_train);
y_train = y(1:n_train);

x_test  = x(n_train+1:end);
y_test  = y(n_train+1:end);

x_fit = linspace(min(x), x_extrap, 400)';

%% ========== 3. 图像统一尺寸设置 ==========
% 两张图使用完全相同的宽度和高度
fig_w = 13;      % 图宽，单位 cm
fig_h = 8.5;     % 图高，单位 cm

% 坐标轴位置也保持一致，插入 Word 后更容易对齐
ax_pos = [0.16 0.17 0.78 0.72];

%% ========== 4. 模型名称与绘图颜色 ==========
model_names = {
    '线性模型', ...
    '幂函数模型', ...
    '指数饱和模型', ...
    '两阶段对数模型'
};

% 色盲友好配色，适合论文图
colors = [
    0.000, 0.447, 0.741;   % 蓝色
    0.850, 0.325, 0.098;   % 橙红色
    0.466, 0.674, 0.188;   % 绿色
    0.494, 0.184, 0.556;   % 紫色
];

results = zeros(4,4);       % R2, RMSE, 测试集RMSE, AARE
params_cell = cell(4,1);    % 保存模型参数
y_ext_cell = cell(4,1);     % 保存外推曲线
y_fit_cell = cell(4,1);     % 保存全数据拟合值
y_pred_cell = cell(4,1);    % 保存测试集预测值

opts = optimoptions('lsqcurvefit', ...
    'Display','off', ...
    'MaxFunctionEvaluations', 5000, ...
    'MaxIterations', 2000);

%% ============================================================
%% 5. 线性模型：d = a*x + b
%% ============================================================
linear_fun = @(p,x) p(1)*x + p(2);

x0 = [0.1, min(y_train)];
lb = [-Inf, -Inf];
ub = [ Inf,  Inf];

p = lsqcurvefit(linear_fun, x0, x_train, y_train, lb, ub, opts);

y_fit  = linear_fun(p, x);
y_pred = linear_fun(p, x_test);
y_ext  = linear_fun(p, x_fit);

params_cell{1} = p;
y_fit_cell{1} = y_fit;
y_pred_cell{1} = y_pred;
y_ext_cell{1} = y_ext;

%% ============================================================
%% 6. 幂函数模型：d = a*x^b + c
%% ============================================================
power_fun = @(p,x) p(1)*x.^p(2) + p(3);

x0 = [max(y_train)-min(y_train), 0.5, min(y_train)];
lb = [0, 0, 0];
ub = [Inf, 5, Inf];

p = lsqcurvefit(power_fun, x0, x_train, y_train, lb, ub, opts);

y_fit  = power_fun(p, x);
y_pred = power_fun(p, x_test);
y_ext  = power_fun(p, x_fit);

params_cell{2} = p;
y_fit_cell{2} = y_fit;
y_pred_cell{2} = y_pred;
y_ext_cell{2} = y_ext;

%% ============================================================
%% 7. 指数饱和模型：d = a*(1-exp(-k*x)) + b
%% ============================================================
exp_fun = @(p,x) p(1)*(1-exp(-p(2)*x)) + p(3);

x0 = [max(y_train)-min(y_train), 0.1, min(y_train)];
lb = [0, 0, 0];
ub = [Inf, Inf, Inf];

p = lsqcurvefit(exp_fun, x0, x_train, y_train, lb, ub, opts);

y_fit  = exp_fun(p, x);
y_pred = exp_fun(p, x_test);
y_ext  = exp_fun(p, x_fit);

params_cell{3} = p;
y_fit_cell{3} = y_fit;
y_pred_cell{3} = y_pred;
y_ext_cell{3} = y_ext;

%% ============================================================
%% 8. 两阶段对数模型
%% log(d)=A+n1*log(x), x<x1
%% log(d)=A+n1*log(x)+n2*log(x/x1), x>=x1
%% ============================================================

logy_train = log(y_train);

% 分段点候选范围：训练集 25% 到 75% 分位数
% 这样可以避免分段点跑到最左端或最右端
x1_candidates = linspace(quantile(x_train,0.25), quantile(x_train,0.75), 80);

best_sse = Inf;
best_beta = [];
best_x1 = NaN;

% 分段点两侧至少需要的数据点数量
min_pts_each_side = 3;

for ii = 1:length(x1_candidates)
    x1 = x1_candidates(ii);

    left_num = sum(x_train < x1);
    right_num = sum(x_train >= x1);

    if left_num < min_pts_each_side || right_num < min_pts_each_side
        continue;
    end

    H = double(x_train >= x1);

    % 设计矩阵：
    % log(d)=A+n1*log(x)+n2*H*log(x/x1)
    Xmat = [ones(size(x_train)), log(x_train), H.*log(x_train./x1)];

    beta = Xmat \ logy_train;

    logy_pred_train = Xmat * beta;
    sse = sum((logy_train - logy_pred_train).^2);

    if sse < best_sse
        best_sse = sse;
        best_beta = beta;
        best_x1 = x1;
    end
end

if isempty(best_beta)
    warning('两阶段对数模型未找到合理分段点，请检查数据点数量或候选范围。');
    best_beta = [0; 1; 0];
    best_x1 = median(x_train);
end

% 参数含义：p = [A, n1, n2, x1]
p = [best_beta(:); best_x1];

two_stage_log_fun = @(p,x) ...
    p(1) + p(2)*log(x) + double(x>=p(4)).*p(3).*log(x./p(4));

y_fit  = exp(two_stage_log_fun(p, x));
y_pred = exp(two_stage_log_fun(p, x_test));
y_ext  = exp(two_stage_log_fun(p, x_fit));

params_cell{4} = p;
y_fit_cell{4} = y_fit;
y_pred_cell{4} = y_pred;
y_ext_cell{4} = y_ext;

%% ============================================================
%% 9. 评价指标计算
%% ============================================================
for m = 1:4
    y_fit = y_fit_cell{m};
    y_pred = y_pred_cell{m};

    R2 = 1 - sum((y - y_fit).^2) / sum((y - mean(y)).^2);
    RMSE = sqrt(mean((y - y_fit).^2));
    Test_RMSE = sqrt(mean((y_test - y_pred).^2));
    AARE = mean(abs((y_test - y_pred)./y_test)) * 100;

    results(m,:) = [R2, RMSE, Test_RMSE, AARE];
end

%% ============================================================
%% 10. 主图：四种模型拟合与外推对比
%% ============================================================
fig1 = figure('Units','centimeters','Position',[4,4,fig_w,fig_h]);
hold on;
grid off;
box off;
set(gcf,'Color','w');

ax = gca;
set(ax, ...
    'FontName','Microsoft YaHei', ...
    'FontSize',8.5, ...
    'LineWidth',0.8, ...
    'TickDir','out', ...
    'TickLength',[0.018 0.018], ...
    'XMinorTick','off', ...
    'YMinorTick','off', ...
    'Layer','top', ...
    'Position',ax_pos);

% 绘制模型曲线
for m = 1:4
    plot(x_fit, y_ext_cell{m}, ...
        'Color', colors(m,:), ...
        'LineWidth',1.6);
end

% 原始数据点
plot(x, y, 'o', ...
    'MarkerSize',4.8, ...
    'MarkerEdgeColor','k', ...
    'MarkerFaceColor',[0.15 0.15 0.15], ...
    'LineWidth',0.6);

% 测试集数据点
plot(x_test, y_test, 's', ...
    'MarkerSize',5.2, ...
    'MarkerEdgeColor','k', ...
    'MarkerFaceColor',[1 1 1], ...
    'LineWidth',0.8);

xlabel('质量损失率 \eta / %', ...
    'FontName','Microsoft YaHei', ...
    'FontSize',9.5);

ylabel('不均匀腐蚀深度 t_{ave} / \mum', ...
    'FontName','Microsoft YaHei', ...
    'FontSize',9.5);
%ylabel('腐蚀坑深度对数均值 \mu_{Hq}', ...
    %'FontName','Microsoft YaHei', ...
    %'FontSize',9.5);


legend([model_names, {'原始数据','测试集'}], ...
    'Location','northwest', ...
    'Box','off', ...
    'FontName','Microsoft YaHei', ...
    'FontSize',7.5);

xlim([min(x)*0.95, x_extrap]);

y_all = [y; y_ext_cell{1}; y_ext_cell{2}; y_ext_cell{3}; y_ext_cell{4}];
ylim([min(y)*0.95, max(y_all)*1.05]);

% 导出图片
exportgraphics(fig1, '四种模型拟合与外推对比.pdf', 'ContentType','vector');
exportgraphics(fig1, '四种模型拟合与外推对比.tif', 'Resolution',600);
exportgraphics(fig1, '四种模型拟合与外推对比.png', 'Resolution',600);

%% ============================================================
%% 11. 残差图：四种模型残差对比
%% ============================================================
fig2 = figure('Units','centimeters','Position',[4,4,fig_w,fig_h]);
hold on;
grid off;
box off;
set(gcf,'Color','w');

ax = gca;
set(ax, ...
    'FontName','Microsoft YaHei', ...
    'FontSize',8.5, ...
    'LineWidth',0.8, ...
    'TickDir','out', ...
    'TickLength',[0.018 0.018], ...
    'XMinorTick','off', ...
    'YMinorTick','off', ...
    'Layer','top', ...
    'Position',ax_pos);

for m = 1:4
    residual = y - y_fit_cell{m};
    plot(x, residual, '-', ...
        'Color', colors(m,:), ...
        'LineWidth',1.3);
end

yline(0, '--k', 'LineWidth',0.8);

xlabel('质量损失率 \eta / %', ...
    'FontName','Microsoft YaHei', ...
    'FontSize',9.5);

ylabel('残差 / \mum', ...
    'FontName','Microsoft YaHei', ...
    'FontSize',9.5);
    %'FontName','Microsoft YaHei', ...
    %'FontSize',9.5);%ylabel('残差', ...


legend(model_names, ...
    'Location','best', ...
    'Box','off', ...
    'FontName','Microsoft YaHei', ...
    'FontSize',7.5);

% 导出图片
exportgraphics(fig2, '四种模型残差对比.pdf', 'ContentType','vector');
exportgraphics(fig2, '四种模型残差对比.tif', 'Resolution',600);
exportgraphics(fig2, '四种模型残差对比.png', 'Resolution',600);

%% ============================================================
%% 12. 命令行输出拟合公式与评价指标
%% ============================================================
fprintf('\n');
fprintf('=============================================================\n');
fprintf('                  四种模型拟合结果\n');
fprintf('=============================================================\n\n');

p = params_cell{1};
fprintf('【1. 线性模型】\n');
fprintf('   d = %.6f x + %.6f\n\n', p(1), p(2));

p = params_cell{2};
fprintf('【2. 幂函数模型】\n');
fprintf('   d = %.6f x^%.6f + %.6f\n\n', p(1), p(2), p(3));

p = params_cell{3};
fprintf('【3. 指数饱和模型】\n');
fprintf('   d = %.6f (1 - exp(-%.6f x)) + %.6f\n\n', p(1), p(2), p(3));

p = params_cell{4};
fprintf('【4. 两阶段对数模型】\n');
fprintf('   log(d) = %.6f + %.6f log(x)，当 x < %.6f\n', ...
    p(1), p(2), p(4));
fprintf('   log(d) = %.6f + %.6f log(x) + %.6f log(x/%.6f)，当 x >= %.6f\n\n', ...
    p(1), p(2), p(3), p(4), p(4));

fprintf('   前阶段对数斜率 n1 = %.6f\n', p(2));
fprintf('   后阶段对数斜率 n1+n2 = %.6f\n', p(2)+p(3));
fprintf('   分段点 x1 = %.6f\n\n', p(4));

fprintf('模型评价表：\n');
fprintf('--------------------------------------------------------------------------\n');
fprintf('模型名称\t\t\tR²\t\tRMSE\t\t测试集RMSE\t平均绝对相对误差(%%)\n');
fprintf('--------------------------------------------------------------------------\n');

for m = 1:4
    fprintf('%-18s\t%.4f\t%.4f\t%.4f\t\t%.2f\n', ...
        model_names{m}, results(m,1), results(m,2), results(m,3), results(m,4));
end

fprintf('--------------------------------------------------------------------------\n');

%% ============================================================
%% 13. 分段点合理性检查
%% ============================================================
p = params_cell{4};
x1 = p(4);

left_num_all = sum(x < x1);
right_num_all = sum(x >= x1);

fprintf('\n两阶段对数模型分段点检查：\n');
fprintf('分段点 x1 = %.6f\n', x1);
fprintf('分段点左侧数据点数量 = %d\n', left_num_all);
fprintf('分段点右侧数据点数量 = %d\n', right_num_all);

if left_num_all < 3 || right_num_all < 3
    fprintf('提示：分段点一侧数据点偏少，两阶段对数模型的稳定性可能不足。\n');
else
    fprintf('分段点两侧数据数量基本满足拟合要求。\n');
end

fprintf('=============================================================\n');

%% ============================================================
%% 14. 输出“模型表达式 + 参数 + 评价指标”论文表格
%% ============================================================

% 提取各模型参数
p1 = params_cell{1};   % 线性模型：[a, b]
p2 = params_cell{2};   % 幂函数模型：[a, b, c]
p3 = params_cell{3};   % 指数饱和模型：[a, k, b]
p4 = params_cell{4};   % 两阶段对数模型：[A, n1, n2, x1]

%% ========== 14.1 生成最终模型表达式字符串 ==========

formula_cell = cell(4,1);

% 1. 线性模型
formula_cell{1} = sprintf('d = %.4fη + %.4f', p1(1), p1(2));

% 2. 幂函数模型
formula_cell{2} = sprintf('d = %.4fη^{%.4f} + %.4f', p2(1), p2(2), p2(3));

% 3. 指数饱和模型
formula_cell{3} = sprintf('d = %.4f[1-exp(-%.4fη)] + %.4f', p3(1), p3(2), p3(3));

% 4. 两阶段对数模型
formula_cell{4} = sprintf(['ln(d)=%.4f+%.4fln(η), η<%.4f; ', ...
                           'ln(d)=%.4f+%.4fln(η)+%.4fln(η/%.4f), η≥%.4f'], ...
                           p4(1), p4(2), p4(4), ...
                           p4(1), p4(2), p4(3), p4(4), p4(4));

%% ========== 14.2 生成参数列 ==========

% 没有的参数用 “—” 表示，方便论文表格展示
param_a  = {'—'; '—'; '—'; '—'};
param_b  = {'—'; '—'; '—'; '—'};
param_c  = {'—'; '—'; '—'; '—'};
param_k  = {'—'; '—'; '—'; '—'};
param_A  = {'—'; '—'; '—'; '—'};
param_n1 = {'—'; '—'; '—'; '—'};
param_n2 = {'—'; '—'; '—'; '—'};
param_eta1 = {'—'; '—'; '—'; '—'};

% 线性模型 d = aη + b
param_a{1} = sprintf('%.4f', p1(1));
param_b{1} = sprintf('%.4f', p1(2));

% 幂函数模型 d = aη^b + c
param_a{2} = sprintf('%.4f', p2(1));
param_b{2} = sprintf('%.4f', p2(2));
param_c{2} = sprintf('%.4f', p2(3));

% 指数饱和模型 d = a[1-exp(-kη)] + b
param_a{3} = sprintf('%.4f', p3(1));
param_k{3} = sprintf('%.4f', p3(2));
param_b{3} = sprintf('%.4f', p3(3));

% 两阶段对数模型
param_A{4} = sprintf('%.4f', p4(1));
param_n1{4} = sprintf('%.4f', p4(2));
param_n2{4} = sprintf('%.4f', p4(3));
param_eta1{4} = sprintf('%.4f', p4(4));

%% ========== 14.3 评价指标格式化 ==========

R2_col        = cell(4,1);
RMSE_col      = cell(4,1);
Test_RMSE_col = cell(4,1);
AARE_col      = cell(4,1);

for m = 1:4
    R2_col{m}        = sprintf('%.4f', results(m,1));
    RMSE_col{m}      = sprintf('%.4f', results(m,2));
    Test_RMSE_col{m} = sprintf('%.4f', results(m,3));
    AARE_col{m}      = sprintf('%.2f', results(m,4));
end

%% ========== 14.4 生成 Excel 总表 ==========

header = {
    '模型名称', ...
    '最终拟合模型表达式', ...
    'a', ...
    'b', ...
    'c', ...
    'k', ...
    'A', ...
    'n1', ...
    'n2', ...
    'η1', ...
    'R²', ...
    'RMSE', ...
    '测试集RMSE', ...
    '平均绝对相对误差/%'
};

table_data = [
    model_names(:), ...
    formula_cell, ...
    param_a, ...
    param_b, ...
    param_c, ...
    param_k, ...
    param_A, ...
    param_n1, ...
    param_n2, ...
    param_eta1, ...
    R2_col, ...
    RMSE_col, ...
    Test_RMSE_col, ...
    AARE_col
];

output_cell = [header; table_data];

writecell(output_cell, '模型表达式_参数_评价指标表.xlsx', 'Sheet', '模型结果');

%% ========== 14.5 生成 Word 可直接打开的三线表 HTML：模型表达式 + 评价指标 ==========

html_file = '模型表达式_评价指标表_三线表.html';
fid = fopen(html_file, 'w', 'n', 'UTF-8');

fprintf(fid, '<!DOCTYPE html>\n');
fprintf(fid, '<html>\n<head>\n<meta charset="UTF-8">\n');

fprintf(fid, '<style>\n');
fprintf(fid, 'body { font-family: SimSun, 宋体, serif; font-size: 10.5pt; }\n');
fprintf(fid, 'table { border-collapse: collapse; margin: 0 auto; border-top: 1.5pt solid black; border-bottom: 1.5pt solid black; width: 100%%; }\n');
fprintf(fid, 'caption { caption-side: top; text-align: center; font-size: 10.5pt; margin-bottom: 6pt; }\n');
fprintf(fid, 'thead tr { border-bottom: 1.0pt solid black; }\n');
fprintf(fid, 'th, td { padding: 4pt 6pt; text-align: center; font-weight: normal; vertical-align: middle; }\n');
fprintf(fid, 'td.formula { text-align: left; }\n');
fprintf(fid, '</style>\n');

fprintf(fid, '</head>\n<body>\n');

fprintf(fid, '<table>\n');
fprintf(fid, '<caption>表 X 质量损失率与不均匀腐蚀深度关系的模型拟合结果</caption>\n');

fprintf(fid, '<thead>\n<tr>\n');
fprintf(fid, '<th>模型名称</th>\n');
fprintf(fid, '<th>最终拟合模型表达式</th>\n');
fprintf(fid, '<th>R<sup>2</sup></th>\n');
fprintf(fid, '<th>RMSE</th>\n');
fprintf(fid, '<th>测试集RMSE</th>\n');
fprintf(fid, '<th>平均绝对相对误差/%</th>\n');
fprintf(fid, '</tr>\n</thead>\n');

fprintf(fid, '<tbody>\n');

for m = 1:4
    fprintf(fid, '<tr>\n');
    fprintf(fid, '<td>%s</td>\n', model_names{m});
    fprintf(fid, '<td class="formula">%s</td>\n', formula_cell{m});
    fprintf(fid, '<td>%s</td>\n', R2_col{m});
    fprintf(fid, '<td>%s</td>\n', RMSE_col{m});
    fprintf(fid, '<td>%s</td>\n', Test_RMSE_col{m});
    fprintf(fid, '<td>%s</td>\n', AARE_col{m});
    fprintf(fid, '</tr>\n');
end

fprintf(fid, '</tbody>\n');
fprintf(fid, '</table>\n');

fprintf(fid, '</body>\n</html>\n');

fclose(fid);

%% ========== 14.6 生成 Word 可直接打开的三线表 HTML：模型参数明细 ==========

html_file2 = '模型参数明细表_三线表.html';
fid = fopen(html_file2, 'w', 'n', 'UTF-8');

fprintf(fid, '<!DOCTYPE html>\n');
fprintf(fid, '<html>\n<head>\n<meta charset="UTF-8">\n');

fprintf(fid, '<style>\n');
fprintf(fid, 'body { font-family: SimSun, 宋体, serif; font-size: 10.5pt; }\n');
fprintf(fid, 'table { border-collapse: collapse; margin: 0 auto; border-top: 1.5pt solid black; border-bottom: 1.5pt solid black; }\n');
fprintf(fid, 'caption { caption-side: top; text-align: center; font-size: 10.5pt; margin-bottom: 6pt; }\n');
fprintf(fid, 'thead tr { border-bottom: 1.0pt solid black; }\n');
fprintf(fid, 'th, td { padding: 4pt 10pt; text-align: center; font-weight: normal; }\n');
fprintf(fid, '</style>\n');

fprintf(fid, '</head>\n<body>\n');

fprintf(fid, '<table>\n');
fprintf(fid, '<caption>表 X 各拟合模型参数取值</caption>\n');

fprintf(fid, '<thead>\n<tr>\n');
fprintf(fid, '<th>模型名称</th>\n');
fprintf(fid, '<th>a</th>\n');
fprintf(fid, '<th>b</th>\n');
fprintf(fid, '<th>c</th>\n');
fprintf(fid, '<th>k</th>\n');
fprintf(fid, '<th>A</th>\n');
fprintf(fid, '<th>n<sub>1</sub></th>\n');
fprintf(fid, '<th>n<sub>2</sub></th>\n');
fprintf(fid, '<th>η<sub>1</sub></th>\n');
fprintf(fid, '</tr>\n</thead>\n');

fprintf(fid, '<tbody>\n');

for m = 1:4
    fprintf(fid, '<tr>\n');
    fprintf(fid, '<td>%s</td>\n', model_names{m});
    fprintf(fid, '<td>%s</td>\n', param_a{m});
    fprintf(fid, '<td>%s</td>\n', param_b{m});
    fprintf(fid, '<td>%s</td>\n', param_c{m});
    fprintf(fid, '<td>%s</td>\n', param_k{m});
    fprintf(fid, '<td>%s</td>\n', param_A{m});
    fprintf(fid, '<td>%s</td>\n', param_n1{m});
    fprintf(fid, '<td>%s</td>\n', param_n2{m});
    fprintf(fid, '<td>%s</td>\n', param_eta1{m});
    fprintf(fid, '</tr>\n');
end

fprintf(fid, '</tbody>\n');
fprintf(fid, '</table>\n');

fprintf(fid, '</body>\n</html>\n');

fclose(fid);

%% ========== 14.7 生成 CSV 备用表格 ==========

writecell(output_cell, '模型表达式_参数_评价指标表.csv');

%% ========== 14.8 输出提示 ==========

fprintf('\n已生成论文可用表格文件：\n');
fprintf('1. 模型表达式_参数_评价指标表.xlsx\n');
fprintf('2. 模型表达式_参数_评价指标表.csv\n');
fprintf('3. 模型表达式_评价指标表_三线表.html\n');
fprintf('4. 模型参数明细表_三线表.html\n');
fprintf('\n建议：Word 中优先打开 HTML 文件，复制三线表到论文正文。\n');
fprintf('如果公式列过长，建议正文使用“模型表达式_评价指标表”，参数单独使用“模型参数明细表”。\n');

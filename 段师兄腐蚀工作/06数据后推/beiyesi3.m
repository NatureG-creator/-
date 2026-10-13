%clear; clc; close all;
rng(0);

%% ====================== 1. 数据（你的格式：第1列=质量损失率，第2列=log深度） ======================
% 文献1 [质量损失率, log(深度/μm)]
lit1 =xiaosiy_sd2;
lit2 =gq_sd2;
% 你的数据
your = drfsd2;

x1 = lit1(:,1); y1 = lit1(:,2);
x2 = lit2(:,1); y2 = lit2(:,2);
x  = your(:,1);  y  = your(:,2);

%% ====================== 2. 两篇文献分别拟合 y = a*x^b → 得到 (a1,b1) (a2,b2) ======================
% 定义模型：y = a*x^b
ft = fittype('a*x^b','independent','x','coefficients',{'a','b'});

f1 = fit(x1,y1,ft);
f2 = fit(x2,y2,ft);

a1 = f1.a; b1 = f1.b;
a2 = f2.a; b2 = f2.b;

%% ====================== 3. 构建文献先验（对 a 和 b 分别算均值 + 标准差） ======================
% 计算 a 的先验
mu_a  = mean([a1,a2]);
sg_a  = std([a1,a2]) + 0.05;  % 加小量稳定

% 计算 b 的先验
mu_b  = mean([b1,b2]);
sg_b  = std([b1,b2]) + 0.02;

%% ====================== 4. 生成先验样本（大量 a 和 b 组合） ======================
N = 6000;

% 先验采样
a_samp = mu_a + sg_a * randn(N,1);
b_samp = mu_b + sg_b * randn(N,1);

% 简单过滤：参数必须为正
valid = (a_samp > 0) & (b_samp > 0);
a_samp = a_samp(valid);
b_samp = b_samp(valid);

%% ====================== 5. 贝叶斯更新：用你的数据来“修正” a 和 b ======================
% 核心：对每一组 (a,b)，计算它贴合你数据的程度（似然）
logL = zeros(size(a_samp));

for i = 1:length(a_samp)
    yhat = a_samp(i) .* (x .^ b_samp(i));   % 🔴 关键模型：y = a*x^b
    logL(i) = sum(normpdf(y, yhat, 0.05));   % 越小越符合
end

% 重采样得到后验（高权重的 a,b 被保留）
w = exp(logL - max(logL));
idx = randsample(1:length(a_samp), N, true, w);

a_post = a_samp(idx);
b_post = b_samp(idx);

%% ====================== 6. 画图：a 的先验 vs 后验 ======================

figure; hold on;
histogram(a_samp, 40, 'FaceAlpha',0.5);   % 蓝色：文献先验
histogram(a_post, 40, 'FaceAlpha',0.5);   % 红色：数据更新后验
title('参数 a 的分布（先验 vs 后验）');
legend('先验','后验'); grid on;

%% ====================== 7. 画图：b 的先验 vs 后验 ======================
figure; hold on;
histogram(b_samp, 40, 'FaceAlpha',0.5);
histogram(b_post, 40, 'FaceAlpha',0.5);
title('参数 b 的分布（先验 vs 后验）');
legend('先验','后验'); grid on;

%% ====================== 8. 自动外推直到 y = 目标值（比如 6.5）======================
target_y = 5.85;   % 你想推到的 y 值（自己改）

% 先粗略往外推，找到对应的 x
x_extend = linspace(min(x), max(x)*5, 500);  % 先推很远
temp_samples = zeros(N, length(x_extend));

for i = 1:N
    temp_samples(i,:) = a_post(i) .* (x_extend .^ b_post(i));
end

% 对每条曲线，找到第一次超过 target_y 的 x
x_stop = zeros(N, 1);
for i = 1:N
    idx = find(temp_samples(i,:) >= target_y, 1);
    if ~isempty(idx)
        x_stop(i) = x_extend(idx);
    else
        x_stop(i) = max(x_extend);
    end
end

% 取最终外推终点 x（均值位置，保证阴影完整）
x_end = mean(x_stop);
x_new = linspace(min(x), x_end, 100);  % 从数据起点 → 推到 y=6.5 对应的 x

% 重新计算到 x_end 的所有曲线
samples = zeros(N, length(x_new));
for i = 1:N
    samples(i,:) = a_post(i) .* (x_new .^ b_post(i));
end

% 95% 区间
m = mean(samples,1);
low = prctile(samples, 2.5, 1);
high = prctile(samples, 97.5, 1);

% 绘图
figure; hold on;
scatter(x,y,80,'k','filled');
plot(x_new, m,'b-','LineWidth',2);
fill([x_new,fliplr(x_new)],[low,fliplr(high)],'b','FaceAlpha',0.2);
yline(target_y, 'r--', 'LineWidth',1.5);  % 画出目标线 y=6.5

xlabel('质量损失率');
ylabel('log(深度/μm)');
title('贝叶斯外推：自动推到 y = 6.5 停止');
legend('数据','均值','95%区间','目标y=6.5','Location','best');
grid on;
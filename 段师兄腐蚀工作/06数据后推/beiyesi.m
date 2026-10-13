%% ====================== 数据格式：第1列质量损失率，第2列指标 ======================
%clear; clc;

%% 1. 输入数据（你直接替换成你的真实数据）
% 文献 1
lit1 =xiaosiy_sd;
lit2 =gq_sd;
% 你的数据
your = drfsd1;

%% 拆分数据
x1 = lit1(:,1); y1 = lit1(:,2);
x2 = lit2(:,1); y2 = lit2(:,2);
x  = your(:,1); y  = your(:,2);

%% 2. 两篇文献拟合 → 生成先验（模型：y = a*x^b，y=log(H/μm)）
ft = fittype('a*x^b','independent','x','coefficients',{'a','b'});
opts = fitoptions('Method','NonlinearLeastSquares');

f1 = fit(x1,y1,ft,opts);
f2 = fit(x2,y2,ft,opts);

a1 = f1.a; b1 = f1.b;
a2 = f2.a; b2 = f2.b;

% 先验：文献均值与标准差
a_mu = mean([a1,a2]);
b_mu = mean([b1,b2]);
a_sd = std([a1,a2]) + 0.04;
b_sd = std([b1,b2]) + 0.02;

%% 3. 贝叶斯拟合（文献先验 + 规范约束：log(H/μm) ≤ log(350)≈5.85）
rng(0);
N = 6000;

% 先验采样
a_samp = a_mu + a_sd * randn(N,1);
b_samp = b_mu + b_sd * randn(N,1);

% 物理约束
valid = a_samp>0 & b_samp>0;
a_samp = a_samp(valid);
b_samp = b_samp(valid);

% 规范约束：log(H/μm) ≤ log(350) ≈ 5.85（T/CSCP 0006-2024）
limit_logH = log(350); % 自然对数，若用log10则改为log10(350)

logLik = zeros(size(a_samp));
for i = 1:length(a_samp)
    mu = a_samp(i)*x.^b_samp(i);
    % 惩罚：超过规范限值则概率急剧下降
    penalty = exp(-max(0, max(mu)-limit_logH).^2/(2*0.1^2));
    logLik(i) = sum(normpdf(y, mu, 0.05)) + log(penalty);
end

% 重采样
w = exp(logLik - max(logLik));
idx = randsample(1:length(a_samp), N, true, w);
a_post = a_samp(idx);
b_post = b_samp(idx);

%% 4. 外推与95%上下界
x_new = linspace(min(x), max(x)*1.3, 100);
logH_samples = zeros(N, length(x_new));

for i = 1:N
    logH_samples(i,:) = a_post(i)*x_new.^b_post(i);
end

logH_mean = mean(logH_samples,1);
logH_low  = prctile(logH_samples, 2.5, 1);
logH_high = prctile(logH_samples, 97.5, 1);

% 规范裁剪
logH_high(logH_high>limit_logH) = limit_logH;

%% 5. 画图（和你现在的图格式完全一致）
figure('Position',[100,100,900,500])
scatter(x,y,100,'k','filled'); hold on;
plot(x_new, logH_mean, 'b-', 'linewidth',2);
fill([x_new,fliplr(x_new)], [logH_low,fliplr(logH_high)], 'b', 'FaceAlpha',0.2);
yline(limit_logH,'r--','LineWidth',1.5); % 规范限值：log(350)
xlabel('质量损失率');
ylabel('log(腐蚀深度/μm)');
legend('Your data','Mean','95% interval','T/CSCP limit','location','best');
grid on;
title('贝叶斯拟合：2篇文献先验 + 规范约束（对数深度）','fontsize',16);
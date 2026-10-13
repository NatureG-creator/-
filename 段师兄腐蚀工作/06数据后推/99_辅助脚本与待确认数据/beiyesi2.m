
%% ====================== 步骤0：输入数据（你的格式） ======================
lit1 = xiaosiy_sd2;
lit2 = gq_sd2;
your = drfsd2;

x1 = lit1(:,1); y1 = lit1(:,2);
x2 = lit2(:,1); y2 = lit2(:,2);
x  = your(:,1);  y  = your(:,2);

%% ====================== 步骤1：两篇文献分别拟合 → 得到参数 ======================
ft = fittype('a*x^b','independent','x','coefficients',{'a','b'});
f1 = fit(x1,y1,ft);
f2 = fit(x2,y2,ft);

a1 = f1.a; b1 = f1.b;
a2 = f2.a; b2 = f2.b;

% ====================== 【关键修改】所有数据 + 拟合曲线同图对比 ======================
figure('Position',[100,100,800,600]); hold on; grid on;
set(gca,'FontSize',12,'FontName','Microsoft YaHei');

% 文献1
scatter(x1,y1,60,'b','filled','MarkerEdgeColor','k');
plot(x1, f1.a*x1.^f1.b,'b-','LineWidth',2.5);

% 文献2
scatter(x2,y2,60,'r','filled','MarkerEdgeColor','k');
plot(x2, f2.a*x2.^f2.b,'r-','LineWidth',2.5);

% 你的数据（高亮显示）
scatter(x,y,80,'g','filled','MarkerEdgeColor','k','LineWidth',1);

% 拟合自己的数据（可选，更清晰）
f_you = fit(x,y,ft);
plot(x, f_you.a*x.^f_you.b,'g-','LineWidth',2.5);

xlabel('质量损失率','FontSize',13);
ylabel('log(深度/μm)','FontSize',13);
legend('文献1数据','文献1拟合','文献2数据','文献2拟合','你的实测数据','你的数据拟合','Location','best');
title('文献数据 vs 你的数据 → 对比图','FontSize',14);
grid on; box on;

%% ====================== 步骤2：计算先验均值、标准差 → 先验分布 ======================
mu_a = mean([a1,a2]);
sg_a = std([a1,a2]) + 0.02;

mu_b = mean([b1,b2]);
sg_b = std([b1,b2]) + 0.01;

figure;
subplot(1,2,1)
x_a = linspace(mu_a-3*sg_a, mu_a+3*sg_a,100);
plot(x_a, normpdf(x_a,mu_a,sg_a),'LineWidth',2);
title(sprintf('a的先验: N(%.3f, %.3f)',mu_a,sg_a)); grid on;

subplot(1,2,2)
x_b = linspace(mu_b-3*sg_b, mu_b+3*sg_b,100);
plot(x_b, normpdf(x_b,mu_b,sg_b),'LineWidth',2);
title(sprintf('b的先验: N(%.3f, %.3f)',mu_b,sg_b)); grid on;
sgtitle('步骤2：由文献参数构建先验分布');

%% ====================== 步骤3：先验采样 → 贝叶斯更新 → 后验参数 ======================
N = 5000;
a_smp = mu_a + sg_a * randn(N,1);
b_smp = mu_b + sg_b * randn(N,1);

valid = a_smp>0 & b_smp>0;
a_smp = a_smp(valid);
b_smp = b_smp(valid);

logL = zeros(size(a_smp));
for i = 1:length(a_smp)
    yhat = a_smp(i)*x.^b_smp(i);
    logL(i) = sum(normpdf(y, yhat, 0.05));
end

w = exp(logL - max(logL));
idx = randsample(1:length(a_smp), N, true, w);
a_post = a_smp(idx);
b_post = b_smp(idx);

figure; hold on;
histogram(a_smp,30,'FaceAlpha',0.5);
histogram(a_post,30,'FaceAlpha',0.5);
title('参数 a 先验分布 vs 后验分布');
legend('先验','后验'); grid on;

%% ====================== 步骤4：概率化外推 → 生成95%区间 ======================
x_new = linspace(min(x), max(x)*1.3, 100);
samples = zeros(N, length(x_new));

for i = 1:N
    samples(i,:) = a_post(i)*x_new.^b_post(i);
end

m = mean(samples,1);
low = prctile(samples, 2.5, 1);
high = prctile(samples, 97.5, 1);

% ====================== 最终图：自带数据 + 区间 ======================
figure('Position',[100,100,800,600]); hold on; grid on;
scatter(x,y,80,'k','filled');  % 你的数据
plot(x_new, m,'b-','LineWidth',2);
fill([x_new,fliplr(x_new)],[low,fliplr(high)],'b','FaceAlpha',0.2);
xlabel('质量损失率'); ylabel('log(深度/μm)');
title('贝叶斯概率外推 → 95% 预测区间','FontSize',12);
legend('你的数据','均值曲线','95%区间','Location','best');
grid on; box on;
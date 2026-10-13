function fenbujianyan(data)
% 导入数据
% 可视化数据分布
figure;
histogram(data, 'BinWidth', 0.1, 'Normalization', 'pdf', 'FaceColor', [0.5 0.8 1]);
hold on;
xlabel('数据值'); ylabel('概率密度');
title('数据直方图与拟合曲线');
% 计算正态分布参数（均值mu，标准差sigma）
[mu, sigma] = normfit(data);
% 或使用分布拟合对象
pd = fitdist(data, 'Normal');
mu = pd.mu;       % 均值
sigma = pd.sigma; % 标准差

disp(['均值 μ = ', num2str(mu)]);
disp(['标准差 σ = ', num2str(sigma)]);
% 生成理论正态分布曲线
x = linspace(min(data), max(data), 1000);
pdf_normal = normpdf(x, mu, sigma);

% 叠加绘制
plot(x, pdf_normal, 'r-', 'LineWidth', 2);
legend('数据分布', '拟合正态曲线');
figure;
qqplot(data);
title('Q-Q图检验正态性');
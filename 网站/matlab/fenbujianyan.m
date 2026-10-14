function fenbujianyan(data, cfg)
if nargin < 2 || isempty(cfg)
    cfg = step00_corrosion_config();
end
% 导入数据
% 可视化数据分布


% - `histogram` 绘制深度数据的直方图：
%   - `BinWidth', 0.1`：每个柱子的宽度为 0.1 深度单位，控制直方图的精细程度；
%   - `Normalization', 'pdf'`：把柱子归一化为**概率密度**，这样才能和后续正态分布的概率密度曲线放在同一坐标系对比；
%   - 颜色设为浅蓝色，视觉更清晰。
% - 作用：一眼就能看出深度数据集中在哪个区间、分布是否对称、有没有偏峰。
figure;
histogram(data, ...
    'BinWidth', cfg.distribution.hist_bin_width, ...
    'Normalization', cfg.distribution.hist_normalization, ...
    'FaceColor', cfg.distribution.hist_face_color);
hold on;
xlabel('数据值'); ylabel('概率密度');
title('数据直方图与拟合曲线');


% 计算正态分布参数（均值mu，标准差sigma）
% - 用两种方法拟合正态分布，结果一致，互为验证：
%   - `normfit` 直接返回正态分布的均值 `mu` 和标准差 `sigma`；
%   - `fitdist` 生成分布对象，再从中提取均值和标准差。
% - **物理意义（对应腐蚀场景）**：
%   - 均值 `mu`：就是整体的**平均腐蚀深度**，对应你之前形貌图里的 “平均线” 位置；
%   - 标准差 `sigma`：反映腐蚀深度的离散程度，数值越大，腐蚀越不均匀，锈坑深浅差异越大。
% - `disp` 在命令行窗口输出计算好的均值和标准差数值。
[mu, sigma] = normfit(data);
% 或使用分布拟合对象
pd = fitdist(data, cfg.distribution.fit_distribution);
mu = pd.mu;       % 均值
sigma = pd.sigma; % 标准差

disp(['均值 μ = ', num2str(mu)]);
disp(['标准差 σ = ', num2str(sigma)]);


% 生成理论正态分布曲线
% - 生成从数据最小值到最大值的 1000 个均匀采样点；
% - `normpdf` 计算对应理论正态分布的概率密度值；
% - 用红色粗线叠加在直方图上，直观对比实际数据和理想正态分布的吻合程度。
x = linspace(min(data), max(data), ...
    cfg.distribution.fit_curve_points);
pdf_normal = normpdf(x, mu, sigma);

% 叠加绘制
plot(x, pdf_normal, 'r-', ...
    'LineWidth', cfg.distribution.fit_line_width);
legend('数据分布', '拟合正态曲线');


% - 新建第二个窗口，绘制分位数 - 分位数图（Q-Q 图）。
% - **检验原理**：把实际数据的分位数，和理论正态分布的分位数一一对应描点。
%   - 如果所有点基本落在一条直线上，说明数据符合正态分布；
%   - 如果点偏离直线明显，说明不符合正态分布，偏离越远分布差异越大。
% - 作用：比直方图更严谨的正态性判断方法，用于定量验证分布类型。
figure;
qqplot(data);
title('Q-Q图检验正态性');

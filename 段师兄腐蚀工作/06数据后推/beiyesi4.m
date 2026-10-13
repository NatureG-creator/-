

%% ====================== 1. 数据加载 ======================
lit1 = xiaosiy_sd;
lit2 = gq_sd;
your = drfsd1;

x1 = lit1(:,1); y1 = lit1(:,2);
x2 = lit2(:,1); y2 = lit2(:,2);
x  = your(:,1);  y  = your(:,2);

%% ====================== 2. 文献拟合幂函数 y = a*x^b ======================
ft = fittype('a*x^b','independent','x','coefficients',{'a','b'});
f1 = fit(x1,y1,ft);
f2 = fit(x2,y2,ft);

a1 = f1.a; b1 = f1.b;
a2 = f2.a; b2 = f2.b;

%% ====================== 3. 构建文献先验 ======================
mu_a = mean([a1,a2]);
sg_a = std([a1,a2]) + 0.05;
mu_b = mean([b1,b2]);
sg_b = std([b1,b2]) + 0.02;

%% ====================== 4. 正态抽样生成先验参数 ======================
N = 6000;
a_samp = mu_a + sg_a * randn(N,1);
b_samp = mu_b + sg_b * randn(N,1);

valid = (a_samp > 0) & (b_samp > 0);
a_samp = a_samp(valid);
b_samp = b_samp(valid);

%% ====================== 5. 贝叶斯权重更新（贴合你的数据） ======================
logL = zeros(size(a_samp));
for i = 1:length(a_samp)
    yhat = a_samp(i) .* (x .^ b_samp(i));
    logL(i) = sum(normpdf(y, yhat, 0.05));
end

w = exp(logL - max(logL));
idx = randsample(1:length(a_samp), N, true, w);

a_post = a_samp(idx);
b_post = b_samp(idx);

%% ====================== 6. 参数分布绘图 ======================
figure; hold on;
histogram(a_samp, 40, 'FaceAlpha',0.5);
histogram(a_post, 40, 'FaceAlpha',0.5);
title('参数 a 分布'); legend('先验','后验'); grid on;

figure; hold on;
histogram(b_samp, 40, 'FaceAlpha',0.5);
histogram(b_post, 40, 'FaceAlpha',0.5);
title('参数 b 分布'); legend('先验','后验'); grid on;

%% ====================== 7. 外推计算 ======================
x_new = linspace(min(x), max(x)*1.5, 100);
samples = zeros(N, length(x_new));
for i = 1:N
    samples(i,:) = a_post(i) .* x_new .^ b_post(i);
end

m   = mean(samples, 1);
low = prctile(samples, 2.5, 1);
high= prctile(samples, 97.5, 1);

%% ====================== 8. 斜率一致性检验 ======================
y_lit1 = a1*x_new.^b1;
y_lit2 = a2*x_new.^b2;
y_lit  = (y_lit1 + y_lit2)/2;

k_your = zeros(N, length(x_new));
for i = 1:N
    ai = a_post(i);
    bi = b_post(i);
    k_your(i,:) = ai * bi * x_new.^(bi - 1);
end

k_lit1 = a1*b1 * x_new.^(b1-1);
k_lit2 = a2*b2 * x_new.^(b2-1);
k_lit  = (k_lit1 + k_lit2)/2;

x_end = max(x);
idx_ext = x_new > x_end;
x_ext_region = x_new(idx_ext);

k_mean_ext = mean(k_your(:, idx_ext), 1);
k_lit_ext  = k_lit(idx_ext);

slope_error = mean( abs( (k_mean_ext - k_lit_ext) ./ k_lit_ext ) ) * 100;

if slope_error < 15
    slope_level = '✅ 外推可信（趋势一致）';
elseif slope_error < 30
    slope_level = '⚠️ 基本可信（趋势接近）';
else
    slope_level = '❌ 不可信（趋势偏离）';
end

%% ====================== 9. 统计可信度指标 ======================
RIW = (high - low)./m *100;
idx_data_end = find(x_new >= max(x),1);
RIW_data = RIW(idx_data_end);
RIW_ext  = RIW(end);
IER = RIW_ext / RIW_data;
mean_RIW_ext = mean(RIW(idx_data_end:end));

if mean_RIW_ext <20 && IER<1.5
    stat_level = '✅ 高可信';
elseif mean_RIW_ext <40 && IER<2.5
    stat_level = '⚠️ 一般可信';
else
    stat_level = '❌ 不可信';
end

%% ====================== 10. 主绘图 ======================
figure('Position',[100,100,800,600]); hold on; grid on;
scatter(x,y,90,'k','filled','DisplayName','实测数据');
plot(x_new, m,'b-','LineWidth',2.5,'DisplayName','外推均值');
fill([x_new,fliplr(x_new)],[low,fliplr(high)],'b','FaceAlpha',0.15,'EdgeColor','none');
plot(x_new, y_lit,'m--','LineWidth',2,'DisplayName','文献大样本趋势');

xlabel('质量损失率','FontSize',12);
ylabel('log(深度/μm)','FontSize',12);

% ========== 修复标题，绝对不报错 ==========
title_str1 = sprintf('统计可信度：%s | 斜率可信度：%s', stat_level, slope_level);
title_str2 = sprintf('斜率相对误差：%.1f%%', slope_error);
title({title_str1, title_str2});

legend('Location','best');

%% ====================== 11. 斜率对比图 ======================
figure; hold on; grid on;
plot(x_ext_region, k_mean_ext,'b-o','LineWidth',2,'DisplayName','你的外推斜率');
plot(x_ext_region, k_lit_ext,'m--','LineWidth',2,'DisplayName','文献斜率');
xlabel('质量损失率'); ylabel('斜率 k(x)');
title(sprintf('斜率平均相对误差 = %.2f%%',slope_error));
legend;

%% ====================== 12. 输出报告 ======================
fprintf('\n========== 外推可信度综合报告 ==========\n');
fprintf('斜率相对误差 = %.2f%%\n',slope_error);
fprintf('斜率趋势判定 = %s\n',slope_level);
fprintf('统计区间判定 = %s\n',stat_level);
fprintf('========================================\n');
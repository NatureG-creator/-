%% ============================================================
% APDL 短柱材料本构曲线绘制
% TBPT,DEFI: 第一列为塑性应变，第二列为真实应力 MPa
% 总真实应变 = 塑性应变 + 真实应力 / 弹性模量
%% ============================================================

clc; clear; close all;

%% ========== 1. 材料参数 ==========
E = 207380;     % 弹性模量 MPa
nu = 0.3;       % 泊松比

%% ========== 2. APDL 中 TBPT 数据 ==========
% 第一列：塑性应变
% 第二列：真实应力 MPa

plastic_strain = [
    0.00000000
    0.00569773
    0.01895855
    0.03353260
    0.05738540
    0.08881010
    0.11814239
    0.15124848
    0.16843153
];

true_stress = [
    464.844
    473.958
    512.240
    539.583
    559.635
    577.865
    594.271
    612.500
    621.615
];

%% ========== 3. 换算总真实应变 ==========
elastic_strain = true_stress ./ E;
true_strain = plastic_strain + elastic_strain;

% 补充弹性段，从原点到屈服点
strain_elastic = [0; true_strain(1)];
stress_elastic = [0; true_stress(1)];

%% ========== 4. 输出数据表 ==========
T = table(plastic_strain, elastic_strain, true_strain, true_stress, ...
    'VariableNames', {'塑性应变','弹性应变','总真实应变','真实应力_MPa'});

disp(T);

%% ========== 5. 绘制真实应力-真实应变曲线 ==========
fig1 = figure('Color','w');
set(fig1,'Units','centimeters','Position',[5 5 14 9]);

hold on; box on; grid off;

% 弹性段
plot(strain_elastic, stress_elastic, 'k-', ...
    'LineWidth', 1.5);

% 塑性段
plot(true_strain, true_stress, 'r-o', ...
    'LineWidth', 1.8, ...
    'MarkerSize', 5, ...
    'MarkerFaceColor', 'r');

xlabel('真实应变 \epsilon_t', ...
    'FontName','Microsoft YaHei', ...
    'FontSize', 11);

ylabel('真实应力 \sigma_t / MPa', ...
    'FontName','Microsoft YaHei', ...
    'FontSize', 11);

legend({'弹性段','塑性强化段'}, ...
    'Location','southeast', ...
    'Box','off', ...
    'FontName','Microsoft YaHei', ...
    'FontSize', 10);

set(gca, ...
    'FontName','Times New Roman', ...
    'FontSize', 10, ...
    'LineWidth', 1.0, ...
    'TickDir','out');

xlim([0, max(true_strain)*1.08]);
ylim([0, max(true_stress)*1.10]);

%% ========== 6. 绘制 APDL 输入形式：真实应力-塑性应变 ==========
fig2 = figure('Color','w');
set(fig2,'Units','centimeters','Position',[5 5 14 9]);

hold on; box on; grid off;

plot(plastic_strain, true_stress, 'b-s', ...
    'LineWidth', 1.8, ...
    'MarkerSize', 5, ...
    'MarkerFaceColor', 'b');

xlabel('塑性应变 \epsilon_p', ...
    'FontName','Microsoft YaHei', ...
    'FontSize', 11);

ylabel('真实应力 \sigma_t / MPa', ...
    'FontName','Microsoft YaHei', ...
    'FontSize', 11);

legend({'APDL TBPT 输入本构'}, ...
    'Location','southeast', ...
    'Box','off', ...
    'FontName','Microsoft YaHei', ...
    'FontSize', 10);

set(gca, ...
    'FontName','Times New Roman', ...
    'FontSize', 10, ...
    'LineWidth', 1.0, ...
    'TickDir','out');

xlim([0, max(plastic_strain)*1.08]);
ylim([min(true_stress)*0.95, max(true_stress)*1.05]);

%% ========== 7. 导出高清图片 ==========
exportgraphics(fig1, '短柱真实应力-真实应变本构曲线.png', 'Resolution', 1200);
exportgraphics(fig1, '短柱真实应力-真实应变本构曲线.tif', 'Resolution', 1200);
exportgraphics(fig1, '短柱真实应力-真实应变本构曲线.pdf', 'ContentType','vector');

exportgraphics(fig2, '短柱APDL塑性应变-真实应力本构曲线.png', 'Resolution', 1200);
exportgraphics(fig2, '短柱APDL塑性应变-真实应力本构曲线.tif', 'Resolution', 1200);
exportgraphics(fig2, '短柱APDL塑性应变-真实应力本构曲线.pdf', 'ContentType','vector');

fprintf('\n已完成本构曲线绘制与图片导出。\n');
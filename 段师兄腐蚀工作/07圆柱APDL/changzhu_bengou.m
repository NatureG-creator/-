%% ============================================================
% APDL 长柱材料本构曲线绘制
% TBPT,DEFI: 第一列为塑性应变，第二列为真实应力 MPa
% 总真实应变 = 塑性应变 + 真实应力 / 弹性模量
%% ============================================================

clc; clear; close all;

%% ========== 1. 材料参数 ==========
E = 201000;     % 弹性模量 MPa
nu = 0.3;       % 泊松比

%% ========== 2. APDL 中 TBPT 数据 ==========
% 第一列：塑性应变
% 第二列：真实应力 MPa

plastic_strain = [
    0.00000000
    0.01114463
    0.02228926
    0.03343389
    0.04457852
    0.05572315
    0.06686778
    0.07801241
    0.08915704
    0.10030167
    0.11144630
    0.12259093
    0.13373556
    0.14488020
    0.15602483
];

true_stress = [
    343.000
    347.444
    369.030
    398.745
    428.103
    453.254
    471.535
    485.151
    496.842
    507.922
    518.895
    529.956
    541.188
    552.630
    564.304
];

%% ========== 3. 换算总真实应变 ==========
elastic_strain = true_stress ./ E;
true_strain = plastic_strain + elastic_strain;

% 补充弹性段：从原点到屈服点
strain_elastic = [0; true_strain(1)];
stress_elastic = [0; true_stress(1)];

%% ========== 4. 输出数据表 ==========
T = table(plastic_strain, elastic_strain, true_strain, true_stress, ...
    'VariableNames', {'PlasticStrain','ElasticStrain','TrueStrain','TrueStress_MPa'});

disp(T);

%% ========== 5. 图 1：真实应力-真实应变曲线 ==========
fig1 = figure('Color','w');
set(fig1,'Units','centimeters','Position',[5 5 14 9]);

hold on; box on; grid off;

% 弹性段
plot(strain_elastic, stress_elastic, 'k-', ...
    'LineWidth', 1.5);

% 塑性强化段
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

%% ========== 6. 图 2：APDL 输入形式，塑性应变-真实应力 ==========
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
exportgraphics(fig1, '长柱真实应力-真实应变本构曲线.png', 'Resolution', 1200);
exportgraphics(fig1, '长柱真实应力-真实应变本构曲线.tif', 'Resolution', 1200);
exportgraphics(fig1, '长柱真实应力-真实应变本构曲线.pdf', 'ContentType','vector');

exportgraphics(fig2, '长柱APDL塑性应变-真实应力本构曲线.png', 'Resolution', 1200);
exportgraphics(fig2, '长柱APDL塑性应变-真实应力本构曲线.tif', 'Resolution', 1200);
exportgraphics(fig2, '长柱APDL塑性应变-真实应力本构曲线.pdf', 'ContentType','vector');

fprintf('\n已完成长柱本构曲线绘制与图片导出。\n');
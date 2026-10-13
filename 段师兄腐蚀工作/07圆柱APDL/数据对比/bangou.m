%% 真实应力-真实应变 → 弹性模量 E + 塑性应变（直接用于ANSYS）

%% 1. 输入数据（你给的：第1列=真实应变，第2列=真实应力 MPa）
data=[
0.468775	641.493
0.409782	616.418
0.323107	574.627
0.236425	537.015
0.177439	507.761
0.118461	474.328
0.0655314	426.269
0.0414997	388.657
0.0235066	342.687
0.00313972	275.821
0.00191692	286.269
0.00110052	275.821
8.991189e-004	177.612
];
data = flipud(data);
% 输入弹性模量 E (MPa)
E = 197540;  

%% ========== 2. 提取并排序 ==========
true_strain = data(:,1);   % 真实总应变
true_stress = data(:,2);   % 真实应力

% 从小到大排序（必须！）
[true_strain, idx] = sort(true_strain);
true_stress = true_stress(idx);

%% ========== 3. 计算塑性应变 ==========
% 弹性应变 = 真实应力 / E
elastic_strain = true_stress / E;

% 塑性应变 = 总真实应变 - 弹性应变
plastic_strain = true_strain - elastic_strain;

% 塑性应变不能 < 0，小于0一律置0
plastic_strain(plastic_strain < 0) = 0;

%% ========== 4. 输出结果 ==========
fprintf('=====================================================\n');
fprintf('           真实塑性应变-真实应力曲线 \n');
fprintf('=====================================================\n');
fprintf('   塑性应变\t\t真实应力\n');

result = [plastic_strain, true_stress];
for i = 1:size(result,1)
    fprintf('%.8f\t%.3f\n', result(i,1), result(i,2));
end

%% ========== 5. 输出 ANSYS TBPT 命令 ==========
fprintf('\n=====================================================\n');
fprintf('            ANSYS 直接复制版（MISO）\n');
fprintf('=====================================================\n');
for i = 1:size(result,1)
    fprintf('TBPT,DEFI, %.8f, %.3f\n', result(i,1), result(i,2));
end

%% ========== 6. 绘图 ==========
figure('Position',[100,100,700,500])
plot(plastic_strain, true_stress, 'b-o','LineWidth',2,'MarkerSize',6);
xlabel('真实塑性应变','FontSize',12);
ylabel('真实应力 (MPa)','FontSize',12);
title('真实应力-塑性应变曲线（ANSYS 输入）','FontSize',14);
grid on;
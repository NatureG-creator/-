% ====================== 输入参数（需根据实际数据修改） ======================
% 示例数据（可替换为你的实际数据）
T_data = [5 10 15 20 30 40 60]; % 自变量 T
%y_data = [20 40 58 112 156 125 166]; % 模拟数据（不均匀腐蚀深度）
y_data = [38 60 84 140 236 165 266]; % 模拟数据（平均腐蚀深度）


% 初始猜测值（关键！需根据数据趋势估计，否则可能拟合失败）
A0 = 1;   % A 的初始猜测（如数据在 T=1 时 y≈A，可设为 y_data(1)）
N0 = 1;   % N 的初始猜测（如数据大致呈二次方增长，设为 2）

% ====================== 非线性拟合过程 ======================
% 定义拟合模型函数（y = A*T^N）
model = @(coeffs, T) coeffs(1) * T.^coeffs(2);  % coeffs = [A, N]

% 使用 nlinfit 拟合（无需额外工具箱）
[coeffs, residuals] = nlinfit(T_data', y_data', model, [A0, N0]);
A_fit = coeffs(1);  % 拟合得到的 A 参数
N_fit = coeffs(2);  % 拟合得到的 N 参数

% ====================== 手动计算决定系数 R² ======================
resnorm = sum(residuals.^2);         % 残差平方和（模型误差）
total_ss = sum((y_data - mean(y_data)).^2); % 总平方和（数据总波动）
R_square = 1 - resnorm / total_ss;    % 决定系数（越接近1，拟合越好）

% ====================== 结果输出与可视化 ======================
fprintf('拟合结果：A = %.4f，N = %.4f\n', A_fit, N_fit);
fprintf('决定系数 R² = %.4f（越接近1，拟合效果越好）\n', R_square); % 修正此处！

% 生成拟合曲线数据
T_plot = linspace(min(T_data), max(T_data), 100);
y_fit = A_fit * T_plot.^N_fit;

% 绘制原始数据与拟合曲线
figure;
scatter(T_data, y_data, 50, 'b', 'filled');
hold on;
plot(T_plot, y_fit, 'r', 'LineWidth', 2);
xlabel('T');
ylabel('y');
legend('原始数据', '拟合曲线');
title('幂函数模型 y = A·T^N 拟合结果');
grid on;
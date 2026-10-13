%% ====================== 长柱本构：工程颈缩 → 真实应力应变 → 塑性应变 → ANSYS ======================
clear; clc; close all;

%% 1. 材料参数
E   = 201e3;      % 弹性模量
fy  = 343;        % 屈服强度
fu  = 481;        % 极限强度
ey  = fy / E;     % 屈服应变

%% 2. Yun-Gardner 模型参数
esh = 0.1*fy/fu - 0.055;
esh = max(0.015, min(esh, 0.03));  % 硬化起点
eu  = 0.6*(1 - fy/fu);
eu  = max(eu, 0.06);               % 工程极限应变

%% 3. 生成工程应变 & 计算工程应力（公式9）
eps_eng = linspace(0, eu, 2000);
sigma_eng = zeros(size(eps_eng));

for i = 1:length(eps_eng)
    e = eps_eng(i);
    if e <= ey
        sigma_eng(i) = E * e;
    elseif e <= esh
        sigma_eng(i) = fy;
    else
        alpha = (e - esh)/(eu - esh);
        term = 0.4*alpha + 2*alpha/(1 + 400*alpha^5)^0.2;
        sigma_eng(i) = fy + (fu - fy)*term;
    end
end

%% ====================== 关键步骤：先在【工程应力】上找颈缩点（峰值） ======================
[sigma_eng_max, idx_neck_eng] = max(sigma_eng);  % 工程应力峰值 = 颈缩点

% 截断工程曲线：只保留颈缩前
eps_eng_neck = eps_eng(1:idx_neck_eng);
sigma_eng_neck = sigma_eng(1:idx_neck_eng);

%% ====================== 再换算：颈缩前工程 → 真实应力应变 ======================
sigma_true = sigma_eng_neck .* (1 + eps_eng_neck);   % 真实应力
eps_true   = log(1 + eps_eng_neck);                   % 真实应变

%% ====================== 真实总应变 → 塑性应变 ======================
eps_pl = eps_true - sigma_true / E;   % 塑性应变 = 总应变 - 弹性应变
eps_pl(eps_pl < 0) = 0;              % 屈服前塑性应变=0

% 去重（避免插值报错）
[eps_pl_unique, idx_unique] = unique(eps_pl);
sigma_unique = sigma_true(idx_unique);

%% ====================== 输出 15 个 ANSYS 点 ======================
nP = 15;
target_pl = linspace(0, max(eps_pl_unique), nP);
target_s  = interp1(eps_pl_unique, sigma_unique, target_pl, 'linear','extrap');
target_s(1) = fy;  % 第一个点：塑性应变0，应力=fy

%% ====================== 输出 ANSYS 命令流 ======================
fprintf('\n========== ANSYS 本构命令（直接复制） ==========\n');
fprintf('TB,PLASTIC,1,0,%d,MISO\n', nP);
fprintf('TBEO,NEGSLOPE,1\n');
for i = 1:nP
    fprintf('TBPT,DEFI,%.8f,%.3f\n', target_pl(i), target_s(i));
end
fprintf('=================================================\n');

%% ====================== 画图：三步都画出来 ======================
figure('Position',[100,100,1200,300])

% 1. 工程应力-应变 + 颈缩点
subplot(1,3,1)
plot(eps_eng, sigma_eng, 'b-','LineWidth',1.5); hold on;
plot(eps_eng_neck, sigma_eng_neck, 'r-','LineWidth',2.5);
xline(eps_eng(idx_neck_eng),'k--','颈缩点');
title('工程应力-应变（颈缩前截断）');
xlabel('工程应变'); ylabel('工程应力 (MPa)'); grid on;

% 2. 真实应力-应变
subplot(1,3,2)
plot(eps_true, sigma_true, 'r-','LineWidth',2.5);
title('真实应力-应变（颈缩前）');
xlabel('真实应变'); ylabel('真实应力 (MPa)'); grid on;

% 3. 真实应力 - 塑性应变（ANSYS 用）
subplot(1,3,3)
plot(target_pl, target_s, 'ms-','LineWidth',2,'MarkerSize',6);
title('真实应力 - 塑性应变（ANSYS 输入）');
xlabel('塑性应变'); ylabel('真实应力 (MPa)'); grid on;

sgtitle('长柱本构全流程：工程颈缩 → 真实 → 塑性','FontSize',14);
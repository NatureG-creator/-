% ===================== MATLAB 高程矩阵转【三个独立坐标文件】(0.3mm间距 固定) =====================
% 说明：修改后 分别导出 X.txt Y.txt Z.txt 三个纯单列数值文件，完美适配ANSYS三次*VREAD读取
% 新增：Z矩阵高程云图+三维曲面 双可视化功能，可直观查看高程分布
clc;close all;  % 增强清理，避免变量残留
Z = Z_filled;   % 替换：你的核心数据，m行n列，每个值是对应点的高程(mm)
[m, n] = size(Z);     % 获取行列数：m=Y方向点数，n=X方向点数

% 核心参数：固定写死，无需修改，严格匹配你的要求
dx = 0.3;             % X方向相邻点间距 = 0.3mm (固定值)
dy = 0.3;             % Y方向相邻点间距 = 0.3mm (固定值)
X_start = 0;          % X起始坐标，默认0，可改
Y_start = 0;          % Y起始坐标，默认0，可改

% 生成规则网格的X/Y坐标矩阵（0.3mm间距精准实现）
[X, Y] = meshgrid(X_start:dx:(X_start+dx*(n-1)), Y_start:dy:(Y_start+dy*(m-1)));

% 展平为一维列向量：X/Y/Z一一对应，列优先排序（APDL结构化网格的核心要求，顺序不变）
X_flat = reshape(X, [], 1);
Y_flat = reshape(Y, [], 1);
Z_flat = reshape(Z, [], 1);

% ===================== 核心修改：分别导出三个独立的TXT文件 =====================
save_path_root = 'E:\'; % 替换：你的保存根路径（只改这里即可，文件名自动生成）
% 导出【纯X坐标】文件 - 单列数值
dlmwrite([save_path_root,'DIANYUN_X.txt'], X_flat, 'delimiter', ' ', 'precision', 6, 'newline', 'pc');
% 导出【纯Y坐标】文件 - 单列数值
dlmwrite([save_path_root,'DIANYUN_Y.txt'], Y_flat, 'delimiter', ' ', 'precision', 6, 'newline', 'pc');
% 导出【纯Z坐标】文件 - 单列数值
dlmwrite([save_path_root,'DIANYUN_Z.txt'], Z_flat, 'delimiter', ' ', 'precision', 6, 'newline', 'pc');

% ===================== 新增核心功能：Z矩阵高程数据 双图可视化 (必看！) =====================
figure('Color','w','Position',[100,100,1200,500]); % 创建白底画布，固定大小，排版美观

%% ========== 子图1：高程云图 (俯视图，最常用！直观查看Z的平面高程分布+高低色差) ==========
subplot(1,2,1);
pcolor(X,Y,Z);   % 伪彩色云图，X/Y为坐标，Z为高程值映射颜色
shading interp;  % 插值平滑渲染，消除网格线，画质高清
colormap jet;    % 配色方案：蓝=低高程，红=高高程，ANSYS同款配色，行业通用
colorbar;        % 右侧显示颜色刻度条，对应Z的高程数值(mm)
set(gca,'FontSize',10); % 字体大小
xlabel('X 坐标 (mm)','FontSize',12);
ylabel('Y 坐标 (mm)','FontSize',12);
title('高程矩阵Z 云图分布 (俯视图)','FontSize',12,'FontWeight','bold');
axis equal tight; % 等比例显示，贴合实际坐标比例

%% ========== 子图2：三维曲面图 (立体图，查看Z的三维形貌+高低起伏趋势) ==========
subplot(1,2,2);
surf(X,Y,Z);     % 三维曲面，X/Y为底平面，Z为竖直高度
shading interp;  % 插值平滑渲染，曲面无棱角
colormap jet;    % 同云图配色，颜色与高程值一一对应
colorbar;        % 右侧显示颜色刻度条
set(gca,'FontSize',10);
xlabel('X 坐标 (mm)','FontSize',12);
ylabel('Y 坐标 (mm)','FontSize',12);
zlabel('Z 高程 (mm)','FontSize',12);
title('高程矩阵Z 三维曲面形貌','FontSize',12,'FontWeight','bold');
axis equal tight;
view(135,30);    % 经典三维视角，兼顾X/Y/Z三轴查看，可手动旋转调整
grid on; box on; % 显示网格+边框，增强立体感

% ===================== 原运行提示信息 =====================
fprintf('三个坐标文件导出完成！保存路径：%s\n', save_path_root);
fprintf('文件名分别为：DIANYUN_X1.txt  DIANYUN_Y1.txt  DIANYUN_Z1.txt\n');
fprintf('上表面节点总数：%d (m=%d行 × n=%d列)\n', m*n, m, n);
fprintf('X范围：%.3f ~ %.3f mm，Y范围：%.3f ~ %.3f mm\n', min(X_flat), max(X_flat), min(Y_flat), max(Y_flat));
fprintf('Z高程范围：%.3f ~ %.3f mm\n', min(Z_flat), max(Z_flat)); % 新增Z范围提示，超实用
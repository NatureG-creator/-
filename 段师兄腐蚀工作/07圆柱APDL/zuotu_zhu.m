%% ==============================
%% 空心圆柱 - 腐蚀矩阵中心插入 + 圆周首尾平滑 + 圆柱面映射显示
%% 顺序：径向 → 圆周 → 轴向
%% ==============================

clc; close all;

%% ========= 1. 输入参数 =========
% % ===== 短柱尺寸 =====
% R_O = 80;        % 外半径 mm
% R_I = 76;        % 内半径 mm
% nx  = 503;       % 圆周方向点数
% ny  = 480;       % 轴向方向点数
% n_radial = 3;    % 径向层数
% L_total = 480;   % 长度 mm

% ===== 如果是长柱，取消下面这段注释 =====
R_O = 90;        % 外半径 mm，D=180
R_I = 86;        % 内半径 mm，T=4
nx  = 565;       % 圆周方向点数，可近似取 2*pi*R_O / 1mm
ny  = 1000;      % 轴向方向点数
n_radial = 3;
L_total = 1000;

%% ========= 2. 外壁腐蚀矩阵中心插入 =========
% baseline 为你前面生成的腐蚀深度矩阵
% 注意：baseline 的单位应与 R_O 一致，建议为 mm
% 如果你的 baseline 单位是 μm，则取消下面这句注释：
% baseline = baseline / 1000;

Z_correct = zeros(ny, nx);

[rows_small, cols_small] = size(baseline);
rows_large = ny;
cols_large = nx;

if rows_small > rows_large || cols_small > cols_large
    error('baseline 尺寸大于目标圆柱面展开矩阵尺寸，请检查 nx、ny 或 baseline 尺寸。');
end

row_start = floor((rows_large - rows_small) / 2) + 1;
col_start = floor((cols_large - cols_small) / 2) + 1;

row_end = row_start + rows_small - 1;
col_end = col_start + cols_small - 1;

Z_correct(row_start:row_end, col_start:col_end) = baseline;

%% ========= 3. 圆周方向首尾平滑过渡 =========
% 只处理圆周方向，避免圆柱闭合位置突变
smooth_win = 5;

for k = 1:ny
    row = Z_correct(k, :);

    pad_row = [row(end-smooth_win+1:end), row, row(1:smooth_win)];
    smooth_row = movmean(pad_row, smooth_win);

    Z_correct(k, :) = smooth_row(smooth_win+1:end-smooth_win);
end

% 保证圆周首尾严格闭合
Z_correct(:, nx) = Z_correct(:, 1);

%% ========= 4. 极坐标网格输出 =========
theta_list = linspace(0, 2*pi, nx);
Z_list     = linspace(0, L_total, ny);

total_node = n_radial * nx * ny;

R_in     = zeros(total_node, 1);
R_out    = zeros(total_node, 1);
TH_all   = zeros(total_node, 1);
Z_all    = zeros(total_node, 1);

node_idx = 0;

for axial = 1:ny
    for circ = 1:nx
        for rad = 1:n_radial

            node_idx = node_idx + 1;

            R_in(node_idx)  = R_I;
            R_out(node_idx) = R_O - Z_correct(axial, circ);

            TH_all(node_idx) = theta_list(circ);
            Z_all(node_idx)  = Z_list(axial);

        end
    end
end

%% ========= 5. 输出 APDL / 后处理所需数据 =========
fid = fopen('DIANYUN_INNER_R.txt','w');
fprintf(fid,'%12.6f\n', R_in);
fclose(fid);

fid = fopen('DIANYUN_OUTER_R.txt','w');
fprintf(fid,'%12.6f\n', R_out);
fclose(fid);

fid = fopen('DIANYUN_THETA.txt','w');
fprintf(fid,'%12.6f\n', TH_all*180/pi);
fclose(fid);

fid = fopen('DIANYUN_Z.txt','w');
fprintf(fid,'%12.6f\n', Z_all);
fclose(fid);

fprintf('矩阵中心插入 + 圆周首尾平滑 + 极坐标数据输出完成。\n');

%% ========= 6. 可视化：圆柱面映射效果 =========
% 生成圆柱坐标
[TH_grid, Z_grid] = meshgrid(theta_list, Z_list);

R_surface = R_O - Z_correct;

X_cyl = R_surface .* cos(TH_grid);
Y_cyl = R_surface .* sin(TH_grid);
Z_cyl = Z_grid;

% 圆柱面展开坐标
S_list = R_O * theta_list;   % 圆周展开长度，单位 mm
[S_grid, Z_expand] = meshgrid(S_list, Z_list);

%% ========= 7. 绘制论文风格映射图 =========
fig = figure('Color','w');
set(fig,'Units','centimeters','Position',[3 3 24 10]);
set(fig,'Renderer','opengl');
set(fig,'GraphicsSmoothing','on');

tiledlayout(1,2,'TileSpacing','compact','Padding','compact');

%% ---- 左图：三维圆柱面腐蚀形貌 ----
ax1 = nexttile;
hold(ax1,'on');

surf(ax1, X_cyl, Y_cyl, Z_cyl, Z_correct, ...
    'EdgeColor','none', ...
    'FaceColor','interp');

shading interp;
colormap(ax1, jet);
cb1 = colorbar(ax1);
cb1.Label.String = '腐蚀深度 / mm';
cb1.Label.FontName = 'Microsoft YaHei';

axis equal;
axis tight;
grid off;
box on;

xlabel('X / mm','FontName','Times New Roman');
ylabel('Y / mm','FontName','Times New Roman');
zlabel('Z / mm','FontName','Times New Roman');

title('(a) 圆柱面腐蚀形貌映射结果', ...
    'FontName','Microsoft YaHei', ...
    'FontSize',10, ...
    'FontWeight','normal');

view(45,25);
camlight headlight;
lighting gouraud;
material dull;

set(ax1, ...
    'FontName','Times New Roman', ...
    'FontSize',9, ...
    'LineWidth',0.8, ...
    'TickDir','out');

%% ---- 右图：圆柱面展开腐蚀深度云图 ----
ax2 = nexttile;
hold(ax2,'on');

imagesc(ax2, S_list, Z_list, Z_correct);
set(ax2,'YDir','normal');

colormap(ax2, jet);
cb2 = colorbar(ax2);
cb2.Label.String = '腐蚀深度 / mm';
cb2.Label.FontName = 'Microsoft YaHei';

% 标出 baseline 插入区域
s_start = S_list(col_start);
s_end   = S_list(col_end);
z_start = Z_list(row_start);
z_end   = Z_list(row_end);

rectangle(ax2, ...
    'Position',[s_start, z_start, s_end-s_start, z_end-z_start], ...
    'EdgeColor','r', ...
    'LineStyle','--', ...
    'LineWidth',1.2);

xlabel('圆周展开长度 / mm','FontName','Microsoft YaHei');
ylabel('轴向长度 / mm','FontName','Microsoft YaHei');

title('(b) 圆柱面展开腐蚀深度分布', ...
    'FontName','Microsoft YaHei', ...
    'FontSize',10, ...
    'FontWeight','normal');

axis tight;
box on;
grid off;

set(ax2, ...
    'FontName','Times New Roman', ...
    'FontSize',9, ...
    'LineWidth',0.8, ...
    'TickDir','out');

%% ========= 8. 导出高清图 =========
exportgraphics(fig, '圆柱面腐蚀映射结果.png', ...
    'Resolution', 1200, ...
    'BackgroundColor','white');

exportgraphics(fig, '圆柱面腐蚀映射结果.tif', ...
    'Resolution', 1200, ...
    'BackgroundColor','white');

exportgraphics(fig, '圆柱面腐蚀映射结果.pdf', ...
    'ContentType','image', ...
    'Resolution',1200, ...
    'BackgroundColor','white');

fprintf('圆柱面映射可视化图片已导出。\n');
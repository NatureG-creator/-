%% ==============================
%% 空心圆柱 - 首尾平滑过渡 + 矩阵精准中心插入
%% 顺序：径向 → 圆周 → 轴向
%% ==============================

%% ========= 1. 输入参数 =========
%长柱尺寸
R_O = 44.5;
R_I = 40.5;
nx  = 280;   % 圆周方向点数（对应矩阵列数）
ny  = 1000;  % 轴向点数（对应矩阵行数）
n_radial = 3;
L_total = 1000;

% --- 模拟生成你的 baseline 矩阵 (600x70) ---
% 注意：这里用 peaks 模拟，你实际运行时换成你自己的 baseline 变量即可

%% ========= 2. 外壁修正矩阵：精准中心插入 =========
Z_correct = zeros(ny, nx); % 初始化大矩阵 1000x280

% --- 获取尺寸 ---
[rows_small, cols_small] = size(baseline); % 600x70
rows_large = ny; % 1000
cols_large = nx; % 280

% --- 计算插入起始位置（让小矩阵在正中心）---
row_start = floor((rows_large - rows_small) / 2) + 1;
col_start = floor((cols_large - cols_small) / 2) + 1;

% --- 执行插入 ---
Z_correct(row_start : row_start + rows_small - 1, ...
          col_start : col_start + cols_small - 1) = baseline;

%% ==============================
%% ✅ 关键：首尾平滑过渡（圆周方向）
%% ==============================
for k = 1:ny
    % 提取这一行的圆周数据
    row = Z_correct(k, :);
    
    % 在最后面加 5 个点做循环平滑（让末尾 → 开头自然过渡）
    pad_row = [row(end-4:end), row, row(1:5)];
    
    % 平滑（关键！让交界不突变）
    smooth_row = movmean(pad_row, 5);
    
    % 截回原来长度
    Z_correct(k, :) = smooth_row(6:end-5);
end

% 最后让首尾完全一致（保证闭合）
Z_correct(:, nx) = Z_correct(:, 1);

%% ========= 3. 极坐标网格 =========
theta_list = linspace(0, 2*pi, nx);
Z_list     = linspace(0, L_total, ny);

total_node = n_radial * nx * ny;
R_in      = zeros(total_node, 1);
R_out     = zeros(total_node, 1);
TH_all    = zeros(total_node, 1);
Z_all     = zeros(total_node, 1);
node_idx  = 0;

%% ==============================
%% 顺序：径向 → 圆周 → 轴向
%% ==============================
for axial = 1:ny
    for circ = 1:nx
        for rad = 1:n_radial
            
            node_idx = node_idx + 1;
            
            R_in(node_idx) = R_I;
            R_out(node_idx) = R_O - Z_correct(axial, circ);
            
            TH_all(node_idx) = theta_list(circ);
            Z_all(node_idx) = Z_list(axial);
            
        end
    end
end

%% ========= 输出 =========
fid = fopen('DIANYUN_INNER_R.txt','w'); fprintf(fid,'%12.6f\n', R_in); fclose(fid);
fid = fopen('DIANYUN_OUTER_R.txt','w'); fprintf(fid,'%12.6f\n', R_out); fclose(fid);
fid = fopen('DIANYUN_THETA.txt','w'); fprintf(fid,'%12.6f\n', TH_all*180/pi); fclose(fid);
fid = fopen('DIANYUN_Z.txt','w'); fprintf(fid,'%12.6f\n', Z_all); fclose(fid);

fprintf('✅ 矩阵中心插入 + 首尾平滑完成！\n');

%% --- (可选) 可视化检查插入效果 ---
figure('Position',[100,100,800,400])
subplot(1,2,1); surf(Z_correct,'EdgeColor','none'); title('插入并平滑后的 Z_correct'); view(2); colorbar;
subplot(1,2,2); plot(Z_correct(500,:), 'b-', 'LineWidth', 1.5); title('中间某一行的圆周轮廓（首尾已平滑）'); xlabel('圆周点'); grid on;
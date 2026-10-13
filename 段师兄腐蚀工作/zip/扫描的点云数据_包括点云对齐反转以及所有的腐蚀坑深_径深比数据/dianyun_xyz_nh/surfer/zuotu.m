%% ===================== 1. 读取TXT点云数据 =====================
% 方法1：使用load函数（适用于纯数值、无表头的TXT）
data = load('N6-60d-f（50）_corrected.txt'); % 替换为你的TXT文件路径
xyz = data(:,1:3); % 提取XYZ坐标
values = xyz(:,3); % 提取数值列（若TXT无此列，可替换为xyz(:,3)使用Z值）

% 方法2：使用textscan函数（适用于含注释或复杂格式的TXT）
% fid = fopen('point_cloud_data.txt', 'r');
% data = textscan(fid, '%f %f %f %f', 'HeaderLines', 1); % 跳过1行表头
% fclose(fid);
% xyz = [data{1}, data{2}, data{3}];
% values = data{4};

%% ===================== 2. 数据预处理（可选） =====================
% 去噪（移除异常值）
values(isoutlier(values)) = NaN; % 标记异常值为NaN
xyz(isnan(values), :) = []; % 删除对应点云
values(isnan(values)) = [];

% 下采样（减少点数量，提升速度）
downsample_ratio = 0.5; % 保留50%的点
idx = randsample(length(values), round(length(values)*downsample_ratio));
xyz = xyz(idx, :);
values = values(idx);

%% ===================== 3. 插值生成规则网格 =====================
% 创建网格（可调整分辨率）
grid_resolution = 0.5; % 网格间距，越小越精细
[X,Y] = meshgrid(min(xyz(:,1)):grid_resolution:max(xyz(:,1)), ...
                min(xyz(:,2)):grid_resolution:max(xyz(:,2)));

% 插值Z坐标和数值
Z = griddata(xyz(:,1), xyz(:,2), xyz(:,3), X, Y, 'cubic'); % 三次插值
V = griddata(xyz(:,1), xyz(:,2), values, X, Y, 'cubic');

%% ===================== 4. 绘制色温图 =====================
figure('Color','w','Position',[100,100,800,600]);
ax = axes('Parent',gcf);

% 绘制曲面图，用V值控制颜色
surf(X,Y,Z,V,'EdgeColor','none','FaceColor','interp');
colormap(jet); % 使用蓝-红渐变配色（与图片一致）
colorbar; % 添加色标

% 设置视角（匹配图片的俯视角度）
view(2); % 2D俯视视角，若需3D可改为view(30,30)
axis equal tight; % 等比例坐标轴

%% ===================== 5. 添加数值标注与美化 =====================
% 标注极值点
[max_val, max_idx] = max(V(:));
[min_val, min_idx] = min(V(:));
max_pos = [X(max_idx), Y(max_idx), Z(max_idx)];
min_pos = [X(min_idx), Y(min_idx), Z(min_idx)];

text(max_pos(1), max_pos(2), max_pos(3), ...
    sprintf('%.2f', max_val), 'Color','k','FontSize',12,'FontWeight','bold');
text(min_pos(1), min_pos(2), min_pos(3), ...
    sprintf('%.2f', min_val), 'Color','k','FontSize',12,'FontWeight','bold');

% 添加标题和坐标轴标签
title('TXT点云数据色温图','FontSize',14,'FontWeight','bold');
xlabel('X坐标','FontSize',12);
ylabel('Y坐标','FontSize',12);
zlabel('Z坐标','FontSize',12);

% 保存图片
print(gcf,'color_temperature_map','-dpng','-r300'); % 300dpi高清PNG
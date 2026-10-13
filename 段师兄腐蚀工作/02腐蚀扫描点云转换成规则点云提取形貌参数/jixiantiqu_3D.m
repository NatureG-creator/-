function [shengdu,sjb,zhijin,max_locs, min_locs, boundaries,boundary_coords]=jixiantiqu_3D(surface_data,params,yuzhi,grid_resolution)
    % 是一套三维表面形貌极值检测与分水岭分割的 MATLAB 自定义函数，核心作用是对你前面网格化得到的高程矩阵做特征分析：
    % 自动识别表面的峰 / 谷极值点、用分水岭算法分割独立的凹坑 / 凸起区域，并计算深度、面积等特征参数，常用于腐蚀形貌、磨损表面、微结构形貌的定量分析。
    % 检测三维曲面极值点并可视化 
    % 输入量：surface_data - 二维矩阵表示的三维高度数据 ，就是前面 `shujuguiyi` 输出的 `Z` 或 `Z_filled`；
    % 输入量：params——极值检测参数包，控制检测灵敏度、间距、邻域大小，见untitled；
    % 输入量：yuzhi——分水岭分割阈值，控制边界识别的灵敏度，见untitled；
    % 输入量：网格分辨率：把像素格数转换成实际物理尺寸，见untitled；
    % 主函数 `jixiantiqu_3D`（主流程 + 可视化）和子函数 `find_local_extrema`（局部极值点检测核心算法）。
    % 输出参数： `shengdu`：**深度**，每个分割区域的最大深度 / 高度
    % 输出参数：`sjb`：**面积**，每个凹坑 / 凸起的投影面积或表面积
    % 输出参数： `zhijin`：**直径**，等效特征直径
    % 输出参数： `max_locs`：极大值点坐标（峰点），格式 `[行号, 列号]`
    % 输出参数： `min_locs`：极小值点坐标（谷点 / 坑底），格式 `[行号, 列号]`
    % 输出参数： `boundaries`：分水岭边界掩码矩阵（二值图，边界处为 1）
    % 输出参数： `boundary_coords`：边界点的坐标集合

    % 创建网格坐标（用于可视化），生成和高程矩阵一一对应的平面坐标矩阵，用于后续绘图和坐标计算。
    % 列方向 → X 轴，行方向 → Y 轴，和图像坐标系一致。
    [X, Y] = meshgrid(1:size(surface_data,2), 1:size(surface_data,1));
    
    % 寻找极值点 ，调用子函数，通过滑动邻域法检测所有局部极大、极小值点，带显著度过滤和间距抑制，输出像素坐标。
    [max_locs, min_locs] = find_local_extrema(surface_data,params);
    
    % 分水岭寻求边界，以极值点为标记，用分水岭算法把表面分割成一个个独立的区域（每个凹坑 / 凸起单独成区），输出区域边界。
    [boundaries,boundary_coords] = fenshuiling_boundry(surface_data, max_locs,yuzhi);
    
    %根据分割出的边界和极值点，结合网格分辨率，计算每个区域的“深度、面积、等效直径”等定量参数，把像素单位转换成实际物理尺寸。
    [shengdu,sjb,zhijin] = fushikengtiqu(surface_data,boundary_coords,max_locs,grid_resolution);

    % 可视化结果 ，新建指定大小的窗口，左右分两个子图对照查看。
    figure('Position', [100, 100, 1200, 500]);
    
    % 子图1：三维曲面 + 极值点 
    % - `sub2ind` 把极值点的「行列索引」转换成矩阵线性索引，取出对应的三维坐标，用红色大点标记极大值峰点；
    subplot(1,2,1);
    surf(X, Y, surface_data, 'EdgeColor', 'none');
    hold on;

    % 修正坐标映射（重点修改处）
    if ~isempty(max_locs)
        plot3(X(sub2ind(size(X), max_locs(:,1), max_locs(:,2))), ...
              Y(sub2ind(size(Y), max_locs(:,1), max_locs(:,2))), ...
              surface_data(sub2ind(size(surface_data), max_locs(:,1), max_locs(:,2))), ...
              'r.', 'MarkerSize', 20);
    end 
    
    % ==================== 新增：绘制极小值点（蓝色圆点）====================
% if ~isempty(min_locs)
%     plot3(X(sub2ind(size(X), min_locs(:,1), min_locs(:,2))), ...
%           Y(sub2ind(size(X), min_locs(:,1), min_locs(:,2))), ...
%           surface_data(sub2ind(size(surface_data), min_locs(:,1), min_locs(:,2))), ...
%           'b.', 'MarkerSize', 20);
% end

    title('三维曲面极值点检测');
    xlabel('X方向'); ylabel('Y方向'); zlabel('高度');
    legend('曲面', '极大值点', '极小值点');
    grid on;
    colormap jet;
    colorbar;
    view(-30, 45);
    
    % 子图2：二维等高线 + 分水岭边界 
    %- 填充等高线图，共 20 个等高层级，直观显示高低分布；- 用红色小点绘制分水岭边界线；- 用红色叉号标记极大值点；
    % - `axis equal` 保证 XY 方向比例一致，图形不变形。

    subplot(1,2,2);
    contourf(X, Y, surface_data, 20);
    hold on;
    % 绘制分水岭边界（方式修正）
    [boundary_y, boundary_x] = find(boundaries); % 获取边界坐标
    plot(boundary_x, boundary_y, 'r.', 'MarkerSize', 5); % 使用点状边界
   
    % 标记极大值点（红色）
    if ~isempty(max_locs)
        % 直接使用列索引作为x坐标，行索引作为y坐标
        plot(max_locs(:,2), max_locs(:,1), 'rx', 'MarkerSize', 10, 'LineWidth', 2); 
    end
    title('二维等高线极值点');
    xlabel('X方向'); ylabel('Y方向');
    legend('等高线', '极大值点');
    colorbar;
    axis equal;
end 
 

% ======================================================================% ======================================================================


    %find_local_extrema是极值检测的核心算法，采用*滑动邻域 + 显著度判断 + 非极大值抑制（NMS）*的方案，比直接求导法抗噪能力更强。
function [max_locs, min_locs] = find_local_extrema(data, params)
    % 改进的三维极值点检测函数
    % 参数解析
    % 用输入解析器接收参数，三个关键检测参数：
    % MinProminence（最小显著度）：中心点和邻域均值的最小差值，值越大检测越严格，误检越少。
    % MinDistance（最小间距）：两个极值点之间的最小像素距离，避免同一个峰 / 谷检出多个点。
    % Neighborhood（邻域窗口）：检测用的滑动窗口大小，窗口越大，越只识别大尺度的极值。

    p = inputParser;
    addParameter(p, 'MinProminence', 0.001, @isnumeric); % 最小显著度
    addParameter(p, 'MinDistance', 20, @isnumeric);     % 极值点最小间距
    addParameter(p, 'Neighborhood', [35 35], @(x) numel(x)==2); % 检测邻域
    parse(p, params{:});

    % 初始化存储
    max_locs = []; max_vals = [];
    min_locs = []; min_vals = [];

    % 获取邻域半径
    nh_radius = floor(p.Results.Neighborhood/2);
    edge_margin = 1; % 调整边界处理逻辑

    % 主检测循环：
    % 1. 逐个遍历每个像素点，以它为中心取指定大小的邻域；
    % 2. 同时满足三个条件才判定为极值：
    %    中心点是邻域内的最大值 / 最小值；
    %    中心点大于 / 小于邻域平均值；
    %    差值超过设定的显著度阈值，排除平缓的伪极值。
    for i = edge_margin:size(data,1)-edge_margin
        for j = edge_margin:size(data,2)-edge_margin
            % 调整邻域范围
            row_range = max(1, i-nh_radius(1)) : min(size(data,1), i+nh_radius(1));
            col_range = max(1, j-nh_radius(2)) : min(size(data,2), j+nh_radius(2));
            region = data(row_range, col_range);
            center = data(i,j);

            % 计算显著性（与邻域均值的差）
            prominence = abs(center - mean(region(:)));

            % 检测极大值
            if center == max(region(:)) && ...
               center > mean(region(:)) && ...
               prominence >= p.Results.MinProminence
                max_locs = [max_locs; i, j];
                max_vals = [max_vals; center];
            end

            % 检测极小值
            if center == min(region(:)) && ...
               center < mean(region(:)) && ...
               prominence >= p.Results.MinProminence
                min_locs = [min_locs; i, j];
                min_vals = [min_vals; center];
            end
        end
    end

    % 应用非极大值抑制（NMS）：
    % 把检测到的极大值按数值从高到低排序；
    % 从最强的开始，逐个检查后面的点和已保留点的距离；
    % 如果距离小于设定的最小间距，就删掉这个较弱的极值点；
    % 极小值点同理做同样的抑制。
    % 作用：消除同一个凸起 / 凹坑上的重复检测点，每个区域只保留一个最显著的极值。
    
    if ~isempty(max_locs) && p.Results.MinDistance > 0
        [~, sort_idx] = sort(max_vals, 'descend');
        keep = true(size(max_locs,1),1);
        for k = 2:length(sort_idx)
            dists = sqrt(sum((max_locs(sort_idx(k),:) - max_locs(sort_idx(1:k-1),:)).^2, 2));
            if any(dists < p.Results.MinDistance)
                keep(sort_idx(k)) = false;
            end
        end
        max_locs = max_locs(keep,:);
    end

    if ~isempty(min_locs) && p.Results.MinDistance > 0
        [~, sort_idx] = sort(min_vals, 'ascend');
        keep = true(size(min_locs,1),1);
        for k = 2:length(sort_idx)
            dists = sqrt(sum((min_locs(sort_idx(k),:) - min_locs(sort_idx(1:k-1),:)).^2, 2));
            if any(dists < p.Results.MinDistance)
                keep(sort_idx(k)) = false;
            end
        end
        min_locs = min_locs(keep,:);
    end
end



function [shengdu,sjb,zhijin,max_locs, min_locs, boundaries,boundary_coords]=Copy_of_jixiantiqu_3D(surface_data,n,params,yuzhi)
    % 检测三维曲面极值点并可视化 
    % 输入：surface_data - 二维矩阵表示的三维高度数据 
  
    % 创建网格坐标（用于可视化）
    [X, Y] = meshgrid(1:size(surface_data,2), 1:size(surface_data,1));
    
    % 寻找极值点 
    [max_locs, min_locs] = find_local_extrema(surface_data,params);
    
    % 分水岭寻求边界
    [boundaries,boundary_coords] = fenshuiling_boundry(surface_data, max_locs,yuzhi);

    [shengdu,sjb,zhijin] = fushikengtiqu(surface_data,boundary_coords,max_locs);

    % 可视化结果 
    figure('Position', [100, 100, 1200, 500]);
    
    % 子图1：三维曲面显示 
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
    
    title('三维曲面极值点检测');
    xlabel('X方向'); ylabel('Y方向'); zlabel('高度');
    legend('曲面', '极大值点', '极小值点');
    grid on;
    colormap jet;
    colorbar;
    view(-30, 45);
    
    % 子图2：二维等高线显示 
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
 
function [max_locs, min_locs] = find_local_extrema(data, params)
    % 改进的三维极值点检测函数
    % 参数解析
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

    % 主检测循环
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

    % 应用非极大值抑制（NMS）
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



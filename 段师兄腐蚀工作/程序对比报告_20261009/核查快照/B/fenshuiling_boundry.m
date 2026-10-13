function [boundaries,boundary_coords] = fenshuiling_boundry(surface_data, max_locs,yuzhi)
    % 初始化标记矩阵
    markers = zeros(size(surface_data));
    for k = 1:size(max_locs,1)
        markers(max_locs(k,1), max_locs(k,2)) = k;
    end
    
    % 高斯平滑处理
    sigma = 0.5;
    smoothed_data = imgaussfilt(surface_data, sigma);
    
    % 梯度计算与处理
    [gx, gy] = imgradientxy(smoothed_data, 'sobel');
    gradient_mag = hypot(gx, gy);
    
    % 自适应梯度阈值处理
    local_contrast = stdfilt(surface_data, ones(5));
    min_height_diff = 0.01 * local_contrast; 
    gradient_mag(gradient_mag < min_height_diff) = 255;
    
    % 背景标记检测
    distance = bwdist(markers > 0);
    background = distance > yuzhi*max(distance(:));
    markers(background) = 255;
    
    % 梯度图修正
    gradient_modified = imimposemin(gradient_mag, markers > 0);
    
    % 分水岭分割
    labels = watershed(gradient_modified);
    
    % 建立极值点与区域的映射
    boundary_coords = cell(size(max_locs,1), 1); % 按输入顺序初始化
    for k = 1:size(max_locs,1)
        % 获取当前极值点坐标
        r = max_locs(k,1);
        c = max_locs(k,2);
        
        % 验证坐标有效性
        if r > size(labels,1) || c > size(labels,2)
            warning('无效坐标: 索引%d (%d,%d)',k,r,c);
            continue;
        end
        
        % 获取对应区域标签
        region_label = labels(r,c);
        
        % 提取区域边界
        region_mask = (labels == region_label);
        B = bwboundaries(region_mask, 'noholes');
        
        if ~isempty(B)
            % 转换为[x,y,height]格式
            coords = B{1}(:, [2 1]); 
            heights = surface_data(sub2ind(size(surface_data), coords(:,2), coords(:,1)));
            boundary_coords{k} = [coords, heights];
        else
            boundary_coords{k} = [];
            warning('未找到索引%d的边界',k);
        end
    end
    
    % 生成边界矩阵
    boundaries = labels == 0;
    
    % 可视化系统
    figure
    subplot(2,3,1), imshow(surface_data,[]), title('原始数据')
    subplot(2,3,2), imshow(markers>0), title('极值点标记')
    subplot(2,3,3), imshow(gradient_modified,[]), title('修正梯度')
    subplot(2,3,4), imshow(boundaries), title('分割边界')
    subplot(2,3,5), imshow(label2rgb(labels,'jet','k')), title('区域标签')
    subplot(2,3,6), surf(smoothed_data,'EdgeColor','none'), hold on
    contour3(boundaries,[1 1],'r','LineWidth',1), view(-30,60), title('3D可视化')
end
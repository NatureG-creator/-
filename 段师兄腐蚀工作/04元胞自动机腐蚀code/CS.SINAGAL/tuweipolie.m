function [tuweipoliedian,p_xiugai]=tuweipolie(a,w,l,p_o,max_gaocha,n)  % 新增n作为输入参数
    depth_map=zeros(size(a,1),size(a,2));
    for i = 1:w
        for j = 1:l
            depth = find(squeeze(a(i,j,:)) == 1, 1, 'first');
            if isempty(depth)
                depth_map(i,j) = n + 1;  % n已作为输入参数，不再未定义
            else
                depth_map(i,j) = depth;
            end
        end
    end
    gaocha=max(depth_map(:))-min(depth_map(:));
    if gaocha>=2
        threshold=0.05*gaocha+min(depth_map(:));
        % 修正：筛选深度≥阈值的元胞（凸起点，腐蚀较浅）
        convex_mask = depth_map >= threshold;  
        [row_indices, col_indices] = find(convex_mask);  
        tuweipoliedian=[row_indices, col_indices];  % 列数=2，正确
        if gaocha<=max_gaocha
            p_xiugai=(gaocha/max_gaocha)*(p_o-1)+1;
        else
            p_xiugai=p_o; 
        end
    else
        % 修正：无凸起点时返回空的2列矩阵（避免ismember报错）
        tuweipoliedian = zeros(0, 2);  
        p_xiugai=1;
    end
end
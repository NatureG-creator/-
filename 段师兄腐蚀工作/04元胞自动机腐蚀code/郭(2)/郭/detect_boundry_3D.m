function boundary = detect_boundry_3D(a, n)
    % 输入参数校验（增加鲁棒性）
    if ~isnumeric(a) || ndims(a) ~= 3
        error('输入a必须是3维数值数组');
    end
    if ~isscalar(n) || n < 1 || ~isnumeric(n)
        error('n必须是正标量数值');
    end
    
    [~, ~, d_orig] = size(a);
    
    % 快速检查：如果没有零值，直接返回空（提前退出，省内存）
    if ~any(a(:) == 0)
        boundary = [];
        % 即时清理：函数提前退出前释放所有临时变量
        clear w l d_orig;
        return;
    end
    
    % --------------------------
    % 优化1：减少内存占用 - 精准计算处理深度（优化find逻辑+即时清理）
    % --------------------------
    % 改用逻辑索引找零值位置，避免find产生大数组
    zero_mask = a == 0;
    % 优化：用any逐层检查，替代find生成全量z_zeros数组（大幅减少内存）
    % 正确：按z维度（第3维）检查每层是否有零值，直接提取z层下标
    z_nonzero = find(any(any(zero_mask, 1), 2), 1, 'last'); % 找最后一个有零值的z层（匹配原代码逻辑）
    % 补充：如果想找所有有零值的z层，去掉'last'即可：z_nonzero = find(any(any(zero_mask, 1), 2));
    JIZHUN_Z = min(max(z_nonzero) + 1, n + 1);
    process_depth = min(JIZHUN_Z, d_orig);
    % 即时清理：用完zero_mask和z_nonzero立即释放（大体积逻辑数组）
    clear zero_mask z_nonzero;
    
    % 如果处理深度为0，直接返回空
    if process_depth < 1
        boundary = [];
        clear w l d_orig process_depth JIZHUN_Z;
        return;
    end
    
    % --------------------------
    % 优化2：低内存边界检测 - 利用卷积/邻域检查
    % --------------------------
    % 定义3D 6邻域结构元素（只检查上下左右前后6个方向）
    se = false(3,3,3);
    se(2,2,1) = true; % Z-
    se(2,2,3) = true; % Z+
    se(2,1,2) = true; % Y-
    se(2,3,2) = true; % Y+
    se(1,2,2) = true; % X-
    se(3,2,2) = true; % X+
    
    % 只处理需要的深度范围，减少内存加载
    a_process = a(:, :, 1:process_depth);
    non_zero_mask = a_process ~= 0; % 非零区域掩码
    
    % 重新生成当前处理范围的零掩码（仅小范围，省内存）
    zero_mask_process = ~non_zero_mask;
    % 用imdilate找非零区域的边界（邻域有零的点）
    expanded_zero = imdilate(zero_mask_process, se); % 膨胀零区域到邻域
    boundary_mask = non_zero_mask & expanded_zero;    % 非零且邻域有零 = 边界
    
    % 即时清理：用完大体积3D数组立即释放
    clear a_process non_zero_mask zero_mask_process expanded_zero se;
    
    % --------------------------
    % 优化3：精准提取边界坐标，无预分配浪费（优化find+即时清理）
    % --------------------------
    % 分步提取索引，避免一次性生成大数组
    boundary_idx = find(boundary_mask); % 边界点线性索引
    [x_coords, y_coords, z_coords] = ind2sub(size(boundary_mask), boundary_idx);
    boundary = [x_coords, y_coords, z_coords];
    % 即时清理：用完边界掩码和索引立即释放
    clear boundary_mask boundary_idx x_coords y_coords z_coords;
    
    % 最终检查：如果无边界点返回空
    if isempty(boundary)
        boundary = [];
    end
    
    % --------------------------
    % 终极优化：强制清理内存碎片（轻量、不阻塞）
    % --------------------------
    % 清理所有剩余临时变量
    clear w l d_orig process_depth JIZHUN_Z;
end
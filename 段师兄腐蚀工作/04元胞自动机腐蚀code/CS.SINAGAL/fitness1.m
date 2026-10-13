function [sd_OBJV, sd_a, sd_d, sd_cl] = fitness1(XY, NIND, data, data_x, a_jisuan, F, n, w, l, space, d_jisuan, stage_number, CL_concentration_jisuan)
    % -------------------------------------------------------------------------
    % 自动分批处理版 fitness 函数（解决 parfor 序列化内存不足问题）
    % 原逻辑保留，但将大种群拆分为小批次并行计算
    % -------------------------------------------------------------------------
    
    % === 配置：分批数量（可调整）===
    num_batches = 5;  % 分成10批；若仍内存不足，可增大到20、50等
    
    % 如果个体数很少，就不分批（避免每批只有1-2个，效率低）
    if NIND <= max(10, num_batches)
        use_batching = false;
    else
        use_batching = true;
        batch_size = ceil(NIND / num_batches);
    end

    % 初始化输出
    sd_OBJV = zeros(NIND, size(data, 2));
    sd_a = cell(NIND, 1);
    sd_d = cell(NIND, 1);
    sd_cl = cell(NIND, 1);

    if ~use_batching
        % 直接全量计算（小种群）
        %fprintf('Running fitness on all %d individuals at once.\n', NIND);
        do_parfor_computation(1, NIND);
    else
        % 分批计算
        %fprintf('Splitting %d individuals into %d batches.\n', NIND, num_batches);
        for b = 1:num_batches
            idx_start = (b - 1) * batch_size + 1;
            idx_end = min(b * batch_size, NIND);
            if idx_start > NIND, break; end
            
            %fprintf('  Batch %d: individuals %d to %d\n', b, idx_start, idx_end);
            do_parfor_computation(idx_start, idx_end);
        end
    end

    % -------------------------------------------------------------------------
    % 内嵌函数：执行一段索引范围内的 parfor 计算
    % -------------------------------------------------------------------------
    function do_parfor_computation(start_idx, end_idx)
        local_N = end_idx - start_idx + 1;
        local_XY = XY(start_idx:end_idx, :);
        
        % 临时存储（仅用于当前批次）
        local_OBJV = zeros(local_N, size(data, 2));
        local_a = cell(local_N, 1);
        local_d = cell(local_N, 1);
        local_cl = cell(local_N, 1);

        % 并行计算当前批次
        parfor i = 1:local_N
            [CS, a, d, CL_concentration] = CA(...
                local_XY(i, :), F, a_jisuan, data, data_x, ...
                n, w, l, space, d_jisuan, stage_number, CL_concentration_jisuan);
            
            local_OBJV(i, :) = round(abs(CS), 4);
            local_a{i} = single(a);
            local_d{i} = single(d);
            local_cl{i} = single(CL_concentration);
        end

        % 写回主结果
        sd_OBJV(start_idx:end_idx, :) = local_OBJV;
        sd_a(start_idx:end_idx) = local_a;
        sd_d(start_idx:end_idx) = local_d;
        sd_cl(start_idx:end_idx) = local_cl;
    end

end
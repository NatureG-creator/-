function [a, CL_concentration] = basic_spread(x, y, z, a, p_h, p_v, n, CL_concentration, CL_threshold, w, l)
    % 6邻域基础扩散算法
    % 定义6个方向：前/后/左/右/上/下
    directions = [
        x, y-1, z, p_h;   % 左
        x, y+1, z, p_h;   % 右
        x-1, y, z, p_h;   % 前 
        x+1, y, z, p_h;   % 后
        x, y, z-1, p_v;   % 上
        x, y, z+1, p_v    % 下
    ];
    
    % 对每个方向执行扩散
    for c = 1:size(directions, 1)
        % 获取目标坐标和概率
        ni = directions(c, 1);
        nj = directions(c, 2);
        nk = directions(c, 3);
        base_prob = directions(c, 4);
        
        % 边界检查
        if (ni >= 1 && ni <= w) && (nj >= 1 && nj <= l) && (nk >= 1 && nk <= n)
            % 验证索引有效性
            if ni <= size(a, 1) && nj <= size(a, 2) && nk <= size(a, 3) && ...
               ni <= size(CL_concentration, 1) && nj <= size(CL_concentration, 2)
                
                % 动态概率计算 (考虑氯离子分布)
                CL_factor = min(CL_concentration(ni, nj) / CL_threshold, 1.0);
                prob = base_prob * 0.5 * (1 + CL_factor);
                
                if rand < prob && a(ni, nj, nk) == 1
                    % 腐蚀扩散
                    a(ni, nj, nk) = 0;
                    
                    % 可选：更新氯离子浓度
                    % CL_concentration(ni, nj) = min(CL_concentration(ni, nj) + 0.3, CL_threshold);
                end
            end
        end
    end
end
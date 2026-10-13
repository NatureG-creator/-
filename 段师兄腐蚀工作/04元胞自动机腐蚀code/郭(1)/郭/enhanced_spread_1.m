function [a, CL_concentration] = enhanced_spread(x, y, z, a, p_h, p_v, n, CL_concentration, CL_threshold, w, l)
    % 26邻域增强扩散算法
    % 增强扩散能力系数
    diffusion_boost = 1.0;  % 扩散能力增强系数
    
    % 生成26邻域偏移量
    [X, Y, Z] = meshgrid(-1:1, -1:1, -1:1);
    offsets = [X(:), Y(:), Z(:)];
    offsets(14, :) = [];  % 移除中心点(0,0,0)
    
    % 计算各方向的基础概率
    base_probs = zeros(26, 1);
    for i = 1:26
        dist = norm(offsets(i, :));
        if dist == 1  % 6个面邻域
            base_probs(i) = diffusion_boost * max(p_h, p_v);
        elseif dist == sqrt(2)  % 12个边邻域
            base_probs(i) = diffusion_boost * 0.7 * max(p_h, p_v);
        else  % 8个角邻域
            base_probs(i) = diffusion_boost * 0.4 * max(p_h, p_v);
        end
    end
    
    % 对每个邻域点执行扩散
    for i = 1:26
        ni = x + offsets(i, 1);
        nj = y + offsets(i, 2);
        nk = z + offsets(i, 3);
        base_prob = base_probs(i);
        
        % 边界检查
        if (ni >= 1 && ni <= w) && (nj >= 1 && nj <= l) && (nk >= 1 && nk <= n)
            % 验证索引有效性
            if ni <= size(a, 1) && nj <= size(a, 2) && nk <= size(a, 3) && ...
               ni <= size(CL_concentration, 1) && nj <= size(CL_concentration, 2)
                
                % 获取氯离子影响因子（非线性增强）
                CL_factor = min((CL_concentration(ni, nj) / CL_threshold)^2, 1.0);
                
                % 动态概率计算（考虑氯离子浓度影响）
                prob = base_prob * (1 + CL_factor);
                
                if rand < prob && a(ni, nj, nk) == 1  % 仅影响未腐蚀金属
                    a(ni, nj, nk) = 0;  % 腐蚀扩散
                    
                    % 更新氯离子浓度
                    CL_concentration(ni, nj) = min(CL_concentration(ni, nj) + 0.5, CL_threshold);
                    
                    % 有限递归扩散（防止过度扩散）
                    if rand < 0.15  % 15%概率触发二次扩散
                        [a, CL_concentration] = spread_corrosion_3d(...
                            ni, nj, nk, a, p_h*0.9, p_v*0.9, n, CL_concentration, CL_threshold);
                    end
                end
            end
        end
    end
end

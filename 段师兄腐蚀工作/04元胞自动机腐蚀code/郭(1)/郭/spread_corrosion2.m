function [a,CL_concentration]=spread_corrosion2(x, y, z, a, p_h, p_v, n, CL_concentration, CL_threshold)
    % 增强扩散能力系数
    diffusion_boost = 1;  % 扩散能力增强系数 (1.0-2.0)
    
    % 三维扩散方向设置 - 26邻域（6面+12边+8角）
    [X,Y,Z] = meshgrid(-1:1, -1:1, -1:1);
    offsets = [X(:), Y(:), Z(:)];
    offsets(14, :) = [];  % 移除中心点(0,0,0)
    
    % 动态概率矩阵 (面/边/角差异化概率)
    base_probs = zeros(26,1);
    for i = 1:26
        dist = norm(offsets(i,:));
        if dist == 1         % 6个面邻域
            base_probs(i) = diffusion_boost * max(p_h, p_v);
        elseif dist == sqrt(2) % 12个边邻域
            base_probs(i) = diffusion_boost * 0.6 * max(p_h, p_v);
        else                % 8个角邻域
            base_probs(i) = diffusion_boost * 0.3 * max(p_h, p_v);
        end
    end
     % 获取a数组的三维维度信息（w*l*n）
        w = size(a, 1);  % 第一维度（宽度）
        l = size(a, 2);  % 第二维度（长度）
    % 第三维度为函数参数n（深度）
    for i = 1:26
        ni = x + offsets(i,1);
        nj = y + offsets(i,2);
        nk = z + offsets(i,3);
        base_prob = base_probs(i);
        
        % 边界检查
       if (ni >= 1 && ni <= w) && (nj >= 1 && nj <= l) && (nk >= 1 && nk <= n)
            % 获取氯离子影响因子（非线性增强）
            CL_factor = (CL_concentration(ni, nj) / CL_threshold)^2;
            
            % 动态概率计算（考虑三维空间影响）
            prob = base_prob * (1 + CL_factor);
            
            if rand < prob && a(ni, nj, nk) == 1  % 仅影响未腐蚀金属
                a(ni, nj, nk) = 0;  % 腐蚀扩散
                
                % 更新氯离子浓度（三维位置）
                CL_concentration(ni, nj) = min(CL_concentration(ni, nj)+1, CL_threshold);
                
                % 递归扩散（深度为1，避免过扩散）
                if rand < 0.8  % 30%概率触发二次扩散
                    [a, CL_concentration] = spread_corrosion(...
                        ni, nj, nk, a, p_h, p_v, n, CL_concentration, CL_threshold);
                end
            end
        end
    end
end

function [a,CL_concentration]=spread_corrosion(x, y, z, a, p_h, p_v,n,CL_concentration,CL_threshold)
    % 三维扩散方向设置 (前/后/左/右/上/下)
    directions = [x, y-1, z, p_h;   % 左
                  x, y+1, z, p_h;   % 右
                  x-1, y, z, p_h;   % 前 
                  x+1, y, z, p_h;   % 后
                  x, y, z-1, p_v;   % 上
                  x, y, z+1, p_v;]; % 下
     % 获取a数组的三维维度信息（w*l*n）
        w = size(a, 1);  % 第一维度（宽度）
        l = size(a, 2);  % 第二维度（长度）
    % 第三维度为函数参数n（深度
	    for C = 1:size(directions, 1)
        % 获取目标坐标和概率
        ni = directions(C, 1);
        nj = directions(C, 2);
        nk = directions(C, 3);
        base_prob = directions(C, 4);
        
        % 边界检查 (三维范围)
        if (ni >= 1 && ni <= w) && (nj >= 1 && nj <= l) && (nk >= 1 && nk <= n)
            % 动态概率计算 (考虑三维氯离子分布)
            CL_factor = CL_concentration(ni, nj) / CL_threshold;
            prob = base_prob * 0.5 * (1 + CL_factor);
            
            if  rand < prob && a(ni, nj, nk)==1
                % 腐蚀扩散
                a(ni, nj, nk) = 0;
                %CL_concentration(max(1,ni),max(1,nj))=min(CL_concentration(max(1,ni),max(1,nj))+1, CL_threshold);
                %CL_concentration(min(n,ni),min(n,nj))=min(CL_concentration(min(n,ni),min(n,nj))+1, CL_threshold);
            end
        end
    end
end
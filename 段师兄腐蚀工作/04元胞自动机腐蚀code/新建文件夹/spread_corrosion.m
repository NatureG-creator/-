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
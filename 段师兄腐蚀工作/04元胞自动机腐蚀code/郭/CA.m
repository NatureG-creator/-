function [CS, a , d, CL_concentration] = CA(XY, F , a, data, data_x ,n,w,l, space, d ,stage_number,CL_concentration)
    N = F;                 % 迭代次数
    p_uniform_base = XY(1);   % 基础均匀腐蚀概率
    p_passive_base = XY(2);    % 基础钝化概率
    p_break = XY(3);          % 钝化膜破裂概率（固定）
    CL_threshold = XY(4);        % 氯离子浓度阈值
    alpha_corrosion =XY(5) ;   % 腐蚀概率放大系数
    alpha_passive = 0.8;     % 钝化概率衰减系数
    simutive_point = XY(6);     % 金属敏感系数
    alpha_p_break =XY(7);      %钝化膜破裂放大系数
	p_h = XY(8); % 水平扩散概率（左右方向）
    p_v = XY(9); % 垂直扩散概率（上下方向）
    p_o = XY(10); % 额外凸位破裂增强概率
    for m=2:n+1
        s_p=randi(w*l*n,1,round(w*l*n*simutive_point));
        d(s_p)=1;
    end
    
    
    
    % 在函数开头添加初期增强参数（可根据需求设为输入或默认值）
    K0 = 0;        % 初期增强持续的迭代次数（前10轮）
    if stage_number==1
         beta=1;
    end

for k = 1:N
    % 额外附加机制凸起破裂概率修正
    %tuweipolie为记录凸起点位x,y坐标的n*2矩阵
    %p_o为凸位破裂最大增强概率
    %30为最大修改高差，超过该高差后修正概率也不超过p_o
    
    [tuweipoliedian,p_tuwei]=tuweipolie(a,w,l,p_o,30,n);

        % 1. 检测所有与腐蚀区域相邻的边界元胞
        % 检测边界元胞
        boundary = detect_boundry_3D(a, n);
        if isempty(boundary)
            break
        end
        % 1. 批量转换边界元胞的索引（预计算，避免循环内的sub2ind）
        boundary_idx = sub2ind(size(a), boundary(:,1), boundary(:,2), boundary(:,3));
        boundary_xy_idx = sub2ind(size(CL_concentration), boundary(:,1), boundary(:,2));
        % 2. 批量提取状态值与参数（过滤无效元胞）
        a_vals = a(boundary_idx);  
        valid_mask = (a_vals ~= 0);  % 过滤已腐蚀的元胞（a=0）
        boundary_idx = boundary_idx(valid_mask);  
        boundary_xy_idx = boundary_xy_idx(valid_mask);  
        boundary = boundary(valid_mask,:);  
        a_vals = a_vals(valid_mask);  
        d_vals = d(boundary_idx);  
        CL_vals = CL_concentration(boundary_xy_idx); 
        % 3. 向量化计算概率与掩码
        inv_CL_threshold = 1 / CL_threshold; 
        CL_factor = CL_vals * inv_CL_threshold; 
        decay_factor = ones(size(a_vals)); 
        % 初期增强系数随迭代次数线性衰减（k=1时beta_max，k=K0时回归1）
        if k <= K0
            decay_factor = 1 + (beta - 1) * (K0 - k + 1) / K0;  
        end
        p_uniform = p_uniform_base * (1 + alpha_corrosion * CL_factor) .* decay_factor;  
        p_passive = p_passive_base * (1 - alpha_passive * CL_factor);  
        rand_vals = rand(size(a_vals));  
        % 4. 批量更新金属元胞（a=1）的腐蚀/钝化
        metal_mask = (a_vals == 1);  % 标记金属元胞
        % 子场景1.1：满足腐蚀条件（rand < p_uniform）
        corrode_mask = metal_mask & (rand_vals < p_uniform);
        % 子场景1.1.1：d>1 → d减1；子场景1.1.2：d=1 → a=0
        d_corrode_mask = corrode_mask & (d_vals > 1);  
        a_corrode_mask = corrode_mask & (d_vals == 1);
        % 批量更新d和a
        d(boundary_idx(d_corrode_mask)) = d(boundary_idx(d_corrode_mask)) - 1;  
        a(boundary_idx(a_corrode_mask)) = 0;  
        % 子场景1.2：不腐蚀但满足钝化条件（rand < p_passive）
        passive_mask = metal_mask & ~corrode_mask & (rand_vals < p_passive);  
        a(boundary_idx(passive_mask)) = 2; % 批量设置为钝化状态

        % 5. 批量更新钝化元胞（a=2且d=1）的破裂
        passive_break_mask = (a_vals == 2) & (d_vals == 1); 
        p_break_cl = zeros(size(passive_break_mask));
        % 筛选passive_break_mask为true的索引
        valid_idx = find(passive_break_mask);
        % 标记凸起点
        boundary_xy = boundary(passive_break_mask,1:2);  
        is_convex = ismember(boundary_xy, tuweipoliedian,'rows'); 
        % 仅对有效索引计算破裂概率
        if ~isempty(valid_idx)
            % 提取有效元胞的CL_factor
            valid_CL_factor = CL_factor(valid_idx); 
            % 计算破裂概率（分阶段逻辑不变）
        if stage_number == 1
            temp_p = p_break * (1 + alpha_p_break * valid_CL_factor).^2;
        else
            temp_p = p_break * (1 + alpha_p_break * valid_CL_factor);
        end
        % 凸位增强（先获取有效元胞中的凸位索引）
        valid_is_convex = is_convex; % 假设is_convex与passive_break_mask同维度
        temp_p(valid_is_convex) = temp_p(valid_is_convex) * p_tuwei;
        % 将计算结果赋值回p_break_cl的有效位置
        %不开启凸位破裂机制
        p_break_cl(valid_idx) = temp_p; 
        end
            
            % 批量判断破裂条件
            break_mask = passive_break_mask & (rand(size(passive_break_mask)) < p_break_cl);
            if any(break_mask)
            % 批量更新a为腐蚀状态
            a(boundary_idx(break_mask)) = 0;  
            % 批量更新氯离子浓度（不超过阈值）
            CL_concentration(boundary_xy_idx(break_mask)) = min(CL_concentration(boundary_xy_idx(break_mask)) + 1, CL_threshold);  
            % 批量调用spread_corrosion2（若该函数支持向量化，可进一步优化；否则保留循环，但仅处理破裂元胞）
            for i = find(break_mask)'
                [a, CL_concentration] = spread_corrosion2(boundary(i,1), boundary(i,2), boundary(i,3), a, p_h, p_v, n, CL_concentration, CL_threshold);
            end
            end
 
        % 检测并重置达到阈值的氯离子浓度
	    CL_concentration(CL_concentration >= CL_threshold) = 0;
        
        
        %[x, y, z] = meshgrid(1:n, 1:n, 2:n);
        %A = a(1:n,1:n,2:n);  %旋转数组使其显示达到上面为氧元胞下面为金属元胞
        %result = scatter3(x(:),y(:), z(:), 10, A(:), 'filled');
        %result.MarkerEdgeColor = [28/255,28/255,28/255];
        %axis([1 n 1 n 1 n]);
        %axis ij
        %set(gca, 'ZDir','reverse') % 反转Z轴方向
        %view(37.5, 30) % 标准三维视角
        %title(['Iteration ', num2str(k)]);
        %pause(0.01);
        
        %进行数据提取工作
        %质量损失率
            quality_loss=(w*l*n-sum(sum(sum(a==1))))/(w*l*n);
        %平均腐蚀深度
            Average_depth=quality_loss*n*space;
            if data_x-Average_depth<=0
                break
            end
end
            size_chuangkou=11;
            [baseline, ~,~,depth_map] = moving_avg_3D(a,size_chuangkou,w,l,n);
            [baseline] = expandMatrix(baseline, 1);
            jicha=max(baseline(:))-min(baseline(:));
            bj_depth=mean(depth_map(:)-min(depth_map(:)))*space;
            if jicha<3
            yuzhi=0.3;
            scale=15;
            elseif jicha<5
            yuzhi=0.4;
            scale=20;
            else
            yuzhi=0.5;
            scale=25;
            end 

            params = {'MinProminence', 0.05, 'MinDistance', 15,'Neighborhood', [scale,scale]};
            [shengdu,sjb,~,~, ~, ~,~]=jixiantiqu_3D(baseline,n,params,yuzhi);
            shengdu=log(shengdu.*space);
            sjb=sjb./10;
            jsb=log(1./sjb);
            sigma1 = std(jsb, 1);
            sigma2 = std(shengdu, 1);
            CS=([Average_depth bj_depth mean(jsb) mean(shengdu) sigma1 sigma2]-data)./data;
end 

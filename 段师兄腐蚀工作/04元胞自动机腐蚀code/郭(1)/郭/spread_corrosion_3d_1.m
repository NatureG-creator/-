function [a, CL_concentration] = spread_corrosion_3d(x, y, z, a, p_h, p_v, n, CL_concentration, CL_threshold)
    % 三维腐蚀扩散模拟系统 - 整合版本
    % 参数:
    % x, y, z - 当前腐蚀点坐标
    % a - 三维金属状态数组 (1=未腐蚀, 0=已腐蚀)
    % p_h - 水平扩散概率
    % p_v - 垂直扩散概率
    % n - 第三维度大小
    % CL_concentration - 氯离子浓度分布
    % CL_threshold - 氯离子阈值
    
    % 获取数组维度信息
    [w, l, ~] = size(a);
    
    % 设置扩散模式选择标志
    enhanced_mode = 0;  % 启用26邻域增强模式
    
    if enhanced_mode
        % 26邻域扩散模式 (6面+12边+8角)
        [a, CL_concentration] = enhanced_spread(x, y, z, a, p_h, p_v, n, CL_concentration, CL_threshold, w, l);
    else
        % 6邻域基础扩散模式 (前后左右上下)
        [a, CL_concentration] = basic_spread(x, y, z, a, p_h, p_v, n, CL_concentration, CL_threshold, w, l);
    end
end



function XY = er2shi(Chrom, lb, ub, bits_per_param)
    % 参数定义
    [NIND, ~] = size(Chrom);
    LIND = length(lb); % 参数个数
    
    % 预分配十进制参数矩阵
    XY = zeros(NIND, LIND);
    
    % 逐参数解码
    for j = 1:LIND
        % 计算当前参数在 Chrom 中的列范围
        start_bit = (j-1)*bits_per_param + 1;
        end_bit = j*bits_per_param;
        
        % 提取二进制位（数值矩阵）
        binary_bits = Chrom(:, start_bit:end_bit);
        
        % 将二进制转换为整数（0 ~ 2^bits_per_param-1）
        int_values = binary_bits * (2.^(bits_per_param-1:-1:0))';
        
        % 线性映射到实际参数范围 [lb(j), ub(j)]
        XY(:, j) = lb(j) + (ub(j) - lb(j)) * int_values / (2^bits_per_param - 1);
    end
end
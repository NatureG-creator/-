function Chrom = latin_begin(NIND, LIND, bits_per_param)
    % 生成基础拉丁超立方样本（范围 [0,1]），避免依赖 Statistics Toolbox。
    population = zeros(NIND, LIND);
    for j = 1:LIND
        population(:, j) = (randperm(NIND)' - rand(NIND, 1)) / NIND;
    end
    % 映射到整数 0~2047（兼容 11 位二进制）
    scaled_samples = round(population * (2^bits_per_param - 1));
    
    % 预分配二进制矩阵（数值型）
    Chrom = zeros(NIND, LIND * bits_per_param);
    
    % 逐参数转换为二进制
    for j = 1:LIND
        % 提取当前参数的整数值（列向量）
        param_ints = scaled_samples(:, j);
        
        % 生成二进制位矩阵（从最高位到最低位）
        bits = zeros(NIND, bits_per_param);
        for k = 1:bits_per_param
            bits(:, k) = bitget(param_ints, bits_per_param - k + 1);
        end
        
        % 填充到 Chrom 矩阵的对应位置
        start_col = (j-1)*bits_per_param + 1;
        end_col = j*bits_per_param;
        Chrom(:, start_col:end_col) = bits;
    end
end

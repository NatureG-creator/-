function SelCh_2 = jiaocha(SelCh_1, px, LIND)
    % 改进的交叉函数
    % 输入参数：
    %   SelCh_1 - 父代种群矩阵，尺寸为 [NIND, LIND*11]
    %   px      - 交叉概率（0~1）
    %   LIND    - 参数个数
    % 输出参数：
    %   SelCh_2 - 子代种群矩阵
    
    [NIND, chrom_len] = size(SelCh_1);
    bits_per_param = chrom_len / LIND; % 每个参数的二进制位数（应为11）
    
    % 打乱个体顺序以避免顺序偏差
    shuffled_indices = randperm(NIND);
    SelCh_shuffled = SelCh_1(shuffled_indices, :);
    
    % 遍历所有可能的配对（步长为2）
    for i = 1:2:NIND-1
        if rand < px
            % 随机选择交叉点（参数边界或参数内部）
            param_idx = randi(LIND); % 选择第几个参数
            bit_in_param = randi(bits_per_param); % 在参数内部的位置
            crossover_point = (param_idx-1)*bits_per_param + bit_in_param;
            
            % 执行交叉
            temp = SelCh_shuffled(i, crossover_point:end);
            SelCh_shuffled(i, crossover_point:end) = SelCh_shuffled(i+1, crossover_point:end);
            SelCh_shuffled(i+1, crossover_point:end) = temp;
        end
    end
    
    % 恢复原始顺序（可选，若需保持种群结构则跳过）
    SelCh_2 = SelCh_shuffled(shuffled_indices, :);
end




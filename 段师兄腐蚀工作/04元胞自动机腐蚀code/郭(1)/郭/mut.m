function SelCh_3 = mut(SelCh_2, pm)
    % 高效向量化变异函数
    % 输入参数：
    %   SelCh_2 - 输入种群矩阵（数值型，元素为0或1），尺寸 [NIND, LIND*11]
    %   pm      - 变异概率（0~1）
    % 输出参数：
    %   SelCh_3 - 变异后的种群矩阵
    
    % 生成变异掩码（逻辑矩阵）
    mutation_mask = rand(size(SelCh_2)) < pm;
    
    % 执行变异（翻转选中位的值）
    SelCh_3 = SelCh_2; % 创建副本
    SelCh_3(mutation_mask) = 1 - SelCh_3(mutation_mask);
end

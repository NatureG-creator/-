function selected_indices = tournament_selection(Fitness, n_selection, tournament_size)
    % 输入参数：
    %   Fitness - 适应度向量（误差越小越好），尺寸 [NIND x 1]
    %   n_selection - 需要选择的个体数量
    %   tournament_size - 每轮锦标赛的参赛个体数（通常取2~5）
    % 输出：
    %   selected_indices - 被选中的个体索引，尺寸 [1 x n_selection]

    NIND = length(Fitness);
    selected_indices = zeros(1, n_selection);
    
    for i = 1:n_selection
        % 随机选取 tournament_size 个参赛者（允许重复）
        candidates = randperm(NIND, tournament_size);
        %防止重复选择已经胜出个体
        while any(ismember(candidates, selected_indices))
            candidates = randperm(NIND, tournament_size);
        end
        % 找出误差最小适应度最大的个体
        [~, best_idx] = max(Fitness(candidates));
        
        % 记录胜出者的全局索引
        selected_indices(i) = candidates(best_idx);
    end
end
function B = shujuxiugai(A, target_min, varargin)
    % 增强腐蚀形貌数组的等高线效果，提高整体最小值，保持随机性和聚团性
    % 输入：
    %   A: 原始腐蚀深度数组（数值越大腐蚀越深）
    %   target_min: 目标最小值（处理后数组的最小值）
    %   可选参数（名称-值对）：
    %     'delta'：处理范围扩展参数（默认1，A <= target_min+delta的元素会被处理）
    %     'max_extra'：额外随机增量最大值（默认1，控制随机性范围）
    %     'sigma'：聚团性控制参数（默认0.5，高斯滤波标准差，值越大聚团区域越大）
    %     'levels'：等高线分层数量（默认3，建议2-5层）
    %     'intensity'：分层增量强度因子（默认[1.2, 1.0, 0.8]，长度需与levels一致，值越大增量越强）
    % 输出：
    %   B: 处理后的数组（带等高线效果，最小值为target_min）

    % 参数解析
    p = inputParser;
    addRequired(p, 'A', @(x) isnumeric(x) && all(size(x)>=2));
    addRequired(p, 'target_min', @(x) isscalar(x) && x > min(A(:)));
    addParameter(p, 'delta', 1, @(x) isscalar(x) && x >=0);
    addParameter(p, 'max_extra', 1, @(x) isscalar(x) && x >=0);
    addParameter(p, 'sigma', 0.5, @(x) isscalar(x) && x >0);
    addParameter(p, 'levels', 3, @(x) isscalar(x) && x >=2 && mod(x,1)==0);
    addParameter(p, 'intensity', [1.2, 1.0, 0.8], @(x) length(x)==p.Results.levels);
    parse(p, A, target_min, varargin{:});
    delta = p.Results.delta;
    max_extra = p.Results.max_extra;
    sigma = p.Results.sigma;
    levels = p.Results.levels;
    intensity = p.Results.intensity;

    % 步骤1：确定处理区域及等高线分层
    mask = A <= target_min + delta;
    original_min = min(A(:));
    depth_range = target_min + delta - original_min;  % 处理区间总深度范围
    layer_edges = linspace(original_min, target_min + delta, levels+1);  % 分层边界

    % 步骤2：基础增量（确保最小值达标）
    base_increment = max(0, target_min - A);

    % 步骤3：生成聚团性随机增量（带等高线分层）
    rand_matrix = rand(size(A));
    filtered_rand = imgaussfilt(rand_matrix, sigma);  % 聚团性随机场

    % 3.1 计算分层权重（区间重叠平滑过渡）
    layer_weights = zeros(levels, size(A,1), size(A,2));  % 分层权重矩阵
    for i = 1:levels
        % 区间下界和上界（重叠50%避免生硬边界）
        lower = layer_edges(i) - depth_range/(2*levels);
        upper = layer_edges(i+1) + depth_range/(2*levels);
        % 计算当前层权重（Sigmoid函数平滑过渡）
        layer_weights(i,:,:) = 1 ./ (1 + exp(10*(A - (lower + upper)/2)/(upper - lower)));
    end
    % 权重归一化（确保各点权重之和为1）
    layer_weights = layer_weights ./ repmat(sum(layer_weights,1), [levels,1,1]);

    % 3.2 分层随机增量计算（深度越低，增量强度越大）
    extra_increment = zeros(size(A));
    for i = 1:levels
        % 当前层增量 = 随机场 * 强度因子 * 层权重
       % 修复后代码（第60行）
extra_increment = extra_increment + filtered_rand .* max_extra .* intensity(i) .* squeeze(layer_weights(i,:,:));
    end

    % 步骤4：总增量计算与结果优化
    total_increment = base_increment + (extra_increment .* mask);  % 仅处理区域添加增量
    B = round(A + total_increment);  % 取整
    B(B < target_min) = target_min;  % 确保最小值达标
end
%% 功能：在【不改变矩阵大小】的前提下，将小矩阵居中替换大矩阵中心区域
% 大矩阵  size: M x N
% 小矩阵  size: P x Q
% 输出：大小不变，中心被小矩阵覆盖替换

function big_mat = insert_matrix_center(big_mat, small_mat)
    [M, N] = size(big_mat);   % 大矩阵尺寸
    [P, Q] = size(small_mat);% 小矩阵尺寸

    % 安全判断
    if P > M || Q > N
        error('小矩阵不能比大矩阵大！');
    end

    % ====================== 核心：计算居中起始坐标 ======================
    startRow = floor((M - P)/2) + 1;  % 起始行
    startCol = floor((N - Q)/2) + 1;  % 起始列

    % ====================== 直接替换中心区域 ======================
    big_mat(startRow : startRow+P-1, startCol : startCol+Q-1) = small_mat;
end
function [junyunfushi,Z_pingtanmian,Z_fushimian,columns] = jisuan_190(Z, cfg)
if nargin < 2 || isempty(cfg)
    cfg = step00_corrosion_config();
end
% 根据含平坦参考区的190 mm点云矩阵计算均匀腐蚀深度。
% 返回值单位与输入Z一致，通常为mm。

flat_count = cfg.reference.flat_column_count;
corrosion_count = cfg.reference.corrosion_column_count;
if size(Z,2) < flat_count
    error('jisuan_190: 输入矩阵列数不足，至少需要%d列。', flat_count);
end

Z_a = Z(:,1:flat_count);
Z_pingtanmian = (max(Z_a(:))-min(Z_a(:))) * ...
    cfg.reference.flat_height_ratio + min(Z_a(:));

start_col = round((size(Z,2)-(corrosion_count-1))/2) + 1;
end_col = start_col + corrosion_count - 1;
if start_col < 1 || end_col > size(Z,2)
    error('jisuan_190: 中央腐蚀区域%d列超出输入矩阵范围。', corrosion_count);
end
Z_b = Z(:,start_col:end_col);             % 中间腐蚀段
columns=start_col:end_col;
Z_fushimian = min(Z_b(:)); % 向内为正：最浅点而不是最深点代表均匀分量。

junyunfushi = Z_fushimian - Z_pingtanmian;

% 返回平滑前有符号深度；主流程以平滑后的最小深度作为最终指标。
end

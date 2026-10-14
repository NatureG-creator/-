function [junyunfushi,Z_pingtanmian,Z_fushimian,columns] = jisuan_190(Z, cfg)
if nargin < 2 || isempty(cfg)
    cfg = step00_corrosion_config();
end
% 参考区与腐蚀区使用同一完整扫描的齐平高程；函数名保留历史兼容，尺寸由矩阵和配置决定。
% 物理腐蚀深度取正值：
% 腐蚀区最高点 - 参考面。旧的反向差值另由主程序保存为有符号诊断。
% 返回值单位与输入Z一致，通常为mm。

flat_count = cfg.reference.flat_column_count;
corrosion_count = cfg.reference.corrosion_column_count;
assert(isnumeric(Z) && ismatrix(Z) && ~isempty(Z) && all(isfinite(Z(:))), ...
    'reference:InvalidMatrix','参考扫描矩阵必须为非空有限二维数值矩阵。');
assert(isscalar(flat_count) && isfinite(flat_count) && flat_count >= 1 && flat_count == fix(flat_count) && ...
    isscalar(corrosion_count) && isfinite(corrosion_count) && corrosion_count >= 1 && corrosion_count == fix(corrosion_count), ...
    'reference:InvalidColumns','参考区和腐蚀区列数必须为正整数。');
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
Z_fushimian = max(Z_b(:),[],'omitnan'); % 高程最高点，对应示意图的表面顶点。

junyunfushi = Z_fushimian - Z_pingtanmian;

% 不使用abs；正号来自明确的“腐蚀区高程-参考高程”方向定义。
end

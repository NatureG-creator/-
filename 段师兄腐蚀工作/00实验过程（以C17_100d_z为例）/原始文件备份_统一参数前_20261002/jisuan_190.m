function [junyunfushi,Z_pingtanmian,Z_fushimian] = jisuan_190(Z)
% 根据含平坦参考区的190 mm点云矩阵计算均匀腐蚀深度。
% 返回值单位与输入Z一致，通常为mm。

if size(Z,2) < 200
    error('jisuan_190: 输入矩阵列数不足，至少需要200列。');
end

Z_a = Z(:,1:200);                         % 左侧平坦参考区域
Z_pingtanmian = (max(Z_a(:))-min(Z_a(:)))*0.2 + min(Z_a(:));

start_col = round((size(Z,2)-167)/2) + 1;
end_col = start_col + 167;                % 共168列，约50 mm
Z_b = Z(:,start_col:end_col);             % 中间腐蚀段
Z_fushimian = max(Z_b(:));

junyunfushi = Z_pingtanmian - Z_fushimian;

disp(['均匀腐蚀深度：',num2str(junyunfushi),' mm']);
end

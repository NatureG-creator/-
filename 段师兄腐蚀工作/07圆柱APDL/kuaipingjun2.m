function baseline=kuaipingjun2(baseline)
% 原始数组：1024×2012 高度场
H_original = baseline; % 替换成你的真实高度矩阵

scale = 4; % 0.25mm → 1mm
[w, l] = size(H_original);

new_w = w / scale;    
new_l = l / scale;    

baseline = zeros(new_w, new_l);

for i = 1:new_w
    for j = 1:new_l
        % 取出 4×4 块
        block = H_original( (i-1)*scale+1 : i*scale , ...
                            (j-1)*scale+1 : j*scale );
        % 块平均（高度场最优降维方法）
        baseline(i,j) = mean(block(:));
    end
end
baseline=(baseline-3).*0.025;
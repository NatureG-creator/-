function H_down=kuaipingjun(a)
w=size(a,1);
l=size(a,2);
n=size(a,3)-1;
depth_map = zeros(w, l);
for i = 1:w
    for j = 1:l
        % 寻找第一个腐蚀层（从表面向下）
        depth = find(squeeze(a(i,j,:)) == 1, 1, 'first');
        if isempty(depth)
            depth_map(i,j) = n + 1; % 如果没有腐蚀层，设置为最大深度
        else
            depth_map(i,j) = depth; % 存储找到的腐蚀层深度
        end
    end
end
% 原始数组：1024×2012 高度场
H_original = depth_map; % 替换成你的真实高度矩阵

scale = 4; % 0.25mm → 1mm
[w, l] = size(H_original);

new_w = w / scale;    
new_l = l / scale;    

H_down = zeros(new_w, new_l);

for i = 1:new_w
    for j = 1:new_l
        % 取出 4×4 块
        block = H_original( (i-1)*scale+1 : i*scale , ...
                            (j-1)*scale+1 : j*scale );
        % 块平均（高度场最优降维方法）
        H_down(i,j) = mean(block(:));
    end
end
H_down=(H_down-3).*0.025;
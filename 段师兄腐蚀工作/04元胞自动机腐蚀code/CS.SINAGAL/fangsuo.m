function B = fangsuo(a, new_w, new_l, new_n)
    [w, l, n] = size(a);
    B = zeros(new_w, new_l, new_n, 'like', a);
    
    for i = 1:new_w
        for j = 1:new_l
            for k = 1:new_n
                % 找到原坐标
                x = round((i-1)/(new_w-1)*(w-1) + 1);
                y = round((j-1)/(new_l-1)*(l-1) + 1);
                z = round((k-1)/(new_n-1)*(n-1) + 1);
                B(i,j,k) = a(x,y,z);
            end
        end
    end
end
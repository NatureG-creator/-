function jisuan_190(Z)
Z_a=Z(:,1:200);
Z_pingtanmian=(max(Z_a(:))-min(Z_a(:)))*0.2+min(Z_a(:))%取20%的分位作为一个平坦面
Z_b=Z(:,round((size(Z,2)-167)/2):round((size(Z,2)-167)/2+167));
Z_fushimian=max(Z_b(:));
junyunfushi=Z_pingtanmian-Z_fushimian;
disp(['均匀腐蚀',num2str(junyunfushi)])
end
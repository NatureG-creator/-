N=1;
clear
%mean_distance需要获取两个平面一个参考面，一个腐蚀面
%将会得到腐蚀面的平均腐蚀深度即
%mean_distance=junzhijisuan('N5-60d-cankao.txt','N5-60d-fushi.txt');
%注意此时我所设置的分辨率是0.3，即一个网格代表0.3mm
%但是所用函数得到的是按照1mm来算的，所以对于sjb要乘以2，shengdu不变
grid_resolution=0.3;    %******
[Z,Z_filled]=shujuguiyi(['C17_100d_z_50_chongxin.txt' ...
    ''],grid_resolution,3);
    % 高斯平滑处理
    sigma = 2.0;
    Z_filled = imgaussfilt(Z_filled, sigma);
 F_filled=Z_filled;
%3jisuan_190(Z)%该函数会统计平坦面20%分位数的高度并和腐蚀面高度相减

params = {'MinProminence', 0.001, 'MinDistance', 15,'Neighborhood', [12,12]};
[shengdu,sjb,zhijin,max_locs, min_locs, boundaries,boundary_coords]=jixiantiqu_3D(-Z_filled,params,0.3,grid_resolution); %******
jicha=max(Z(:))-min(Z(:));
bujunyun=mean(-Z_filled(:)-min(-Z_filled(:)));

disp(['不均匀腐蚀深度',num2str(bujunyun)])
% jsb=log(1./sjb);
% shengdu2=log(shengdu.*1000);
% fenbujianyan(jsb)
% fenbujianyan(shengdu2) 

% 径深比对数
jsb = log(1./sjb);
jsb = jsb(isfinite(jsb));
fenbujianyan(jsb);

% 腐蚀坑深度：mm转为μm后取自然对数
shengdu2 = log(shengdu.*1000);
shengdu2 = shengdu2(isfinite(shengdu2));
fenbujianyan(shengdu2);

% untitled.m
%   → shujuguiyi.m
%   → jixiantiqu_3D.m
%       → fenshuiling_boundry.m
%       → fushikengtiqu.m
%   → fenbujianyan.m
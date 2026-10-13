N=1;
%mean_distance需要获取两个平面一个参考面，一个腐蚀面
%将会得到腐蚀面的平均腐蚀深度即
%mean_distance=junzhijisuan('N5-60d-cankao.txt','N5-60d-fushi.txt');
%注意此时我所设置的分辨率是0.5，即一个网格代表0.5mm
%但是所用函数得到的是按照1mm来算的，所以对于sjb要乘以2，shengdu不变
grid_resolution=0.2;
[Z,Z_filled]=shujuguiyi(['N18-30d-f' ...
    ''],grid_resolution);
    % 高斯平滑处理
    %sigma = 1.5;
    %Z_filled = imgaussfilt(Z_filled, sigma);
params = {'MinProminence', 0.001, 'MinDistance', 25,'Neighborhood', [30,30]};
[shengdu,sjb,zhijin,max_locs, min_locs, boundaries,boundary_coords]=jixiantiqu_3D(-Z_filled,params,0.5,grid_resolution);
jicha=max(Z(:))-min(Z(:));
bujunyun=mean(Z_filled(:)-min(Z_filled(:)));
disp(['高差',num2str(jicha)])
disp(['不均匀腐蚀深度',num2str(bujunyun)])
%取对数
shengdu=log(shengdu.*1000);
jsb=log(1./sjb);
fenbujianyan(jsb)
fenbujianyan(shengdu) 
N=1;
clear
%mean_distance需要获取两个平面一个参考面，一个腐蚀面
%将会得到腐蚀面的平均腐蚀深度即
%mean_distance=junzhijisuan('N5-60d-cankao.txt','N5-60d-fushi.txt');
%注意此时我所设置的分辨率是0.5，即一个网格代表0.5mm
%但是所用函数得到的是按照1mm来算的，所以对于sjb要乘以2，shengdu不变
grid_resolution=0.3;
script_dir = fileparts(mfilename('fullpath'));
if isempty(script_dir)
    script_dir = pwd;
end

% 190 mm 点云用于平均（均匀）腐蚀深度；60 mm 点云用于蚀坑和不均匀腐蚀统计。
file_190 = fullfile(script_dir,'C17-100d-z（190）_corrected.txt');
file_60  = fullfile(script_dir,'C17-100d-z（60）_corrected.txt');

[Z190,Z190_filled]=shujuguiyi(file_190,grid_resolution,3);
[Z,Z_filled]=shujuguiyi(file_60,grid_resolution,3);
    % 高斯平滑处理
    sigma = 1.5;
    Z_filled = imgaussfilt(Z_filled, sigma);
F_filled=Z_filled;

% 由190 mm 点云计算平均（均匀）腐蚀深度。
[junyunfushi, H_flat, H_corroded] = jisuan_190(Z190);

params = {'MinProminence', 0.01, 'MinDistance', 15,'Neighborhood', [12,12]};
[shengdu,sjb,zhijin,max_locs, min_locs, boundaries,boundary_coords]=jixiantiqu_3D(-Z_filled,params,0.3,grid_resolution);
jicha=max(Z(:))-min(Z(:));
bujunyun=mean(-Z_filled(:)-min(-Z_filled(:)));

disp(['不均匀腐蚀深度',num2str(bujunyun)])
jsb=log(1./sjb);
shengdu2=log(shengdu.*1000);
fenbujianyan(jsb)
fenbujianyan(shengdu2)

% ===== 统一保存给元胞自动机使用的六个目标参数 =====
% 点云高度单位按 mm 处理；元胞自动机目标深度统一使用 um。
average_corrosion_depth    = junyunfushi * 1000;
nonuniform_corrosion_depth = bujunyun   * 1000;

[mu_jsb, sigma_jsb]       = normfit(jsb);
[mu_depth, sigma_depth]   = normfit(shengdu2);

% 与 stage_moni.m 中的 data_x~data4 一一对应。
data_x = average_corrosion_depth;
data_y = nonuniform_corrosion_depth;
data1  = mu_jsb;
data2  = mu_depth;
data3  = sigma_jsb;
data4  = sigma_depth;

statistics_file = fullfile(script_dir,'C17_100d_z_statistics.mat');
save(statistics_file, ...
    'average_corrosion_depth','nonuniform_corrosion_depth', ...
    'mu_jsb','mu_depth','sigma_jsb','sigma_depth', ...
    'data_x','data_y','data1','data2','data3','data4', ...
    'junyunfushi','bujunyun','H_flat','H_corroded', ...
    'shengdu','sjb','jsb','shengdu2');

fprintf('\n六个目标参数已保存到：%s\n', statistics_file);
fprintf('data_x = %.6f um\n', data_x);
fprintf('data_y = %.6f um\n', data_y);
fprintf('data1  = %.6f\n', data1);
fprintf('data2  = %.6f\n', data2);
fprintf('data3  = %.6f\n', data3);
fprintf('data4  = %.6f\n', data4);

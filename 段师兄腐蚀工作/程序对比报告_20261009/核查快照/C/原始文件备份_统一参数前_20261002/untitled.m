N=1;
clear
%mean_distance需要获取两个平面一个参考面，一个腐蚀面
%将会得到腐蚀面的平均腐蚀深度即
%mean_distance=junzhijisuan('N5-60d-cankao.txt','N5-60d-fushi.txt');
%注意此时我所设置的分辨率是0.3，即一个网格代表0.3mm
%但是所用函数得到的是按照1mm来算的，所以对于sjb要乘以2，shengdu不变
grid_resolution=0.3;    %******

% 由190 mm点云计算均匀腐蚀深度。
% 190 mm数据必须包含左侧平坦参考区和中间约50 mm腐蚀段。
files_190 = dir('*190*chongxin*');
if isempty(files_190)
    error('未找到190 mm点云文件，请确认当前文件夹中存在包含190和chongxin的文件。');
end
file_190 = files_190(1).name;
[Z190,~] = shujuguiyi(file_190,grid_resolution,3);
[junyunfushi,H_flat,H_corroded] = jisuan_190(Z190);

% 由50 mm点云计算腐蚀坑深度和不均匀腐蚀参数。
[Z,Z_filled]=shujuguiyi(['C17_100d_z_50_chongxin.txt' ...
    ''],grid_resolution,3);
    % 高斯平滑处理
    sigma = 2.0;
    Z_filled = imgaussfilt(Z_filled, sigma);
 F_filled=Z_filled;
%3jisuan_190(Z)%该函数会统计平坦面20%分位数的高度并和腐蚀面高度相减

params = {'MinProminence', 0.001, 'MinDistance', 15,'Neighborhood', [12,12]};
[shengdu,sjb,zhijin,max_locs, min_locs, boundaries,boundary_coords]=jixiantiqu_3D(-Z_filled,params,0.3,grid_resolution); %******

% 每个腐蚀坑的深度
pit_depth_mm = shengdu;
pit_depth_um = shengdu .* 1000;

disp('各腐蚀坑深度（μm）：');
disp(pit_depth_um);

disp(['平均坑深：', num2str(mean(pit_depth_um)), ' μm']);
disp(['最大坑深：', num2str(max(pit_depth_um)), ' μm']);
disp(['最小坑深：', num2str(min(pit_depth_um)), ' μm']);

% 保存全部腐蚀坑结果
result = table((1:numel(shengdu))', pit_depth_mm, pit_depth_um, ...
    'VariableNames', {'Pit_ID','Depth_mm','Depth_um'});
writetable(result, '腐蚀坑深度统计.xlsx');

jicha=max(Z(:))-min(Z(:));
bujunyun=mean(-Z_filled(:)-min(-Z_filled(:)));

disp(['不均匀腐蚀深度：',num2str(bujunyun),' mm']);
disp(['均匀腐蚀深度：',num2str(junyunfushi),' mm']);
disp(['均匀腐蚀深度：',num2str(junyunfushi*1000),' μm']);
disp(['平均腐蚀坑深度：',num2str(mean(pit_depth_mm,'omitnan')),' mm']);
disp(['平均腐蚀坑深度：',num2str(mean(pit_depth_um,'omitnan')),' μm']);
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

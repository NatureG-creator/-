function verify_comparison()
% 仅在合成表面/同一输入点云上做组件对照，不运行会覆盖原结果的主脚本。
base = 'D:/Research Projects/段师兄腐蚀工作';
scan = fullfile(base,'zip','扫描的点云数据_包括点云对齐反转以及所有的腐蚀坑深_径深比数据');
folders = {fullfile(scan,'dianyun_xyz'), fullfile(base,'zip','段瑞飞'), ...
    fullfile(base,'00实验过程（以C17_100d_z为例）')};
report_root = fileparts(mfilename('fullpath'));
old_path = path;
cleanup_path = onCleanup(@() path(old_path)); %#ok<NASGU>
old_visible = get(groot,'defaultFigureVisible');
set(groot,'defaultFigureVisible','off');
cleanup_visible = onCleanup(@() set(groot,'defaultFigureVisible',old_visible)); %#ok<NASGU>
[xx,yy] = meshgrid(1:130,1:70);
surface = 0.02*exp(-((xx-25).^2+(yy-20).^2)/45) + ...
    0.05*exp(-((xx-70).^2+(yy-25).^2)/70) + ...
    0.08*exp(-((xx-105).^2+(yy-48).^2)/55);
params = {'MinProminence',0.001,'MinDistance',15,'Neighborhood',[12,12]};
result = cell(1,3);
for k=1:3
    path(old_path);addpath(folders{k},'-begin');
    clear jixiantiqu_3D fushikengtiqu fenshuiling_boundry step00_corrosion_config
    [h,r,d,peaks,~,boundary,coords] = jixiantiqu_3D(surface,params,0.3,0.3);
    result{k} = struct('h',h,'r',r,'d',d,'peaks',peaks, ...
        'boundary',boundary,'coords',{coords});
    close all;
end
assert(isequaln(result{1},result{2}),'前两个文件夹核心在相同设置下不一致');
assert(isequaln(result{1},result{3}),'第三个文件夹核心在相同有限输入/设置下不一致');
fprintf('PASS: synthetic surface, equal core outputs for A/B/C, %d pits\n',numel(result{1}.h));

% 同一真实点云，比较网格化输出；不改变文件内容，不保存原程序图。
point_file = fullfile(folders{3},'C17_100d_z_50_chongxin.txt');
grid = cell(1,3);
for k=1:3
    path(old_path);addpath(folders{k},'-begin');
    clear shujuguiyi step00_corrosion_config
    if k==2
        [z,f] = shujuguiyi(point_file,0.3);
    else
        [z,f] = shujuguiyi(point_file,0.3,3);
    end
    grid{k} = struct('z',z,'filled',f);
    fprintf('Grid %d shape %d x %d, filled range %.8g .. %.8g\n', ...
        k,size(f,1),size(f,2),min(f(:)),max(f(:)));
    close all;
end
assert(isequaln(grid{1},grid{3}),'A/C相同输入和设置网格化不一致');
fprintf('PASS: real C17 point cloud preprocessing A == C at matched settings\n');

% 两个均匀深度函数中央区域的列索引确实相差1列，构造可辨别矩阵验证。
ztest = repmat(-(1:650)/1000,4,1);
path(old_path);addpath(fullfile(folders{3},'02点云处理'),'-begin');
clear jisuan_190
[uniform_old,~,~] = jisuan_190(ztest);
path(old_path);addpath(folders{3},'-begin');
clear jisuan_190 step00_corrosion_config
[uniform_new,h_flat,h_corroded] = jisuan_190(ztest);
assert(abs((uniform_new-uniform_old)-0.001)<1e-12);
assert(isscalar(h_flat)&&isscalar(h_corroded));
fprintf('PASS: central window moves 1 column; uniform delta %.6g mm\n',uniform_new-uniform_old);
fprintf('PASS: H_flat/H_corroded are scalars, not surface matrices\n');
save(fullfile(report_root,'组件对照验证.mat'),'result','grid', ...
    'uniform_old','uniform_new','h_flat','h_corroded','point_file');
end

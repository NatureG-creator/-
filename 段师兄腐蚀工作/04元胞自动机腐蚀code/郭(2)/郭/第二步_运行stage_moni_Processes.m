% 第二步：运行 stage_moni，并强制使用本文件夹代码和 Processes 并行池
% 运行前请先执行：
% run('第一步_修复Processes并行池.m')
%
% 说明：
% 这个入口脚本用于避免 MATLAB 调用其他文件夹中的同名 fitness.m/GA.m/CA.m。

clc;
this_dir = fileparts(mfilename('fullpath'));
cd(this_dir);
addpath(this_dir, '-begin');

% 清除缓存，确保 stage_moni 调用的是当前文件夹的函数。
clear fitness GA CA stage_moni;
clear functions;

fprintf('=== 第二步：运行 stage_moni ===\n');
fprintf('当前工作目录: %s\n', pwd);
fprintf('当前调用 stage_moni: %s\n', which('stage_moni'));
fprintf('当前调用 fitness: %s\n', which('fitness'));
fprintf('当前调用 GA: %s\n', which('GA'));
fprintf('当前调用 CA: %s\n', which('CA'));

% 如果没有并行池，则先启动 8 个 Processes workers。
% 如果第一步已经成功留下了 8 workers 池，这里会直接复用。
pool = gcp('nocreate');
if isempty(pool)
    fprintf('当前没有并行池，先启动 8 个 Processes workers。\n');
    myCluster = parcluster('Processes');
    myCluster.JobStorageLocation = 'C:\MatlabParallelJobs\corrosion_processes';
    pool = parpool(myCluster, 8);
else
    fprintf('当前已有并行池: %s, workers=%d\n', pool.Cluster.Profile, pool.NumWorkers);
    if ~strcmpi(pool.Cluster.Profile, 'Processes')
        error('当前并行池不是 Processes。请先执行 delete(gcp(''nocreate''))，再重新运行第一步。');
    end
end

stage_moni;

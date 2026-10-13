% 第一步：修复并测试 MATLAB Processes 并行池
% 运行方式：在 MATLAB 当前文件夹切到本目录后执行：
% run('第一步_修复Processes并行池.m')
%
% 作用：
% 1. 强制把当前郭(2)\郭目录放到 MATLAB 路径最前面，避免调用其他文件夹里的同名 fitness.m。
% 2. 关闭残留并行池和 MATLABWorker.exe 残留进程。
% 3. 把 Processes 的 JobStorageLocation 改到纯英文短路径，减少中文路径/长路径导致的 worker 崩溃。
% 4. 先测试 1 个 worker，再测试 2 个 workers；如果失败，打印完整错误原因。

clc;
fprintf('=== 第一步：开始修复 Processes 并行池 ===\n');

% 当前脚本所在目录，也就是郭(2)\郭目录。
this_dir = fileparts(mfilename('fullpath'));
cd(this_dir);
addpath(this_dir, '-begin');

% 清除同名函数缓存，避免 MATLAB 继续使用旧的 fitness/GA/CA。
clear fitness GA CA stage_moni;
clear functions;

fprintf('当前工作目录: %s\n', pwd);
fprintf('当前 fitness 调用顺序:\n');
which fitness -all
fprintf('当前 GA 调用顺序:\n');
which GA -all
fprintf('当前 CA 调用顺序:\n');
which CA -all
fprintf('当前 stage_moni 调用顺序:\n');
which stage_moni -all

% 1. 关闭当前残留并行池。
pool = gcp('nocreate');
if ~isempty(pool)
    fprintf('关闭已有并行池，类型: %s, workers=%d\n', pool.Cluster.Profile, pool.NumWorkers);
    delete(pool);
end

% 2. 强制结束残留 MATLAB worker 进程。
% 说明：如果上一次 Processes worker 崩溃，残留进程可能阻止新池启动。
fprintf('尝试清理残留 MATLABWorker.exe 进程...\n');
[~, kill_msg] = system('taskkill /F /IM MATLABWorker.exe');
fprintf('%s\n', kill_msg);

% 3. 读取并配置 Processes 集群。
fprintf('读取 Processes 集群配置...\n');
myCluster = parcluster('Processes');

% 4. 使用纯英文短路径作为 JobStorageLocation。
job_dir = 'C:\MatlabParallelJobs\corrosion_processes';
if ~exist(job_dir, 'dir')
    mkdir(job_dir);
end
fprintf('设置 JobStorageLocation: %s\n', job_dir);
myCluster.JobStorageLocation = job_dir;

% 5. 删除旧崩溃作业。
try
    fprintf('清理旧 Jobs，数量: %d\n', numel(myCluster.Jobs));
    delete(myCluster.Jobs);
catch ME
    fprintf(2, '旧 Jobs 清理警告: %s\n', ME.message);
end

% 6. 保存配置。
try
    saveProfile(myCluster);
    fprintf('Processes 配置已保存。\n');
catch ME
    fprintf(2, 'saveProfile 警告: %s\n', ME.message);
end

% 7. 先用 1 个 worker 测试。
try
    fprintf('测试启动 1 个 Processes worker...\n');
    pool = parpool(myCluster, 1);
    fprintf('1 worker 启动成功。\n');

    fprintf('测试 parfor 基础计算...\n');
    test_result = zeros(1, 4);
    parfor i = 1:4
        test_result(i) = i^2;
    end
    disp(test_result);

    delete(pool);
catch ME
    fprintf(2, '\n=== 1 worker 测试失败：说明 MATLAB Processes 环境本身仍有问题 ===\n');
    fprintf(2, '错误信息: %s\n', ME.message);
    fprintf(2, '错误标识: %s\n', ME.identifier);
    fprintf(2, 'JobStorageLocation: %s\n', myCluster.JobStorageLocation);
    for k = 1:numel(ME.stack)
        fprintf(2, '调用栈 %d: %s 第 %d 行\n', k, ME.stack(k).name, ME.stack(k).line);
    end
    rethrow(ME);
end

% 8. 再用 2 个 workers 测试，这是当前腐蚀代码推荐起步值。
try
    fprintf('测试启动 2 个 Processes workers...\n');
    pool = parpool(myCluster, 2);
    fprintf('2 workers 启动成功。\n');

    fprintf('测试 parfor 多 worker 计算...\n');
    test_result = zeros(1, 8);
    parfor i = 1:8
        test_result(i) = i^2 + 1;
    end
    disp(test_result);

    fprintf('=== Processes 并行池修复完成，可以运行 stage_moni ===\n');
catch ME
    fprintf(2, '\n=== 2 workers 测试失败：1 worker 可用但多进程 worker 数过高或环境不稳定 ===\n');
    fprintf(2, '错误信息: %s\n', ME.message);
    fprintf(2, '错误标识: %s\n', ME.identifier);
    fprintf(2, 'JobStorageLocation: %s\n', myCluster.JobStorageLocation);
    for k = 1:numel(ME.stack)
        fprintf(2, '调用栈 %d: %s 第 %d 行\n', k, ME.stack(k).name, ME.stack(k).line);
    end
    rethrow(ME);
end

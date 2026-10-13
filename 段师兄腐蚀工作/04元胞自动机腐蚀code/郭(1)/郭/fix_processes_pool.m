% 修复 Processes 并行池环境。
% 运行顺序：
%   1) 在 MATLAB 命令行运行：fix_processes_pool
%   2) 若显示 Processes 并行池启动成功，再运行：stage_moni
%
% 关键修复点：
%   - 清理旧的崩溃作业；
%   - 把 JobStorageLocation 改到纯英文短路径，避免中文路径/括号路径影响 worker；
%   - 先用 4 个 worker 测试，稳定后再调大。

fprintf('========== Processes 并行池修复开始 ==========\n');

workers = 4; % 可调参数：先用 2 或 4，稳定后可改成 6、8。
job_dir = 'C:\matlab_parallel_jobs';

if ~exist(job_dir, 'dir')
    mkdir(job_dir);
end

try
    pool = gcp('nocreate');
    if ~isempty(pool)
        fprintf('关闭当前并行池: %s, worker 数: %d\n', pool.Type, pool.NumWorkers);
        delete(pool);
    end
catch ME
    fprintf(2, '关闭当前并行池失败: %s\n', ME.message);
end

try
    c = parcluster('Processes');
    fprintf('当前 Processes JobStorageLocation: %s\n', c.JobStorageLocation);
    if ~isempty(c.Jobs)
        fprintf('删除旧作业数量: %d\n', numel(c.Jobs));
        delete(c.Jobs);
    end
    c.JobStorageLocation = job_dir;
    saveProfile(c);
    fprintf('新的 Processes JobStorageLocation: %s\n', c.JobStorageLocation);
catch ME
    fprintf(2, '配置 Processes 集群失败: %s\n', ME.message);
end

try
    fprintf('尝试启动 Processes 并行池，worker 数: %d\n', workers);
    pool = parpool('Processes', workers);
    fprintf('Processes 并行池启动成功，worker 数: %d\n', pool.NumWorkers);
catch ME
    fprintf(2, 'Processes 并行池启动失败。\n');
    fprintf(2, '%s\n', getReport(ME, 'extended', 'hyperlinks', 'off'));
end

fprintf('========== Processes 并行池修复结束 ==========\n');


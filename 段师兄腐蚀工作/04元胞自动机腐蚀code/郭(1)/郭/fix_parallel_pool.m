% 修复/清理 MATLAB 并行池环境。
% 用途：
% 1. 删除 Processes 配置文件下保留的崩溃作业；
% 2. 关闭当前并行池；
% 3. 优先启动 threads 线程池，避免 Processes worker 崩溃。

fprintf('========== 并行池清理开始 ==========\n');

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
    myCluster = parcluster('Processes');
    if ~isempty(myCluster.Jobs)
        fprintf('删除 Processes 配置文件中的旧作业数量: %d\n', numel(myCluster.Jobs));
        delete(myCluster.Jobs);
    else
        fprintf('Processes 配置文件中没有旧作业。\n');
    end
catch ME
    fprintf(2, '清理 Processes 旧作业失败: %s\n', ME.message);
end

try
    pool = parpool('threads');
    fprintf('threads 并行池启动成功，worker 数: %d\n', pool.NumWorkers);
catch ME
    fprintf(2, 'threads 并行池启动失败: %s\n', ME.message);
    fprintf(2, '后续 fitness.m 会自动改用串行 for 兜底。\n');
end

fprintf('========== 并行池清理结束 ==========\n');


% 测试 Processes 并行池是否能正常执行 parfor。
% 先运行 fix_processes_pool，再运行本文件。

fprintf('========== Processes parfor 测试开始 ==========\n');

pool = gcp('nocreate');
if isempty(pool) || ~strcmpi(pool.Type, 'processes')
    fprintf('当前没有 Processes 池，尝试启动 4 个 worker。\n');
    pool = parpool('Processes', 4);
else
    fprintf('当前 Processes 池已存在，worker 数: %d\n', pool.NumWorkers);
end

n = 16;
y = zeros(1, n);
parfor i = 1:n
    y(i) = i * i;
end

expected = (1:n).^2;
if isequal(y, expected)
    fprintf('Processes parfor 测试通过。\n');
else
    error('Processes parfor 测试失败：结果不一致。');
end

fprintf('========== Processes parfor 测试结束 ==========\n');


% 安全运行入口：用于运行 stage_moni.m
% 作用：
% 1. 不主动调用图形系统，避免 MATLAB R2026a 的 HGApp/Home 服务崩溃；
% 2. 固定随机种子，方便复现实验；
% 3. 出错时打印完整报错堆栈，方便定位。

clearvars
clc

script_dir = fileparts(mfilename('fullpath'));
if isempty(script_dir)
    script_dir = pwd;
end
cd(script_dir);

rng(1, 'twister');

try
    fprintf('========== 安全入口启动 stage_moni：%s ==========\n', datestr(now));
    run('stage_moni.m');
catch ME
    fprintf(2, '\n!!!!!! run_stage_moni_safe 捕获到错误 !!!!!!\n');
    fprintf(2, '%s\n', getReport(ME, 'extended', 'hyperlinks', 'off'));
    rethrow(ME);
end

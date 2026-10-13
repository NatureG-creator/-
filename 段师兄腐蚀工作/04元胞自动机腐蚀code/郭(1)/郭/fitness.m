function [sd_OBJV, sd_a, sd_d,sd_cl] = fitness(XY, NIND, data, data_x, a_jisuan, F, n, w, l, space, d_jisuan, stage_number, CL_concentration_jisuan,gen)
    % 输入参数：
    %   XY: 种群的参数矩阵，每行表示一个个体的参数
    %   NIND: 种群规模
    %   data: 真实数据，用于计算适应度
    %   data_x: 其他相关数据或参数
    %
    % 输出参数：
    %   sd_OBJV: 每个个体的适应度值
    %   sd_a: 每个个体对应的元胞自动机状态
    %   sd_F: 每个个体的迭代次数
    % 函数实现代码
    % 初始化输出变量
    sd_OBJV = zeros(NIND,size(data,2)); % 存储每个个体的适应度
    sd_a = cell(NIND, 1); % 存储每个个体的元胞自动机状态
    sd_d = cell(NIND, 1);
    sd_cl = cell(NIND, 1);
    % 定义初始边界条件
    % 遍历每个个体   
    if iscell(a_jisuan)
        disp('是元胞数组')
    end
        fprintf('[阶段 %d | 第 %d 代] 开始评估 %d 个个体...\n', stage_number, gen, NIND);
        tic_fitness = tic;

        % 强制使用 Processes 进程池。
        % 注意：Processes 池会启动多个独立 MATLAB worker，若环境中有崩溃残留、
        % 中文 JobStorageLocation 或 worker 数过多，容易出现 worker 访问冲突。
        % 运行 stage_moni 前建议先执行 fix_processes_pool。
        use_parallel = false;
        try
            processes_workers = 4; % 可调参数：Processes worker 数，建议先从 2 或 4 开始，稳定后再加大。
            pool = gcp('nocreate');
            if isempty(pool) || ~strcmpi(pool.Type, 'processes')
                if ~isempty(pool)
                    delete(pool);
                end
                pool = parpool('Processes', processes_workers);
            end
            use_parallel = true;
            fprintf('[阶段 %d | 第 %d 代] 使用 Processes 并行池评估个体，worker 数: %d。\n', stage_number, gen, pool.NumWorkers);
        catch ME
            fprintf(2, '[阶段 %d | 第 %d 代] Processes 并行池不可用，改用串行 for。原因: %s\n', stage_number, gen, ME.message);
        end

        if use_parallel
            progress_queue = parallel.pool.DataQueue;
            afterEach(progress_queue, @(idx) fprintf('[阶段 %d | 第 %d 代] 个体 %d/%d 完成\n', stage_number, gen, idx, NIND));
            parfor i = 1:NIND
                % 提取当前个体的参数
                % 调用元胞自动机函数进行模拟
                [CS, a , d ,CL_concentration] = CA(XY(i, :), F,a_jisuan,data,data_x,n,w,l,space,d_jisuan,stage_number,CL_concentration_jisuan);
                % 计算适应度（目标函数值）
                sd_OBJV(i,:) = round(abs(CS),2); % 示例：适应度为真实数据与模拟结果的差值
                sd_a{i} = a; % 存储元胞自动机状态
                sd_d{i} = d; % 存储元胞自动机状态
                sd_cl{i} = CL_concentration;
                send(progress_queue, i);
            end
        else
            for i = 1:NIND
                % 串行兜底：不依赖 Parallel Computing Toolbox worker，稳定性最高。
                [CS, a , d ,CL_concentration] = CA(XY(i, :), F,a_jisuan,data,data_x,n,w,l,space,d_jisuan,stage_number,CL_concentration_jisuan);
                sd_OBJV(i,:) = round(abs(CS),2);
                sd_a{i} = a;
                sd_d{i} = d;
                sd_cl{i} = CL_concentration;
                fprintf('[阶段 %d | 第 %d 代] 个体 %d/%d 完成\n', stage_number, gen, i, NIND);
            end
        end
        fprintf('[阶段 %d | 第 %d 代] 全部个体评估完成，用时 %.2f 秒。\n', stage_number, gen, toc(tic_fitness));
    end
    

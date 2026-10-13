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
        pool = gcp('nocreate');
        parfor i = 1:NIND
            % 提取当前个体的参数
            % 调用元胞自动机函数进行模拟
            [CS, a , d ,CL_concentration] = CA(XY(i, :), F,a_jisuan,data,data_x,n,w,l,space,d_jisuan,stage_number,CL_concentration_jisuan);
        % 计算适应度（目标函数值）
            sd_OBJV(i,:) = round(abs(CS),2); % 示例：适应度为真实数据与模拟结果的差值
            sd_a{i} = a; % 存储元胞自动机状态
            sd_d{i} = d; % 存储元胞自动机状态
            sd_cl{i} = CL_concentration;
            
        end
        if mod(gen,50)==0
        % 关闭并行池释放内存
        delete(pool);
        % 压缩内存碎片
        end
    end
    
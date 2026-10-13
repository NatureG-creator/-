function [perfect_result,perfect_parameter,perfect_a,perfect_d,perfect_cl] = GA(w,l,n,data_x,data,a_input,F,stage_number,space,d_input,cl_input)
% perfect_result-最小误差
% perfect_parameter-最优参数
% perfect_a—元胞状态

%遗传算法参数设置
NIND=100; %种群规模
LIND=10;%参数个数
bits_per_param = 11; % 每个参数的二进制位数
lb =[0   0  0    5   1 0   1  0     0  1 ];% 参数下界
ub =[0.3 1 0.005 35 35 0.1 35 0.5 0.5 15];% 参数上界
%参数分别为氧气浓度、金属腐 蚀概率、产物腐蚀概率
SLIND=5;%被选择个数
MAXGEN=10; %最大迭代数为MAXGEN-1
base_px=0.5; %交叉概率
base_pm=0.5; %变异概率
decay_rate=0.2;%自适应变异交叉率

%小生境参数
sigma_share=0.3;%相似度阈值

fprintf('\n========== GA 开始：阶段 %d ==========\n', stage_number);
fprintf('网格尺寸: %d x %d x %d, 最大 CA 迭代 F = %d, GA 最大代数 = %d\n', w, l, n, F, MAXGEN-1);
fprintf('目标数据: [%s]\n', num2str(data, '%.4f '));

%预赋值
%初始元胞都是一致的
%最上层为腐蚀空间
%下方全为金属空间
%设置平均适应度
OBJV=zeros(NIND,1);

% 初始化种群
% 采用拉丁超立方生成初始种群
Chrom=latin_begin(NIND,LIND,bits_per_param);

%代计数器
gen=1;
tic;
% 开始循环
while gen<MAXGEN
    fprintf('\n[阶段 %d] GA 第 %d/%d 代开始...\n', stage_number, gen, MAXGEN-1);
    tic_gen = tic;
    
    %计算种群的目标函数值
    XY=er2shi(Chrom,lb,ub,bits_per_param);

    %在while内动态计算遗传系数
    current_px = max(0.6, min(0.95, base_px * exp(-decay_rate*(gen/MAXGEN))));
    current_pm = max(0.01, min(0.3, base_pm + (0.3 - base_pm)*(gen/MAXGEN)));

    %元胞数组的返回程序
    if stage_number == 1
        %将个体初始化
        %初始时输入a
           a_begin=ones(w, l, n+1);
           a_begin(:,:,1)=0;
           a_jisuan=a_begin;
           d_jisuan=ones(size(a_begin))*3;
           CL_concentration_jisuan = zeros(w, l); % 氯离子浓度
    else
        %将返回的perfect_a作为
        a_jisuan=a_input;
        d_jisuan=d_input;
        CL_concentration_jisuan=cl_input;
    end

    %开始进行适应度计算
    %带有正负的objv
    [objv,sd_a,sd_d,sd_cl]=fitness(XY,NIND,data,data_x,a_jisuan,F,n,w,l,space,d_jisuan,stage_number,CL_concentration_jisuan,gen);
    %objv=[Average_depth bj_depth mean(jsb) mean(shengdu) sigma1 sigma2;
    %不采纳蚀坑径深比标准差，将腐蚀坑深度的均值和标准差统一
    objv(:,5)=[];
    %objv=[Average_depth bj_depth mean(jsb) mean(shengdu) sigma1 sigma2;
    %蚀坑深度均值：标准差=6/4，5/5，4/6
    objv(:,4)=0.6*objv(:,4)+0.4*objv(:,5);
    objv(:,5)=[];
    
    %总体均值进一步分布
    

    %将输出对应所有个体达到对质量损失率时所对应的适应度大小，元胞空间a分布情况，迭代次数对应情况
    % 适应度评估
    % 适应度只取平均适应度OBJV大小以完成选择,objv是NIND*2的数组
    for i=1:NIND
        OBJV(i)=0.1*objv(i,1)+0.3*objv(i,2)+0.2*objv(i,3)+0.4*objv(i,4);
    end
    [gen_best_objv, gen_best_idx] = min(OBJV);
    fprintf('[阶段 %d] 第 %d 代当前最优个体: %d, 加权误差: %.6f, 分项误差: [%s]\n', ...
        stage_number, gen, gen_best_idx, gen_best_objv, num2str(objv(gen_best_idx,:), '%.4f '));
    %小生境适应度共享
    %在适应度计算后添加共享函数增加相似个体惩罚机制
    %第一步进行适应度处理适应度越高个体越优秀
    Fitness = 1 ./ (OBJV + eps);  % eps 防止除零

    % 计算共享适应度
    % 计算全距离矩阵 (NIND x NIND)
    dist_matrix = pdist2(XY, XY); % 计算种群中每个个体之间的欧几里得距离，生成一个大小为NIND*NIND的距离矩阵。
    dist_matrix(logical(eye(NIND))) = 0; % 生成一个对角线为true的逻辑矩阵，用于将距离矩阵的对角线元素（即个体自身的距离）设置为   0  。

    % 计算共享系数
    %share_terms表示每个个体与其他个体的相似性（共享系数），值越接近1表示越相似
    share_terms = max(1 - dist_matrix/sigma_share, 0);
    %表示每个个体的共享系数之和，用于后续的适应度共享计算
    sum_shared = sum(share_terms, 2) + 1; 

    % 计算共享适应度
    shared_Fitness = Fitness ./ sum_shared;
   
    % 更新适应度为共享后的值
    Fitness = shared_Fitness;


    %将每一代族群的适应度存入
    if gen==1
        [~,I_min_OBJV]=min(OBJV);
        perfect_result=objv(I_min_OBJV,:);
        perfect_parameter=XY(I_min_OBJV,:);
        perfect_a=sd_a{I_min_OBJV};
        perfect_d=sd_d{I_min_OBJV};
        perfect_cl=sd_cl{I_min_OBJV};
        shiyingdu=0.1*objv(I_min_OBJV,1)+0.3*objv(I_min_OBJV,2)+0.2*objv(I_min_OBJV,3)+0.4*objv(I_min_OBJV,4);
    else
        [~,I_min_OBJV]=min(OBJV);
        if sum(perfect_result)>sum(objv(I_min_OBJV,:))
           perfect_result=objv(I_min_OBJV,:);
           perfect_parameter=XY(I_min_OBJV,:);
           perfect_a=sd_a{I_min_OBJV};
           perfect_d=sd_d{I_min_OBJV};
           perfect_cl=sd_cl{I_min_OBJV};
           %shiyingdu=0.1*objv(I_min_OBJV,1)+0.3*objv(I_min_OBJV,2)+0.2*objv(I_min_OBJV,3)+0.4*objv(I_min_OBJV,4);
           shiyingdu=0.1*objv(I_min_OBJV,1)+0.3*objv(I_min_OBJV,2)+0.2*objv(I_min_OBJV,3)+0.4*objv(I_min_OBJV,4);
        end
    end
 
    %判定适应度大小若存在适应度误差小于5%则输出
    if sum(perfect_result)<=0.01
    fprintf('=== 最优解 ===\n');
    fprintf('代际: %d, 个体索引: %d\n', gen, I_min_OBJV);
    fprintf('参数: [%s]\n', num2str(perfect_parameter, '%.4f '));
    fprintf('适应度总体值: %s\n', num2str(shiyingdu, '%.4f '));
    fprintf('误差: %.4f%% (平均腐蚀深度), %.4f%% (jf)\n, %.4f%% (sjb)\n, %.4f%% (sd)\n', perfect_result(1)*100, perfect_result(2)*100,perfect_result(3)*100,perfect_result(4)*100);
    break
    end

    [~, I] = sort(Fitness);  
    % 适应度越大越好
    % 适应度排序按列从到小到大的顺序排列
    % 方便置换后续的较差父代个体
    % 以进行后续的替代最差个体工作

    %选择操作
    %自适应竞标赛规模

    %根据种群多样性动态调整
    diversity = std(Fitness); % 适应度方差衡量多样性
    tournament_size = max(2, round(5 * diversity));
    I_S=tournament_selection(Fitness,SLIND,tournament_size);
    SelCh_1=Chrom(I_S,:);

    % 交叉操作
    SelCh_2 = jiaocha(SelCh_1, current_px, LIND);
    % 变异操作
    SelCh_3 = mut(SelCh_2, current_pm);
    % 重插入操作
    % 以变异后的个体代替父代中最差个体
    % 最差个体即I_tidai
    I_worst=I(1:size(SelCh_3,1));
    Chrom(I_worst,:)=SelCh_3;
    fprintf('[阶段 %d] GA 第 %d 代结束，用时 %.2f 秒。历史最佳加权误差: %.6f\n', ...
        stage_number, gen, toc(tic_gen), shiyingdu);
    % 更新代计数器
    gen = gen + 1;
    if gen==MAXGEN
    % 输出结果
    fprintf('=== 最优解 ===\n');
    fprintf('代际: %d, 个体索引: %d\n', gen, I_min_OBJV);
    fprintf('参数: [%s]\n', num2str(perfect_parameter, '%.4f '));
    fprintf('误差: %.4f%% (平均腐蚀深度), %.4f%% (bjf)\n, %.4f%% (sjb)\n, %.4f%% (sd)\n', perfect_result(1)*100, perfect_result(2)*100, perfect_result(3)*100, perfect_result(4)*100);
    end
end
toc;
%注释：
%OBJV_sd=cell(MAXGEND,1)每一行储存的是每一代际的objv
%objv是由fitness输出的元胞数组代表着每一代所有种群的适应度objv=cell(1, NIND);
%适应度组成：objv{i} = round(abs(CS),2);其中CS=[max_depth;min_depth].*0.01-data';
%调用适应度格式是OBJV_sd{}{}()
%注释：
%XY_sd=cell(MAXGEN,1);
%该元胞数组储存着每代个体的参数组成XY
%XY的组成则为SIZE=[NIND LIND]的数组
%引用XY的话即
%XY_sd{gen}(n,:)
%注释
%XY_F=cell(MAXGEN,1);
%该元胞数组储存着每代个所有个体的最终迭代次数
%每个元胞组成为zeros(1, NIND);
%a_sd=cell(MAXGEN,1);
%该元胞数组储存着每代个所有个体的最终元胞状态
%每个元胞组成为cell(1, NIND);


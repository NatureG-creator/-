%% 基础参数
% Codex demo: use a small grid to demonstrate CS calculation quickly.
rng(1);
F = 80;
w = 200;
l = 80;
n = 50;
space = 25;
stage_number = 1;

% ===================== 用户自主设置 =====================
use_parallel = false;     % 并行开关：true=开启并行，false=串行
parallel_workers = 6;     % 并行核数`
load_external_data = false;% 外部输入：true=使用外部a/d/CL，false=默认初始化

% ==========================================================

% 完美参数
XY = [0.05, 0.3, 0.001, 20, 10, 0.02, 10, 0.1, 0.05, 5];
data_x =456;
data_y = 100;
data1 = 1.86;
data2 = 5.74;
data3 = 0.63;
data4 = 0.27;
data = [data_x, data_y, data1, data2, data3, data4];

%% ===================== 均匀分块 =====================
num_blocks = 5;
[block_coords] = split_uniform_10_blocks(w, l);

%% ===================== 初始化：外部输入 或 默认 =====================
if load_external_data
    fprintf('✅ 使用外部输入 a / d / CL_concentration\n');
else
    fprintf('✅ 使用默认初始化\n');
    a = zeros(w, l, n+1);
    a(:,:,2:end) = 1;
    d = 3 * ones(w, l, n+1);
    CL_concentration = zeros(w, l);
    
    s_p = randi(w*l*n, 1, round(w*l*n*XY(6)));
    full_d = ones(w,l,n)*3;
    full_d(s_p) = 1;
    d(:,:,2:end) = full_d;
    clear full_d s_p;
end

%% ===================== 分块 =====================
blocks = struct();
for b = 1:num_blocks
    x1 = block_coords(b,1); x2 = block_coords(b,2);
    y1 = block_coords(b,3); y2 = block_coords(b,4);
    blocks(b).a = a(x1:x2, y1:y2, :);
    blocks(b).d = d(x1:x2, y1:y2, :);
    blocks(b).CL = CL_concentration(x1:x2, y1:y2);
end
clear a d CL_concentration;

%% ===================== 并行 =====================
if use_parallel
    pool = gcp('nocreate');
    if isempty(pool)
        parpool('local', parallel_workers);
    end
    fprintf('✅ %d核并行已启动\n', parallel_workers);
else
    fprintf('✅ 串行模式\n');
end

%% ===================== 迭代主循环 =====================
N = F;
p_uniform_base = XY(1);
p_passive_base = XY(2);
p_break = XY(3);
CL_threshold = XY(4);
alpha_corrosion = XY(5);
alpha_passive = 0.8;
alpha_p_break = XY(7);
p_h = XY(8);
p_v = XY(9);
p_o = XY(10);
K0 = 0;
beta = 1;

fprintf('=========================================\n');
fprintf('           腐蚀模拟开始迭代\n');
fprintf('=========================================\n');
start_time = tic;

for k = 1:N
    if use_parallel
        parfor b = 1:num_blocks
            blocks(b) = block_process(blocks(b), k, n, ...
                p_uniform_base, p_passive_base, p_break, CL_threshold,...
                alpha_corrosion, alpha_passive, alpha_p_break,...
                p_h, p_v, p_o, K0, beta, stage_number);
        end
    else
        for b = 1:num_blocks
            blocks(b) = block_process(blocks(b), k, n, ...
                p_uniform_base, p_passive_base, p_break, CL_threshold,...
                alpha_corrosion, alpha_passive, alpha_p_break,...
                p_h, p_v, p_o, K0, beta, stage_number);
        end
    end

    % 终止条件
    total_metal = 0;
    for b = 1:num_blocks
        total_metal = total_metal + sum(sum(sum(blocks(b).a == 1)));
    end
    quality_loss = (w*l*n - total_metal) / (w*l*n);
    Average_depth = quality_loss * n * space;

    % 进度
    progress = k / N * 100;
    elapsed_time = toc(start_time);
    est_remain = (elapsed_time/k*(N-k))*(k>1);
    
    fprintf('迭代: %4d/%4d | 进度: %5.1f%% | 已用: %4.1fs | 剩余预估: %4.1fs | 平均腐蚀深度: %.2f\n',...
        k,N,progress,elapsed_time,est_remain,Average_depth);

    if data_x - Average_depth <= 0
        fprintf('\n已达到目标深度，提前终止！\n');
        break;
    end
end

fprintf('\n迭代完成！总耗时：%.2f 秒\n', toc(start_time));

%% ===================== 合并完整 a + d + CL =====================
full_a = zeros(w,l,n+1);
full_d = zeros(w,l,n+1);
full_CL = zeros(w,l);

for b = 1:num_blocks
    x1 = block_coords(b,1); x2 = block_coords(b,2);
    y1 = block_coords(b,3); y2 = block_coords(b,4);
    full_a(x1:x2,y1:y2,:) = blocks(b).a;
    full_d(x1:x2,y1:y2,:) = blocks(b).d;
    full_CL(x1:x2,y1:y2) = blocks(b).CL;
end

a = full_a;
d = full_d;
CL_concentration = full_CL;
clear blocks full_a full_d full_CL;

%% ===================== 后续分析 =====================
size_chuangkou = 11;
[baseline, ~,~,depth_map] = moving_avg_3D(a, size_chuangkou, w, l, n);
jicha = max(baseline(:)) - min(baseline(:));
bj_depth = mean(depth_map(:) - min(depth_map(:))) * space;

if jicha < 3
    yuzhi = 0.3; scale = 15;
elseif jicha < 5
    yuzhi = 0.4; scale = 20;
else
    yuzhi = 0.5; scale = 25;
end

params = {'MinProminence',0.05,'MinDistance',15,'Neighborhood',[scale,scale]};
[shengdu, sjb] = jixiantiqu_3D(baseline,n,params,yuzhi);
shengdu = log(shengdu.*space);
sjb = sjb./10;
jsb = log(1./sjb);
sigma1 = std(jsb, 0);
sigma2 = std(shengdu, 0);
CS = ([Average_depth bj_depth mean(jsb) mean(shengdu) sigma1 sigma2]-data)./data;

simulated = [Average_depth bj_depth mean(jsb) mean(shengdu) sigma1 sigma2];
fprintf('\n================ CS 演示结果 ================\n');
disp('simulated = [Average_depth bj_depth mean(jsb) mean(shengdu) sigma1 sigma2]');
disp(simulated);
disp('data = [data_x data_y data1 data2 data3 data4]');
disp(data);
disp('CS = (simulated - data) ./ data');
disp(CS);
disp('abs(CS) * 100 = 每一项的百分比误差(%)');
disp(abs(CS) * 100);

%% ===================== 分块函数 =====================
function coords = split_uniform_10_blocks(W, L)
    num = 5;
    coords = zeros(num,4);
    w_list = linspace(1,W+1,num+1);
    for i = 1:num
        x1 = round(w_list(i));
        x2 = round(w_list(i+1))-1;
        coords(i,:) = [x1,x2,1,L];
    end
end

%% ===================== 块处理函数（无报错版） =====================
function block = block_process(block, k, n, ...
    p_uniform_base, p_passive_base, p_break, CL_threshold,...
    alpha_corrosion, alpha_passive, alpha_p_break,...
    p_h, p_v, p_o, K0, beta, stage_number)

a = block.a;
d = block.d;
CL_concentration = block.CL;
wb = size(a,1);
lb = size(a,2);

[~,~] = tuweipolie(a, wb, lb, p_o, 30, n);
boundary = detect_boundry_3D(a, n);

if ~isempty(boundary)
    boundary_idx = sub2ind(size(a), boundary(:,1), boundary(:,2), boundary(:,3));
    boundary_xy_idx = sub2ind(size(CL_concentration), boundary(:,1), boundary(:,2));
    a_vals = a(boundary_idx);
    valid_mask = a_vals ~= 0;
    
    boundary = boundary(valid_mask,:);
    boundary_idx = boundary_idx(valid_mask);
    boundary_xy_idx = boundary_xy_idx(valid_mask);
    a_vals = a_vals(valid_mask);
    d_vals = d(boundary_idx);
    CL_vals = CL_concentration(boundary_xy_idx);
    
    CL_factor = CL_vals / CL_threshold;
    decay_factor = ones(size(a_vals));
    if k <= K0
        decay_factor = 1 + (beta-1)*(K0-k+1)/K0;
    end
    
    p_uniform = p_uniform_base * (1 + alpha_corrosion*CL_factor) .* decay_factor;
    p_passive = p_passive_base * (1 - alpha_passive*CL_factor);
    rand_vals = rand(size(a_vals));
    
    metal_mask = a_vals == 1;
    corrode_mask = metal_mask & rand_vals < p_uniform;
    d_mask = corrode_mask & d_vals > 1;
    a_mask = corrode_mask & d_vals == 1;
    d(boundary_idx(d_mask)) = d(boundary_idx(d_mask)) - 1;
    a(boundary_idx(a_mask)) = 0;
    
    passive_mask = metal_mask & ~corrode_mask & rand_vals < p_passive;
    a(boundary_idx(passive_mask)) = 2;
    
    passive_break_mask = (a_vals == 2) & (d_vals == 1);
    p_break_cl = zeros(size(passive_break_mask));
    valid_idx = find(passive_break_mask);
    
    if ~isempty(valid_idx)
        cf = CL_factor(valid_idx);
        if stage_number == 1
            p_break_cl(valid_idx) = p_break * (1 + alpha_p_break*cf).^2;
        else
            p_break_cl(valid_idx) = p_break * (1 + alpha_p_break*cf);
        end
    end
    
    break_mask = passive_break_mask & rand(size(passive_break_mask)) < p_break_cl;
    if any(break_mask)
        a(boundary_idx(break_mask)) = 0;
        CL_concentration(boundary_xy_idx(break_mask)) = ...
            min(CL_concentration(boundary_xy_idx(break_mask))+1, CL_threshold);
        
        for i = find(break_mask)'
            [a, CL_concentration] = spread_corrosion2(...
                boundary(i,1),boundary(i,2),boundary(i,3),...
                a,p_h,p_v,n,CL_concentration,CL_threshold);
        end
    end
    CL_concentration(CL_concentration >= CL_threshold) = 0;
end

block.a = a;
block.d = d;
block.CL = CL_concentration;
end

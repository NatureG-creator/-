function [shengdu,sjb,zhijin] = ...
    fushikengtiqu(data, pits, max_loc, grid_resolution, cfg)
if nargin < 5 || isempty(cfg)
    cfg = step00_corrosion_config();
end
if nargin < 4 || isempty(grid_resolution)
    grid_resolution = cfg.preprocessing.grid_resolution_mm;
end
    %输入量：data - 二维矩阵表示的三维高度数据 ，就是前面 `shujuguiyi` 输出的 `Z` 或 `Z_filled`；
    %输入量：pits：个坑的边界三维坐标，元胞数组，每个元胞存`[x坐标, y坐标, 高程]`，分水岭算法跑完的结果；
    %输入量：max_loc——每个坑的极大值点坐标，格式为`[行号, 列号]`；
    %输入量：grid_resolution——网格分辨率，即单个像素对应的实际物理长度，用于把像素数转换成真实尺寸；
    %输出参数：shengdu：每个坑的深度；
    %输出参数：sjb：每个坑的面积；
    %输出参数：zhijin：每个坑的等效直径。
    
num_pits=size(pits,1);
%锈坑数据统计，先统计总共有多少个分割出来的坑，提前建好空数组，分别存放每个坑的深度、X 方向宽度、Y 方向宽度、面积、直径，后面循环逐个赋值。
xiukeng_depth=zeros(size(pits,1),1);
xiukeng_bianjieX=zeros(size(pits,1),1);
xiukeng_bianjieY=zeros(size(pits,1),1);
xiukeng_sjb=zeros(size(pits,1),1);
zhijin=zeros(size(pits,1),1);


% data=-Z_filled时，最小值对应腐蚀表面的最高点（图中的“顶点”）
switch cfg.pit_detection.depth_reference_mode
    case 'global_minimum'
        surface_top = min(data(:),[],'omitnan');
    otherwise
        error('不支持的坑深参考面模式: %s', ...
            cfg.pit_detection.depth_reference_mode);
end

%逐个处理每个腐蚀坑。
for k = 1:num_pits

%提取锈坑深度
% 检查当前腐蚀坑边界
if isempty(pits{k})
    warning('第%d个腐蚀坑没有有效边界，已跳过。',k);
    xiukeng_depth(k) = NaN;
    xiukeng_sjb(k) = NaN;
    zhijin(k) = NaN;
    continue;
end

% 极大值点的行、列坐标
row = max_loc(k,1);
col = max_loc(k,2);

% 检查索引范围
if row < 1 || row > size(data,1) || ...
   col < 1 || col > size(data,2)
    warning('第%d个腐蚀坑的极值点索引超出范围。',k);
    xiukeng_depth(k) = NaN;
    xiukeng_sjb(k) = NaN;
    zhijin(k) = NaN;
    continue;
end

% data=-Z_filled时，极大值点对应腐蚀坑底
pit_bottom = data(row,col);

% 图中定义的锈坑相对深度：腐蚀表面顶点到坑底
xiukeng_depth(k) = max(0,pit_bottom-surface_top);

% 腐蚀坑在X、Y方向的尺寸
xiukeng_bianjieX(k) = ...
    range(pits{k}(:,1))*grid_resolution;

xiukeng_bianjieY(k) = ...
    range(pits{k}(:,2))*grid_resolution;

% 用X、Y方向平均跨度近似表示腐蚀坑直径
switch cfg.pit_detection.diameter_mode
    case 'mean_xy_span'
        zhijin(k) = ...
            (xiukeng_bianjieX(k)+xiukeng_bianjieY(k))/2;
    otherwise
        error('不支持的坑径计算模式: %s', ...
            cfg.pit_detection.diameter_mode);
end

% 深径比：坑深/坑径
if zhijin(k) > 0
    xiukeng_sjb(k) = xiukeng_depth(k)/zhijin(k);
else
    xiukeng_sjb(k) = NaN;
end


     % 4. 计算当前pit的参考面（最小值）
    %xiukeng_cankaomian=min(pits{k}(:,3));
    % xiukeng_cankaomian=min(data(:));
    % xiukeng_depth(k)= (data(sub2ind(size(data), max_loc(k,1), max_loc(k,2)))-xiukeng_cankaomian);
    % xiukeng_bianjieX(k) = range(pits{k}(:,1)).*grid_resolution; 
    % xiukeng_bianjieY(k) = range(pits{k}(:,2)).*grid_resolution;
    % xiukeng_sjb(k)=(xiukeng_depth(k))/((xiukeng_bianjieX(k)+xiukeng_bianjieY(k))*0.5);
    % zhijin(k)=(xiukeng_bianjieX(k)+xiukeng_bianjieY(k))*0.5;
end

shengdu=xiukeng_depth;
sjb=xiukeng_sjb;
end

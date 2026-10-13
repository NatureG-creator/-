function [Z,Z_filled] = shujuguiyi(fill, grid_resolution, xiuzhenghang)

% 读取txt文件（替换为你的实际文件名）
data = readtable(fill);

% 提取x、y、z坐标（假设数据列顺序为x,y,z）
x = data{:, 1};         %取出 `data` 全部行、第 1 列的数据，赋值给变量 `x`
y = data{:, 2};         %取出 `data` 全部行、第 2 列的数据，赋值给 `y`
z = -data{:, 3};        %取出 `data` 全部行、第 3 列的数据，整体取负，赋值给 `z`

%% 步骤1：拟合原始数据的倾斜平面（同前）
%`变量(:)` 的作用：不管原来 x/y/z 是行向量还是列向量，强制转为列向量。
%`\` 是 MATLAB左除运算符，用来求解超定方程组的最小二乘解。
A = [x(:) y(:) ones(size(x))];
coeff = A \ z(:);       % 最小二乘拟合平面方程：z = a*x + b*y + c

%% 步骤2：旋转并平移平面至xy平面齐平
% 1. 读取离散点坐标 `x,y,z`
% 2. 最小二乘拟合基准平面 \(z=ax+by+c\)
% 3. 求平面法向量
% 4. 计算旋转轴、旋转角，构造罗德里格斯旋转矩阵
% 5. 对点云整体旋转，把倾斜平面放平
% 6. 得到校正后的 z，用于后续网格化
normal_original = [coeff(1), coeff(2), -1];         %平面方程 z=ax+by+c，改写为：ax+by - z + c =0，平面的法向量：n_0=(a,b,-1)，也就是`normal_original`。
normal_original = normal_original / norm(normal_original);      %`norm()`：求向量模长。除以模长：单位法向量。
normal_target = [0, 0, 1];          %目标法向量：竖直向上，对应水平面（z 轴垂直平面）。我们要把原始倾斜平面旋转到这个水平位置。
%`cross(A,B)`：向量叉乘。
% 叉乘结果 = 同时垂直于两个法向量的向量，也就是**旋转轴**。
% 几何含义：绕这个轴旋转，就能把原始法向量转到目标法向量。
% `dot`：向量点乘。
% 点乘公式：n_0* n_t =  |n_0|* |n_t|*cos\theta
% 两个都是单位向量，所以 \(\theta=\arccos(\boldsymbol n_0\cdot\boldsymbol n_t)\)，得到**需要旋转的角度（弧度）**。
rotation_axis = cross(normal_original, normal_target);
rotation_axis = rotation_axis / norm(rotation_axis);
rotation_angle = acos(dot(normal_original, normal_target));
  
u = rotation_axis;
theta = rotation_angle;
K = [0, -u(3), u(2); u(3), 0, -u(1); -u(2), u(1), 0];
R = eye(3) + sin(theta)*K + (1 - cos(theta))*(K*K);

points = [x(:), y(:), z(:)];
rotated_points = points * R';           % 修正倾斜后的点，对点云所有点做旋转变换，原始倾斜平面被旋转成水平面。

z_rotated = rotated_points(:, 3);       %**已经剔除了整体平面倾斜，只剩下局部高低起伏。

%% 步骤3：通过主成分分析（PCA）确定网格主方向
% 平面方位校正（本段代码）：用 PCA 找到 xy 平面内点云的长轴方向，计算与 x 轴的夹角
% → 后续一般会绕 z 轴旋转，把点云长轴对齐到 x 轴，让整个点云完全 “摆正”，方便后续网格化、计算尺寸或特征参数。
% 提取修正后的x、y坐标（z已齐平，仅处理xy平面）
xy_points = rotated_points(:, 1:2);

% 计算协方差矩阵（反映数据分布方向），反映了数据在 x、y 方向的离散程度，以及两个方向的相关性。
cov_matrix = cov(xy_points);

% 主成分分析：特征向量对应主方向（第一特征向量为长轴方向）
[V, ~] = eig(cov_matrix);  % V的列是特征向量（按特征值升序排列）
major_axis = V(:, 2);  % 第二列对应最大特征值（长轴方向）

% 计算当前长轴与X轴的夹角（弧度）
angle_current = atan2(major_axis(2), major_axis(1));  % 长轴方向角

%% 步骤4：计算旋转角度并对齐坐标轴
% 目标角度为0（长轴与X轴平行）
angle_rotate = -angle_current;      % 需旋转的角度（负号为顺时针旋转）

% 构建二维旋转矩阵（绕Z轴旋转），对列向量形式的坐标点做旋转变换
R_2d = [cos(angle_rotate), -sin(angle_rotate);
        sin(angle_rotate), cos(angle_rotate)];

% 对xy坐标应用旋转（保持z坐标不变）
rotated_xy = (xy_points - mean(xy_points)) * R_2d';     % 先中心化再旋转，计算点云在 x、y 方向的均值，也就是点云的几何中心坐标，减去均值：把整个点云平移，让它的中心与坐标原点重合。
                                                        %旋转矩阵默认是**绕坐标原点旋转**。如果不先中心化，直接旋转，点云会绕全局原点 “公转”，
                                                        % 整体位置会发生偏移；先中心化再旋转，实现的是“绕点云自身中心旋转”，只转朝向不挪位置。
rotated_xy = rotated_xy + mean(xy_points);              % 恢复原中心位置（可选）

%% 步骤5：生成边缘对齐坐标轴的网格数据
% 提取旋转后的x、y、z坐标
x_aligned = rotated_xy(:, 1);
y_aligned = rotated_xy(:, 2);
z_aligned = rotated_points(:, 3);  % z坐标已平移至最小值为0

% 生成网格范围（基于对齐后的x和y的最小/最大值）
% `x_grid` / `y_grid`：根据点云的 x、y 坐标范围，按输入的 `grid_resolution`（网格分辨率：0.3mm，看untitled.m）生成等间距的一维网格线。
% `meshgrid`：把一维的 x、y 网格线扩展成二维坐标矩阵 `X` 和 `Y`，尺寸为 `M行 × N列`（M = y 网格点数量，N = x 网格点数量），每个网格点对应唯一的 (x,y) 坐标。
x_grid = min(x_aligned):grid_resolution:max(x_aligned);                     %起始值 : 步长 : 终止值
y_grid = min(y_aligned):grid_resolution:max(y_aligned);                     %起始值 : 步长 : 终止值
[X, Y] = meshgrid(x_grid, y_grid);%二维坐标矩阵

% 插值生成对齐后的网格数据
%griddata` 是 MATLAB 内置的散乱点插值函数，把离散的 (x,y,z) 点插值到刚才生成的规则网格 (X,Y) 上，输出网格高程矩阵 `Z`。
% 超出原始点云覆盖范围的网格位置会返回 `NaN`（空值 / 空洞）。
% 默认使用线性插值，兼顾平滑度和保真度。
Z = griddata(x_aligned, y_aligned, z_aligned, X, Y);

% `fillmissing` 用于填充矩阵中的 `NaN` 空洞：
% `'nearest'`：最近邻填充法，用距离最近的有效值填充空值，边缘区域也适用。
% `dim=1`：按**列**方向填充（上下方向，每一列内部从上到下补全）。
% `dim=2`：按**行**方向填充（左右方向，每一行内部从左到右补全）。
% 先列后行做两次填充，确保网格内所有空洞都被填满，得到完整的网格 `Z_filled`。
% 对应你函数的两个输出：`Z` 是原始插值带空洞的网格，`Z_filled` 是填充完成的完整网格。
Z_filled = fillmissing(Z, 'nearest', 1);            % 1表示按列填充
Z_filled = fillmissing(Z_filled, 'nearest', 2);     % 2表示按行填充

%删除边缘坏点
Z(1:xiuzhenghang,:)=[];
Z(end-xiuzhenghang:end,:)=[];
Z(:,1:xiuzhenghang)=[];
Z(:,end-xiuzhenghang:end)=[];
Z_filled(1:xiuzhenghang,:)=[];
Z_filled(end-xiuzhenghang:end,:)=[];
Z_filled(:,1:xiuzhenghang)=[];
Z_filled(:,end-xiuzhenghang:end)=[];
X=X(xiuzhenghang+1:end-(xiuzhenghang+1),xiuzhenghang+1:end-(xiuzhenghang+1));
Y=Y(xiuzhenghang+1:end-(xiuzhenghang+1),xiuzhenghang+1:end-(xiuzhenghang+1));

% ===================== 修正：将Z值最低点严格设为0 =====================
Z_max = max(Z(:));          % 计算Z的全局最小值（修正原错误的max）/取全局最大值（最高点）
Z(:) = Z - Z_max;           % 平移数据，使最低点=0/最高点平移至 0，其余全为负数
% =========================================================================

%Z=Z(:,2:70);
%Z_filled=Z_filled(:,1:70);

%% 步骤6：可视化和验证（删除网格线+15号字体+所有原有设置）
figure;%新建一个绘图窗口
% 彻底关闭绘图区背景网格
grid off;                  
% 关闭坐标轴刻度线（可选，若需保留刻度仅删网格可注释）
% box off;

% 绘制曲面并隐藏曲面网格线
s1 = surf(X, Y, Z);         %以 X、Y 为平面坐标，Z 为高程，绘制三维曲面。
s1.EdgeColor = 'none';     % 隐藏曲面本身的网格线
%s1.FaceColor = 'interp';   % 按z值插值着色
%s1.FaceLighting = 'none';  % 关闭曲面光照/阴影效果
%lighting none;             % 全局关闭光照（彻底消除阴影）
shading interp;            % 平滑着色

% ===================== 核心修改：统一设置15号字体 =====================
%  `set(gca, ...)`：设置坐标轴刻度数字的字体；
%  `xlabel/ylabel/zlabel`：设置三个坐标轴的名称标签；
%  `colorbar`：设置右侧色标尺的刻度字体。
set(gca, 'FontSize', 15, 'FontName', 'Times New Roman');  % 坐标轴刻度、标签字体设为15号
xlabel('X ', 'FontSize', 15, 'FontName', 'Times New Roman');
ylabel('Y ', 'FontSize', 15, 'FontName', 'Times New Roman');
zlabel('Z', 'FontSize', 15, 'FontName', 'Times New Roman');
colorbar('FontSize', 15, 'FontName', 'Times New Roman');  % 色标字体设为15号
% =========================================================================

% ===================== 保留原有设置 =====================
clim([-0.5 0]);            % 强制标尺范围-0.5~0
colormap(turbo);           % 颜色图改为turbo风格
% =========================================================================

axis tight;
view(3);                   % 3D视角（原注释写"俯视"是错误的，view(2)才是俯视）
end
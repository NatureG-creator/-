function [Z,Z_filled]=shujuguiyi(fill,grid_resolution,xiuzhenghang)
% 读取txt文件（替换为你的实际文件名）
data = readtable(fill);

% 提取x、y、z坐标（假设数据列顺序为x,y,z）
x = data{:, 1};
y = data{:, 2};
z = -data{:, 3};

%% 步骤1：拟合原始数据的倾斜平面（同前）
A = [x(:) y(:) ones(size(x))];
coeff = A \ z(:);  % 平面方程：z = a*x + b*y + c

%% 步骤2：旋转并平移平面至xy平面齐平
normal_original = [coeff(1), coeff(2), -1];
normal_original = normal_original / norm(normal_original);
normal_target = [0, 0, 1];
rotation_axis = cross(normal_original, normal_target);
rotation_axis = rotation_axis / norm(rotation_axis);
rotation_angle = acos(dot(normal_original, normal_target));

u = rotation_axis;
theta = rotation_angle;
K = [0, -u(3), u(2); u(3), 0, -u(1); -u(2), u(1), 0];
R = eye(3) + sin(theta)*K + (1 - cos(theta))*(K*K);

points = [x(:), y(:), z(:)];
rotated_points = points * R';  % 修正倾斜后的点

z_rotated = rotated_points(:, 3);

%% 步骤3：通过主成分分析（PCA）确定网格主方向
% 提取修正后的x、y坐标（z已齐平，仅处理xy平面）
xy_points = rotated_points(:, 1:2);

% 计算协方差矩阵（反映数据分布方向）
cov_matrix = cov(xy_points);

% 主成分分析：特征向量对应主方向（第一特征向量为长轴方向）
[V, ~] = eig(cov_matrix);  % V的列是特征向量（按特征值升序排列）
major_axis = V(:, 2);  % 第二列对应最大特征值（长轴方向）

% 计算当前长轴与X轴的夹角（弧度）
angle_current = atan2(major_axis(2), major_axis(1));  % 长轴方向角

%% 步骤4：计算旋转角度并对齐坐标轴
% 目标角度为0（长轴与X轴平行）
angle_rotate = -angle_current;  % 需旋转的角度（负号为顺时针旋转）

% 构建二维旋转矩阵（绕Z轴旋转）
R_2d = [cos(angle_rotate), -sin(angle_rotate);
        sin(angle_rotate), cos(angle_rotate)];

% 对xy坐标应用旋转（保持z坐标不变）
rotated_xy = (xy_points - mean(xy_points)) * R_2d';  % 先中心化再旋转
rotated_xy = rotated_xy + mean(xy_points);  % 恢复原中心位置（可选）

%% 步骤5：生成边缘对齐坐标轴的网格数据
% 提取旋转后的x、y、z坐标
x_aligned = rotated_xy(:, 1);
y_aligned = rotated_xy(:, 2);
z_aligned = rotated_points(:, 3);  % z坐标已平移至最小值为0

% 生成网格范围（基于对齐后的x和y的最小/最大值）
x_grid = min(x_aligned):grid_resolution:max(x_aligned);
y_grid = min(y_aligned):grid_resolution:max(y_aligned);
[X, Y] = meshgrid(x_grid, y_grid);

% 插值生成对齐后的网格数据
Z = griddata(x_aligned, y_aligned, z_aligned, X, Y);

Z_filled = fillmissing(Z, 'nearest', 1);  % 1表示按列填充
Z_filled = fillmissing(Z_filled, 'nearest', 2);

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
Z_min = max(Z(:));          % 计算Z的全局最小值（修正原错误的max）
Z(:) = Z - Z_min;           % 平移数据，使最低点=0
% =========================================================================

%Z=Z(:,2:70);
%Z_filled=Z_filled(:,1:70);

%% 步骤6：可视化和验证（删除网格线+15号字体+所有原有设置）
figure;
% 彻底关闭绘图区背景网格
grid off;                  
% 关闭坐标轴刻度线（可选，若需保留刻度仅删网格可注释）
% box off;

% 绘制曲面并隐藏曲面网格线
s1 = surf(X, Y, Z);
s1.EdgeColor = 'none';     % 隐藏曲面本身的网格线
%s1.FaceColor = 'interp';   % 按z值插值着色
%s1.FaceLighting = 'none';  % 关闭曲面光照/阴影效果
%lighting none;             % 全局关闭光照（彻底消除阴影）
shading interp;            % 平滑着色

% ===================== 核心修改：统一设置15号字体 =====================
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
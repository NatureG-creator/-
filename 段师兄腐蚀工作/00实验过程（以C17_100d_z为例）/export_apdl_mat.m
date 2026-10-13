function output_file = export_apdl_mat(config)
%EXPORT_APDL_MAT 直接从 MATLAB 导出 APDL 可读取的表面 MAT 文件。
%
% 直接运行本文件时，修改下方默认配置；也可以传入结构体 config 做批量调用。
% 输出只包含一个二维 double 变量：Z_filled 或 F_filled；不重采样。
%
% measured 模式：读取已有二维 Z_filled/F_filled，并原尺寸原值保存。
% simulation 模式：读取包含 perfect_a 或 a_output 的三维 CA 状态，
%                  按 z 方向寻找第一层未腐蚀金属并转换为正腐蚀深度(mm)。

if nargin < 1 || isempty(config)
    config = default_config();
end
config = normalize_config(config);

if ~isfile(config.input_mat)
    error('export:InputMissing', '输入 MAT 文件不存在：%s', config.input_mat);
end

source = load(config.input_mat);
switch config.mode
    case 'measured'
        [source_variable, matrix] = read_measured_matrix(source, config.input_mat, config.input_variable);
        if isempty(config.output_variable)
            output_variable = source_variable;
        else
            output_variable = config.output_variable;
        end
    case 'simulation'
        state = read_simulation_state(source, config.input_mat);
        matrix = surface_from_ca_state(state, config.space_z_um);
        if isempty(config.output_variable)
            output_variable = 'F_filled';
        else
            output_variable = config.output_variable;
        end
    otherwise
        error('export:Mode', 'mode 只能是 measured 或 simulation。');
end

validate_variable_name(output_variable);
matrix = validate_matrix(matrix, config.input_mat);

output_file = config.output_mat;
output_folder = fileparts(output_file);
if ~isempty(output_folder) && ~isfolder(output_folder)
    mkdir(output_folder);
end

% 动态变量名保存，确保输出 MAT 中只有 APDL 需要的变量。
S = struct();
S.(output_variable) = double(matrix);
save(output_file, '-struct', 'S', '-v7');

fprintf('已生成 MATLAB MAT：%s\n', output_file);
fprintf('变量：%s；尺寸：%d x %d；范围：[%.6g, %.6g]\n', ...
    output_variable, size(matrix, 1), size(matrix, 2), min(matrix(:)), max(matrix(:)));
end

function config = default_config()
% 直接点击 Run 时只需修改这几个参数。
config = struct();
config.mode = 'measured';                 % 'measured' 或 'simulation'
config.input_mat = 'D:\Research Projects\段师兄腐蚀工作\00实验过程（以C17_100d_z为例）\正向深度结果_20261012_142529_060\正向腐蚀深度与指标.mat';         % 输入 MAT 路径
config.output_mat = 'D:\Research Projects\段师兄腐蚀工作\00实验过程（以C17_100d_z为例）\结果文件\Fanmian_apdl.mat';   % 输出 MAT 路径
config.output_variable = '';              % 空值=自动沿用/默认；也可写 Z_filled/F_filled
config.input_variable = '';               % measured 空值=自动识别
config.space_z_um = 25;                   % simulation 的 Z 向元胞尺寸(um)
end

function config = normalize_config(config)
required = {'mode', 'input_mat', 'output_mat', 'output_variable', 'space_z_um'};
for i = 1:numel(required)
    if ~isfield(config, required{i})
        error('export:Config', 'config 缺少字段：%s', required{i});
    end
end
if ~isfield(config, 'input_variable') || isempty(config.input_variable)
    config.input_variable = '';
end
config.mode = lower(char(config.mode));
config.input_mat = char(config.input_mat);
config.output_mat = char(config.output_mat);
config.output_variable = char(config.output_variable);
config.input_variable = char(config.input_variable);
if ~isscalar(config.space_z_um) || ~isfinite(config.space_z_um) || config.space_z_um <= 0
    error('export:SpaceZ', 'space_z_um 必须是正的有限标量。');
end
end

function [name, matrix] = read_measured_matrix(source, input_mat, requested)
if ~isempty(requested)
    name = char(requested);
    if ~isfield(source, name)
        error('export:VariableMissing', '%s 中不存在变量 %s。', input_mat, name);
    end
    matrix = source.(name);
    return;
end
for candidate = {'Z_filled', 'F_filled'}
    if isfield(source, candidate{1})
        name = candidate{1};
        matrix = source.(name);
        return;
    end
end
error('export:VariableMissing', '%s 未找到 Z_filled 或 F_filled。', input_mat);
end

function state = read_simulation_state(source, input_mat)
for candidate = {'perfect_a', 'a_output'}
    if isfield(source, candidate{1})
        state = source.(candidate{1});
        return;
    end
end
error('export:StateMissing', ...
    '%s 未找到 perfect_a 或 a_output；MATLAB 不能直接读取 NPZ。', input_mat);
end

function matrix = surface_from_ca_state(state, space_z_um)
state = double(state);
if ndims(state) ~= 3 || any(size(state) < 1) || any(~isfinite(state(:)))
    error('export:StateShape', 'CA 状态必须是有限的三维数值数组。');
end
[nrow, ncol, nz] = size(state);
has_metal = false(nrow, ncol);
depth_layer = ones(nrow, ncol) * (nz - 1);
for k = 1:nz
    mask = ~has_metal & (state(:, :, k) == 1);
    depth_layer(mask) = k - 1;  % 与 Python 的 zero-based 层索引一致
    has_metal(mask) = true;
end
matrix = depth_layer * double(space_z_um) / 1000;
end

function matrix = validate_matrix(matrix, input_mat)
if ~isnumeric(matrix) || ~ismatrix(matrix) || isempty(matrix) || any(~isfinite(matrix(:)))
    error('export:Matrix', '%s 中的表面必须是非空、有限的二维数值矩阵。', input_mat);
end
matrix = double(matrix);
end

function validate_variable_name(name)
if ~ismember(name, {'Z_filled', 'F_filled'})
    error('export:OutputVariable', 'output_variable 只能是 Z_filled 或 F_filled。');
end
end

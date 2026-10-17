function summary = matlab_apdl_convert(input_file, output_dir, input_variable, dx_mm, dy_mm, x_start_mm, y_start_mm)
%MATLAB_APDL_CONVERT Convert a 2-D surface matrix to APDL X/Y/Z vectors.
% The matrix is preserved exactly. meshgrid plus MATLAB (:), matching the
% existing matlab_apdl.m rule and the coordinate parser used by the website.
if nargin < 3 || isempty(input_variable), input_variable = ''; end
if nargin < 4 || isempty(dx_mm), dx_mm = 0.3; end
if nargin < 5 || isempty(dy_mm), dy_mm = 0.3; end
if nargin < 6 || isempty(x_start_mm), x_start_mm = 0; end
if nargin < 7 || isempty(y_start_mm), y_start_mm = 0; end
input_file = char(input_file);
output_dir = char(output_dir);
if ~isfile(input_file), error('matlab_apdl_convert:InputMissing', '输入文件不存在：%s', input_file); end
if ~isscalar(dx_mm) || ~isfinite(dx_mm) || dx_mm <= 0, error('matlab_apdl_convert:Spacing', 'dx_mm 必须是正的有限数值。'); end
if ~isscalar(dy_mm) || ~isfinite(dy_mm) || dy_mm <= 0, error('matlab_apdl_convert:Spacing', 'dy_mm 必须是正的有限数值。'); end
if ~isscalar(x_start_mm) || ~isfinite(x_start_mm) || ~isscalar(y_start_mm) || ~isfinite(y_start_mm)
    error('matlab_apdl_convert:Origin', 'X/Y 起点必须是有限数值。');
end
if ~isfolder(output_dir), mkdir(output_dir); end

[~, ~, ext] = fileparts(input_file);
ext = lower(ext);
if strcmp(ext, '.mat')
    source = load(input_file);
    candidates = {'Z_filled', 'F_filled'};
    if isempty(input_variable)
        found = candidates(cellfun(@(name) isfield(source, name) && isnumeric(source.(name)) && ismatrix(source.(name)), candidates));
        if numel(found) ~= 1, error('matlab_apdl_convert:Variable', 'MAT 需要明确选择唯一表面变量 Z_filled 或 F_filled。'); end
        input_variable = found{1};
    end
    if ~isfield(source, input_variable), error('matlab_apdl_convert:Variable', 'MAT 中没有变量 %s。', input_variable); end
    grid_matrix = source.(input_variable);
elseif ismember(ext, {'.csv', '.txt', '.tsv'})
    if strcmp(ext, '.csv'), grid_matrix = readmatrix(input_file, 'Delimiter', ',');
    elseif strcmp(ext, '.tsv'), grid_matrix = readmatrix(input_file, 'Delimiter', 'tab');
    else, grid_matrix = readmatrix(input_file); end
    input_variable = '';
else
    error('matlab_apdl_convert:Extension', '仅支持 MAT、CSV、TXT、TSV 二维矩阵。');
end
if ~isnumeric(grid_matrix) || ~ismatrix(grid_matrix) || min(size(grid_matrix)) < 2 || any(~isfinite(grid_matrix(:)))
    error('matlab_apdl_convert:Matrix', '输入必须是至少 2×2 的有限二维数值矩阵。');
end
grid_matrix = double(grid_matrix);
[ny, nx] = size(grid_matrix);
[X, Y] = meshgrid(x_start_mm + (0:nx-1) * dx_mm, y_start_mm + (0:ny-1) * dy_mm);
write_vector(fullfile(output_dir, 'DIANYUN_X.txt'), X(:));
write_vector(fullfile(output_dir, 'DIANYUN_Y.txt'), Y(:));
write_vector(fullfile(output_dir, 'DIANYUN_Z.txt'), grid_matrix(:));
summary = struct('shape', [ny, nx], 'point_count', numel(grid_matrix), 'variable', input_variable, ...
    'dx_mm', dx_mm, 'dy_mm', dy_mm, 'origin_x_mm', x_start_mm, 'origin_y_mm', y_start_mm);
fprintf('MATLAB APDL 坐标已生成：%d × %d，%d 点。\n', ny, nx, numel(grid_matrix));
end

function write_vector(filename, values)
fid = fopen(filename, 'w');
if fid < 0, error('matlab_apdl_convert:Output', '无法写入输出文件：%s', filename); end
cleanup = onCleanup(@() fclose(fid));
fprintf(fid, '%.12g\n', values);
end

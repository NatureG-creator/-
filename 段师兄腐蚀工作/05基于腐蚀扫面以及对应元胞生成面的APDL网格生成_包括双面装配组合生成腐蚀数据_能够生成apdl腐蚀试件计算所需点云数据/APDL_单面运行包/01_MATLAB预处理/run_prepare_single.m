%% 单面 MATLAB 预处理入口：加载一个 Z_filled 表面并生成 APDL 坐标文件
% 默认数据：../00_输入数据/C/C17_100D/60/Z60193.mat
% 输出目录：../02_坐标文件

thisFile = mfilename('fullpath');
scriptDir = fileparts(thisFile);
packageDir = fileparts(scriptDir);
inputDir = fullfile(packageDir, '00_输入数据', 'C', 'C17_100D', '60');
outputDir = fullfile(packageDir, '02_坐标文件');
preprocessScript = fullfile(scriptDir, 'matlab_apdl_danmian.m');

zFile = fullfile(inputDir, 'Z60193.mat');
if ~isfile(zFile)
    error('默认输入文件不存在：%s', zFile);
end

zData = load(zFile);
if ~isfield(zData, 'Z_filled')
    error('单面输入 MAT 文件必须包含变量 Z_filled。');
end
Z_filled = zData.Z_filled;
if ~isnumeric(Z_filled) || ~ismatrix(Z_filled) || isempty(Z_filled) || any(~isfinite(Z_filled(:)))
    error('Z_filled 必须是非空、有限的二维数值矩阵。');
end

if ~isfolder(outputDir)
    mkdir(outputDir);
end
oldDir = pwd;
cleanupObj = onCleanup(@() cd(oldDir)); %#ok<NASGU>
cd(outputDir);
run(preprocessScript);

expectedFiles = {'DIANYUN_X.txt', 'DIANYUN_Y.txt', 'DIANYUN_Z.txt'};
for k = 1:numel(expectedFiles)
    if ~isfile(fullfile(outputDir, expectedFiles{k}))
        error('单面预处理未生成文件：%s', expectedFiles{k});
    end
end
fprintf('单面预处理完成。尺寸：%d×%d；坐标文件已写入：%s\n', ...
    size(Z_filled, 1), size(Z_filled, 2), outputDir);

%% 推荐运行入口：加载一组正反面 MAT 数据并生成 APDL 坐标文件
% 默认数据：C17_100D/60，Z_filled 和 F_filled 均为 60×193
% 输出目录：../02_坐标文件

thisFile = mfilename('fullpath');
scriptDir = fileparts(thisFile);
packageDir = fileparts(scriptDir);
inputDir = fullfile(packageDir, '00_输入数据', 'C', 'C17_100D', '60');
outputDir = fullfile(packageDir, '02_坐标文件');
preprocessScript = fullfile(scriptDir, 'matlab_apdl_shuangmian_recommended.m');

zFile = fullfile(inputDir, 'Z60193.mat');
fFile = fullfile(inputDir, 'F.mat');
if ~isfile(zFile) || ~isfile(fFile)
    error('默认输入文件不存在：%s 或 %s', zFile, fFile);
end

zData = load(zFile);
fData = load(fFile);
if ~isfield(zData, 'Z_filled') || ~isfield(fData, 'F_filled')
    error('输入 MAT 文件必须分别包含变量 Z_filled 和 F_filled。');
end
Z_filled = zData.Z_filled;
F_filled = fData.F_filled;
if ~isequal(size(Z_filled), [60, 193]) || ~isequal(size(F_filled), [60, 193])
    error('默认数据尺寸必须为 60×193，当前为 %s 和 %s。', ...
        mat2str(size(Z_filled)), mat2str(size(F_filled)));
end

if ~isfolder(outputDir)
    mkdir(outputDir);
end
oldDir = pwd;
cleanupObj = onCleanup(@() cd(oldDir));
cd(outputDir);
run(preprocessScript);

expectedFiles = {
    'DIANYUN_FRONT_X.txt'
    'DIANYUN_FRONT_Y.txt'
    'DIANYUN_FRONT_Z.txt'
    'DIANYUN_BACK_X.txt'
    'DIANYUN_BACK_Y.txt'
    'DIANYUN_BACK_Z.txt'
};
for k = 1:numel(expectedFiles)
    if ~isfile(fullfile(outputDir, expectedFiles{k}))
        error('预处理未生成文件：%s', expectedFiles{k});
    end
end
fprintf('预处理完成。坐标文件已写入：%s\n', outputDir);

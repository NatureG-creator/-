% 第一步：复现截图对应的 Q355 原始输入版本，不使用后期替换的质量损失率。
root = fileparts(mfilename('fullpath'));
addpath(root);
run_original_fits('Q355');

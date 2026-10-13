% 第二步（独立可选）：用 drf.mat 第1组做 Q370NH 同方法拟合。
% 这是新增材料计算，不是把截图中的 Q355 公式改名为 Q370NH。
root = fileparts(mfilename('fullpath'));
addpath(root);
run_original_fits('Q370NH');

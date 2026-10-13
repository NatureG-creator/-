% 第1步仅转到原MATLAB目录运行，不在代码6重新处理扫描点云。
original_matlab_dir='D:/Research Projects/段师兄腐蚀工作/00实验过程（以C17_100d_z为例）';
assert(isfile(fullfile(original_matlab_dir,'export_original_ca_target.m')), ...
    '原目录缺少目标导出接口。');
addpath(original_matlab_dir,'-begin'); % 原算法优先，避免同名函数串目录。
clear step00_corrosion_config; % 清除persistent旧配置，修改后读最新设置。
run(fullfile(original_matlab_dir,'untitled.m')); % 原算法链保留；用190共同零面正深度统计、绘图和导出。
if ca_target_export.calibration_ready
    disp('第1步完成。接下来在Python编辑器运行step02_ca_ga.py。');
else
    warning('mainflow:TargetNotReady','原数据已导出，但参考深度/样本未通过检查；先读导出说明，不能进入CA-GA校准。');
end

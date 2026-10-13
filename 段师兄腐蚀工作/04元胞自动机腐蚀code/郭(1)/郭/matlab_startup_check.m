% 启动自检：只验证 MATLAB 能进入当前文件夹并写文件，不运行 GA。
clearvars
script_dir = fileparts(mfilename('fullpath'));
cd(script_dir);
output_dir = fullfile(script_dir, 'outputs_matlab');
if ~exist(output_dir, 'dir')
    mkdir(output_dir);
end
check_file = fullfile(output_dir, 'matlab_startup_check.txt');
fid = fopen(check_file, 'w');
fprintf(fid, 'MATLAB startup check OK: %s\n', datestr(now));
fprintf(fid, 'Current folder: %s\n', pwd);
fclose(fid);
disp(['MATLAB startup check wrote: ', check_file]);

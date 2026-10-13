% 极简运行入口：不调用任何图形或额外设置，只直接运行 stage_moni.m。
script_dir = fileparts(mfilename('fullpath'));
if isempty(script_dir)
    script_dir = pwd;
end
cd(script_dir);
run('stage_moni.m');

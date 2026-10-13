function verify_changed_scripts()
% 在独立新目录执行三程序的四组真实输入；不运行会覆盖旧结果的批处理入口。
record_dir=fileparts(mfilename('fullpath'));
root=fileparts(record_dir);
names={'shujunihe_sd.m','shujunihe_bjf.m','shujunihe3_jsb.m'};
folders={'8_图3-8腐蚀坑深度对数均值_来源与复现', ...
         '7_图3-7不均匀腐蚀深度_四模型来源与复现', ...
         '9_图3-9腐蚀坑径深比对数均值_来源与复现'};
inputs={{'sj1.mat','sj7.mat','gq2.mat','sj5_bare_steel_sd.mat'}, ...
        {'sj1.mat','sj7.mat','sj3_bjf.mat','sj2_bjf.mat'}, ...
        {'sj1.mat','sj7.mat','gq2.mat','sj5_bare_steel_jsb.mat'}};
variables={{'xiaosiy_sd2','wzy_sd','gq_sd2','sd_5'}, ...
           {'xiaosiy_bjf2','wzy_bjf','bjf3','bjf2'}, ...
           {'xsy_jsb2','wzy_jsb','gq_jsb2','jsb_5'}};
results_dir=fullfile(record_dir,['完整运行验证_',char(datetime('now','Format','yyyyMMdd_HHmmss_SSS'))]);
assert(~isfolder(results_dir),'verify:Exists','不覆盖已有验证目录。');
mkdir(results_dir);
diary(fullfile(results_dir,'MATLAB运行日志.txt')); log_cleanup=onCleanup(@()diary('off'));
old_visible=get(groot,'defaultFigureVisible');
visibility_cleanup=onCleanup(@()set(groot,'defaultFigureVisible',old_visible));
set(groot,'defaultFigureVisible','off');
summary=struct([]);
for group=1:3
    source=fullfile(root,folders{group},'程序',names{group});
    diagnostics=checkcode(source,'-id');
    fprintf('CHECKCODE %s: %d issue(s)\n',names{group},numel(diagnostics));
    save(fullfile(results_dir,[names{group}(1:end-2),'_checkcode.mat']),'diagnostics');
    for dataset=1:4
        input=fullfile(root,folders{group},'输入数据',inputs{group}{dataset});
        loaded=load(input,variables{group}{dataset});
        matrix=loaded.(variables{group}{dataset});
        out=fullfile(results_dir,names{group}(1:end-2),sprintf('数据%d',dataset));
        mkdir(out); copyfile(source,fullfile(out,names{group}));
        info=execute_one(out,names{group},matrix,group);
        info.source=source;info.input=input;info.input_variable=variables{group}{dataset};info.dataset=dataset;
        if isempty(summary)
            summary=info;
        else
            summary(end+1)=info; %#ok<AGROW>
        end
        fprintf('FULL_RUN %s dataset%d: selected=%d breakpoint=%.9g score=%.9g\n', ...
            names{group},dataset,info.two_stage_selected,info.breakpoint,info.score);
    end
end
save(fullfile(results_dir,'验证汇总.mat'),'summary');
writetable(struct2table(summary),fullfile(results_dir,'验证汇总.csv'));
fprintf('ALL_12_FULL_RUNS_COMPLETED\nRESULTS_DIR=%s\n',results_dir);
end

function info=execute_one(out,filename,matrix,group)
previous=pwd;folder_cleanup=onCleanup(@()cd(previous));
cd(out);
bjf2=matrix;sd_5=matrix;jsb_5=matrix; %#ok<NASGU>
run(filename); % 执行未经修改的本次程序副本，连同全部图像和表格输出。
if group==3
    selected=any(strcmp(used_model_names,'两阶段对数模型'));
else
    selected=numel(params_cell)>=4 && isfinite(best_score);
end
cut=NaN;score=NaN;
if selected
    p=params_cell{4};cut=p(4);
    pred=exp(p(1)+p(2)*log(x_train)+p(3)*max(log(x_train/cut),0));
    score=sqrt(mean((y_train-pred).^2));
    if ~isempty(x_test)
        pred=exp(p(1)+p(2)*log(x_test)+p(3)*max(log(x_test/cut),0));
        score=score+sqrt(mean((y_test-pred).^2));
    end
end
save('验证工作区.mat','params_cell','results','x_train','y_train','x_test','y_test', ...
     'x_fit','y_fit_cell','y_ext_cell','selected','cut','score');
info=struct('two_stage_selected',selected,'breakpoint',cut,'score',score, ...
    'train_count',numel(x_train),'validation_count',numel(x_test));
close(fig1);close(fig2);
end

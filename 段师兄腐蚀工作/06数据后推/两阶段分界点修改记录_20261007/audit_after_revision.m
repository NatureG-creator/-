function audit_after_revision()
% 对照修改前备份检查静态诊断，并重新执行两阶段搜索回归测试。
record_dir=fileparts(mfilename('fullpath'));
entries=readtable(fullfile(record_dir,'修改前来源校验.csv'), ...
    'TextType','string','Delimiter',',','Encoding','UTF-8','VariableNamingRule','preserve');
for k=1:height(entries)
    old=checkcode(char(entries.Backup(k)),'-id');
    current=checkcode(char(entries.Source(k)),'-id');
    fprintf('DIAGNOSTICS %s: before=%d after=%d\n',entries.Source(k),numel(old),numel(current));
    % 行号因插入搜索逻辑而变化；按诊断类型和信息核对，避免误判为新增问题。
    old_keys=sort(string({old.id})+"|"+string({old.message}));
    new_keys=sort(string({current.id})+"|"+string({current.message}));
    assert(all(ismember(new_keys,old_keys)), ...
        'audit:NewDiagnostic','发现修改前没有的静态诊断，请人工核对。');
    removed=setdiff(old_keys,new_keys);
    for j=1:numel(removed)
        fprintf('  removed: %s\n',removed(j));
    end
    for j=1:numel(current)
        fprintf('  line %d [%s] %s\n',current(j).line,current(j).id,current(j).message);
    end
end
results=runtests(fullfile(record_dir,'test_two_stage_revision.m'));
assertSuccess(results);
save(fullfile(record_dir,'回归验证结果.mat'),'results');
fprintf('AUDIT_AND_6_REGRESSION_TESTS_PASSED\n');
end

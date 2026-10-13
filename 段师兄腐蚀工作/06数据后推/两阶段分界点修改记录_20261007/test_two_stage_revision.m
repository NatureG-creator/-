function tests=test_two_stage_revision
% 直接执行三个文件中的实际搜索段，对比独立枚举的最小原尺度RMSE评分。
tests=functiontests(localfunctions);
end

function testDepthWithValidation(t)
check_selection(t,1,true);
end
function testNonuniformWithValidation(t)
check_selection(t,2,true);
end
function testRatioWithValidation(t)
check_selection(t,3,true);
end
function testDepthWithoutValidation(t)
check_selection(t,1,false);
end
function testNonuniformWithoutValidation(t)
check_selection(t,2,false);
end
function testRatioWithoutValidation(t)
check_selection(t,3,false);
end

function check_selection(t,index,with_validation)
x=(1:11)'; y=[2;2.4;2.9;3.1;3.4;3.9;4.1;5;5.8;6;8.5];
if with_validation, xv=12; yv=12.5; else, xv=[]; yv=[]; end
minimum=[2 3 2];
[p,candidates]=execute_search(index,x,y,xv,yv,minimum(index));
expected_candidates=unique([linspace(quantile(x,.25),quantile(x,.75),500)';x]);
verifyEqual(t,candidates(:),expected_candidates(:));
[expected,score]=reference_search(x,y,xv,yv,minimum(index),expected_candidates);
verifyEqual(t,p(:),expected(:),'AbsTol',1e-10);
verifyEqual(t,score_for(p,x,y,xv,yv),score,'AbsTol',1e-10);
verifyGreaterThanOrEqual(t,sum(x<p(4)),minimum(index));
verifyGreaterThanOrEqual(t,sum(x>=p(4)),minimum(index));
% 分界点处模型连续；后阶段增量不是第二条独立截距直线。
left=exp(p(1)+p(2)*log(p(4)));
right=exp(p(1)+p(2)*log(p(4))+p(3)*log(p(4)/p(4)));
verifyEqual(t,left,right,'AbsTol',1e-12);
end

function [p,candidates]=execute_search(index,x_train,y_train,x_test,y_test,min_pts_each_side)
files=source_files(); source=fileread(files{index});
if index<3
    first=strfind(source,'logy_train = log(y_train);');
    last=strfind(source,'if isempty(best_beta)');
    eval(source(first(1):last(1)-1));
    p=[best_beta(:);best_x1];
else
    first=strfind(source,'function [p_best, ok] = fit_two_stage_log_model');
    last=strfind(source,'function y = two_stage_log_predict');
    section=source(first(1):last(1)-1);
    first_body=strfind(section,'    % 模型：');
    body=regexprep(section(first_body(1):end),'end\s*$','');
    eval(body);
    assert(ok,'test:NoBreakpoint','未找到有效分界点。');
    p=p_best;
end
candidates=x1_candidates;
end

function [best,score]=reference_search(x,y,xv,yv,minimum,candidates)
score=Inf; best=[];
for k=1:numel(candidates)
    cut=candidates(k);
    if sum(x<cut)<minimum || sum(x>=cut)<minimum,continue;end
    design=[ones(size(x)),log(x),max(log(x/cut),0)];
    beta=design\log(y); candidate=[beta;cut];
    value=score_for(candidate,x,y,xv,yv);
    if value<score,score=value;best=candidate;end
end
end

function value=score_for(p,x,y,xv,yv)
pred=exp(p(1)+p(2)*log(x)+p(3)*max(log(x/p(4)),0));
value=sqrt(mean((y-pred).^2));
if ~isempty(xv)
    pred=exp(p(1)+p(2)*log(xv)+p(3)*max(log(xv/p(4)),0));
    value=value+sqrt(mean((yv-pred).^2));
end
end

function files=source_files()
root=fileparts(fileparts(mfilename('fullpath')));
files={fullfile(root,'8_图3-8腐蚀坑深度对数均值_来源与复现','程序','shujunihe_sd.m'), ...
       fullfile(root,'7_图3-7不均匀腐蚀深度_四模型来源与复现','程序','shujunihe_bjf.m'), ...
       fullfile(root,'9_图3-9腐蚀坑径深比对数均值_来源与复现','程序','shujunihe3_jsb.m')};
end

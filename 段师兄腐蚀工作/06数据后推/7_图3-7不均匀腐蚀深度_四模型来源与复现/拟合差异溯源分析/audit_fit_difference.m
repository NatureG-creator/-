function audit_fit_difference
% Independently audit inputs, training splits, models and saved metrics.
out = fileparts(mfilename('fullpath'));
base = fileparts(out);
files = {'sj1.mat','sj7.mat','sj3_bjf.mat','sj2_bjf.mat'};
vars = {'xiaosiy_bjf2','wzy_bjf','bjf3','bjf2'};
opts = optimoptions('lsqcurvefit','Display','off', ...
    'MaxFunctionEvaluations',5000,'MaxIterations',2000);
rows = [];
checks = [];
for d = 1:4
    input = load(fullfile(base,'输入数据',files{d}),vars{d});
    raw = input.(vars{d});
    saved = load(fullfile(base,'重新计算结果',sprintf('数据%d',d),'完整拟合结果.mat'));
    exported = readmatrix(fullfile(base,'重新计算结果',sprintf('数据%d',d),'原始输入数据.csv'));
    good = all(isfinite(raw),2) & all(raw>0,2);
    clean = sortrows(raw(good,:),1);
    x = clean(:,1); y = clean(:,2);
    assert(isequal(size(raw),size(exported)));
    inputError = max(abs(raw(:)-exported(:)));
    assert(inputError<1e-10);
    assert(isequal(x,saved.x) && isequal(y,saved.y));
    assert(isequal(x(1:numel(saved.x_train)),saved.x_train));
    metricError = 0;
    for m = 1:4
        yh = predict(saved.params_cell{m},x,m);
        yt = predict(saved.params_cell{m},saved.x_test,m);
        metrics = [1-sum((y-yh).^2)/sum((y-mean(y)).^2), ...
            sqrt(mean((y-yh).^2)),sqrt(mean((saved.y_test-yt).^2)), ...
            mean(abs((saved.y_test-yt)./saved.y_test))*100];
        metricError = max(metricError,max(abs(metrics-saved.results(m,:))));
    end
    assert(metricError<1e-8);
    checks = [checks; d,size(raw,1),sum(~good),numel(x), ...
        numel(saved.x_train),inputError,metricError]; %#ok<AGROW>
    for ratio = [0.8,0.9]
        nt = min(round(numel(x)*ratio),numel(x)-1);
        xx = x(1:nt); yy = y(1:nt);
        span = max(yy)-min(yy);
        ps = cell(4,1);
        ps{1} = lsqcurvefit(@(p,t)predict(p,t,1),[.1,min(yy)],xx,yy,[-Inf,-Inf],[Inf,Inf],opts);
        ps{2} = lsqcurvefit(@(p,t)predict(p,t,2),[span,.5,min(yy)],xx,yy,[0,0,0],[Inf,5,Inf],opts);
        ps{3} = lsqcurvefit(@(p,t)predict(p,t,3),[span,.1,min(yy)],xx,yy,[0,0,0],[Inf,Inf,Inf],opts);
        best = Inf;
        for knot = linspace(quantile(xx,.25),quantile(xx,.75),80)
            if ~any(xx<knot) || ~any(xx>=knot), continue; end
            X = [ones(size(xx)),log(xx),double(xx>=knot).*log(xx/knot)];
            b = X\log(yy);
            sse = sum((log(yy)-X*b).^2);
            if sse<best, best=sse; ps{4}=[b;knot]; end
        end
        for m = 1:4
            p = nan(1,4); p(1:numel(ps{m}))=ps{m};
            yh=predict(ps{m},x,m);
            rows=[rows;d,ratio,nt,m,p,sqrt(mean((y-yh).^2))]; %#ok<AGROW>
            fprintf('DATA%d ratio=%.1f n=%d model%d p=%s\n',d,ratio,nt,m,mat2str(ps{m},12));
        end
    end
end
writetable(array2table(rows,'VariableNames', ...
    {'Dataset','TrainRatio','TrainCount','Model','P1','P2','P3','P4','AllDataRMSE'}), ...
    fullfile(out,'训练比例对照.csv'));
writetable(array2table(checks,'VariableNames', ...
    {'Dataset','RawCount','RemovedCount','ValidCount','SavedTrainCount','InputMaxError','MetricMaxError'}), ...
    fullfile(out,'输入与评价指标核验.csv'));
save(fullfile(out,'溯源核验结果.mat'),'rows','checks');
fprintf('AUDIT_PASS: all four inputs and saved metrics verified.\n');
end

function y = predict(p,x,m)
switch m
    case 1, y=p(1)*x+p(2);
    case 2, y=p(1)*x.^p(2)+p(3);
    case 3, y=p(1)*(1-exp(-p(2)*x))+p(3);
    case 4, y=exp(p(1)+p(2)*log(x)+double(x>=p(4)).*p(3).*log(x/p(4)));
end
end

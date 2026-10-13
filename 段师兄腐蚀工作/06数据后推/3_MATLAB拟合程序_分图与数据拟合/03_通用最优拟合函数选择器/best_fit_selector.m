function result = best_fit_selector( ...
        data_file,x_column,y_column,output_dir,export_figures,model_selection)
%BEST_FIT_SELECTOR 自动比较候选函数，或仅拟合用户指定的函数。

if nargin < 2 || isempty(x_column)
    x_column = "x";
end
if nargin < 3 || isempty(y_column)
    y_column = "y";
end
if nargin < 4 || isempty(output_dir)
    if istable(data_file)
        error('BestFit:OutputDirRequiredForTable', ...
            '当data_file为table时，必须显式指定output_dir。');
    end
    [inputFolder,inputName] = fileparts(data_file);
    output_dir = fullfile(inputFolder,[inputName '_拟合结果']);
end
if nargin < 5
    export_figures = true;
end
if nargin < 6 || isempty(model_selection)
    model_selection = "自动选择最优函数";
end
model_selection = normalize_model_selection(model_selection);

[x,y] = read_xy_data(data_file,x_column,y_column);
valid = isfinite(x) & isfinite(y);
x = x(valid);
y = y(valid);
[x,order] = sort(x(:));
y = y(order);

if numel(x) < 4
    error('BestFit:InsufficientData','有效数据点少于4个，无法进行可靠拟合。');
end

cleaned_data = table(x,y);
[models,ranking_table,best_model] = fit_candidate_models( ...
    x,y,model_selection);
output_files = export_results(cleaned_data,models,ranking_table, ...
    best_model,output_dir,logical(export_figures));
result = struct( ...
    'cleaned_data',cleaned_data, ...
    'models',models, ...
    'ranking_table',ranking_table, ...
    'best_model',best_model, ...
    'requested_model',model_selection, ...
    'output_dir',string(output_dir), ...
    'output_files',output_files, ...
    'export_figures',logical(export_figures));
end

function [models,ranking,best] = fit_candidate_models(x,y,modelSelection)
if modelSelection == "自动选择最优函数"
    models = repmat(empty_model(),9,1);
    models(1) = fit_linear_model(x,y);
    models(2) = fit_quadratic_model(x,y);
    models(3) = fit_power_model(x,y);
    models(4) = fit_logarithmic_model(x,y);
    models(5) = fit_exponential_model(x,y);
    models(6) = fit_exponential_saturation_model(x,y);
    models(7) = fit_hyperbolic_saturation_model(x,y);
    models(8) = fit_two_stage_power_model(x,y);
    models(9) = fit_two_stage_log_model(x,y);
else
    switch modelSelection
        case "线性函数"
            models = fit_linear_model(x,y);
        case "二次函数"
            models = fit_quadratic_model(x,y);
        case "幂函数"
            models = fit_power_model(x,y);
        case "对数函数"
            models = fit_logarithmic_model(x,y);
        case "指数函数"
            models = fit_exponential_model(x,y);
        case "指数饱和函数"
            models = fit_exponential_saturation_model(x,y);
        case "双曲线饱和函数"
            models = fit_hyperbolic_saturation_model(x,y);
        case "连续两阶段幂函数"
            models = fit_two_stage_power_model(x,y);
        case "两阶段对数模型"
            models = fit_two_stage_log_model(x,y);
        otherwise
            error('BestFit:UnknownModel','未知拟合函数：%s',modelSelection);
    end
end

for i = 1:numel(models)
    if models(i).success
        prediction = models(i).predict(x);
        if any(~isfinite(prediction)) || ~isreal(prediction)
            models(i) = mark_failed(models(i),"预测结果包含非有限值或复数");
        else
            models(i).metrics = calculate_metrics(y,prediction, ...
                models(i).parameter_count);
        end
    end
end

success = [models.success]';
aicc = inf(numel(models),1);
rmse = inf(numel(models),1);
for i = 1:numel(models)
    if success(i)
        aicc(i) = models(i).metrics.AICc;
        rmse(i) = models(i).metrics.RMSE;
    end
end
[~,order] = sortrows([~success,aicc,rmse],[1 2 3]);
models = models(order);

if ~any([models.success])
    error('BestFit:NoValidModel','没有可用于当前数据的候选模型。');
end
best = models(find([models.success],1));
ranking = models_to_table(models);
end

function modelSelection = normalize_model_selection(modelSelection)
if ~(ischar(modelSelection) || ...
        (isstring(modelSelection) && isscalar(modelSelection)))
    error('BestFit:UnknownModel','拟合函数名称必须是一个字符串。');
end
modelSelection = string(modelSelection);
automaticAliases = ["auto","自动","自动选择","自动选择最优函数"];
if any(strcmpi(modelSelection,automaticAliases))
    modelSelection = "自动选择最优函数";
    return;
end

allowedModels = ["线性函数","二次函数","幂函数","对数函数", ...
    "指数函数","指数饱和函数","双曲线饱和函数", ...
    "连续两阶段幂函数","两阶段对数模型"];
index = find(strcmpi(modelSelection,allowedModels),1);
if isempty(index)
    error('BestFit:UnknownModel','未知拟合函数：%s',modelSelection);
end
modelSelection = allowedModels(index);
end

function model = fit_linear_model(x,y)
model = empty_model();
model.name = "线性函数";
try
    p = polyfit(x,y,1);
    model.parameters = p;
    model.parameter_count = 2;
    model.formula = sprintf('y = %.10g*x %+.10g',p(1),p(2));
    model.predict = @(xq) polyval(p,xq);
    model.success = true;
    model.status = "成功";
catch exception
    model = mark_failed(model,string(exception.message));
end
end

function model = fit_quadratic_model(x,y)
model = empty_model();
model.name = "二次函数";
try
    p = polyfit(x,y,2);
    model.parameters = p;
    model.parameter_count = 3;
    model.formula = sprintf('y = %.10g*x^2 %+.10g*x %+.10g', ...
        p(1),p(2),p(3));
    model.predict = @(xq) polyval(p,xq);
    model.success = true;
    model.status = "成功";
catch exception
    model = mark_failed(model,string(exception.message));
end
end

function model = fit_power_model(x,y)
model = empty_model();
model.name = "幂函数";
model.parameter_count = 2;
if any(x <= 0) || any(y <= 0)
    model = mark_failed(model,"跳过：幂函数要求全部x>0且y>0");
    return;
end
try
    initial = polyfit(log(x),log(y),1);
    theta0 = [initial(2),initial(1)];
    objective = @(theta) safe_sse(y, ...
        exp(theta(1)).*x.^theta(2));
    theta = fminsearch(objective,theta0,solver_options());
    p = [exp(theta(1)),theta(2)];
    model.parameters = p;
    model.formula = sprintf('y = %.10g*x^{%.10g}',p(1),p(2));
    model.predict = @(xq) p(1).*xq.^p(2);
    model.success = true;
    model.status = "成功";
catch exception
    model = mark_failed(model,string(exception.message));
end
end

function model = fit_logarithmic_model(x,y)
model = empty_model();
model.name = "对数函数";
model.parameter_count = 2;
if any(x <= 0)
    model = mark_failed(model,"跳过：对数函数要求全部x>0");
    return;
end
try
    p = polyfit(log(x),y,1);
    model.parameters = p;
    model.formula = sprintf('y = %.10g*ln(x) %+.10g',p(1),p(2));
    model.predict = @(xq) p(1).*log(xq)+p(2);
    model.success = true;
    model.status = "成功";
catch exception
    model = mark_failed(model,string(exception.message));
end
end

function model = fit_exponential_model(x,y)
model = empty_model();
model.name = "指数函数";
model.parameter_count = 2;
try
    if all(y > 0)
        initial = polyfit(x,log(y),1);
        theta0 = [log(max(exp(initial(2)),realmin)),initial(1)];
        objective = @(theta) safe_sse(y, ...
            exp(theta(1)).*exp(theta(2).*x));
        theta = fminsearch(objective,theta0,solver_options());
        p = [exp(theta(1)),theta(2)];
    else
        p0 = [mean(y),0];
        objective = @(p) safe_sse(y,p(1).*exp(p(2).*x));
        p = fminsearch(objective,p0,solver_options());
    end
    model.parameters = p;
    model.formula = sprintf('y = %.10g*exp(%.10g*x)',p(1),p(2));
    model.predict = @(xq) p(1).*exp(p(2).*xq);
    model.success = true;
    model.status = "成功";
catch exception
    model = mark_failed(model,string(exception.message));
end
end

function model = fit_exponential_saturation_model(x,y)
model = empty_model();
model.name = "指数饱和函数";
model.parameter_count = 3;
try
    xScale = max(max(x)-min(x),eps);
    theta0 = [max(y)-min(y),log(1/xScale),min(y)];
    objective = @(theta) safe_sse(y,theta(1).*(1-exp( ...
        -exp(theta(2)).*x))+theta(3));
    theta = fminsearch(objective,theta0,solver_options());
    p = [theta(1),exp(theta(2)),theta(3)];
    model.parameters = p;
    model.formula = sprintf( ...
        'y = %.10g*(1-exp(-%.10g*x)) %+.10g',p(1),p(2),p(3));
    model.predict = @(xq) p(1).*(1-exp(-p(2).*xq))+p(3);
    model.success = true;
    model.status = "成功";
catch exception
    model = mark_failed(model,string(exception.message));
end
end

function model = fit_hyperbolic_saturation_model(x,y)
model = empty_model();
model.name = "双曲线饱和函数";
model.parameter_count = 3;
try
    xScale = max(median(abs(x)),eps);
    theta0 = [max(y)-min(y),log(xScale),min(y)];
    objective = @(theta) safe_sse(y,theta(1).*x./( ...
        exp(theta(2))+x)+theta(3));
    theta = fminsearch(objective,theta0,solver_options());
    p = [theta(1),exp(theta(2)),theta(3)];
    model.parameters = p;
    model.formula = sprintf('y = %.10g*x/(%.10g+x) %+.10g', ...
        p(1),p(2),p(3));
    model.predict = @(xq) p(1).*xq./(p(2)+xq)+p(3);
    model.success = true;
    model.status = "成功";
catch exception
    model = mark_failed(model,string(exception.message));
end
end

function model = fit_two_stage_power_model(x,y)
model = empty_model();
model.name = "连续两阶段幂函数";
model.parameter_count = 4;
if numel(x) < 6
    model = mark_failed(model,"跳过：两阶段模型至少需要6个数据点");
    return;
end
if any(x <= 0) || any(y <= 0)
    model = mark_failed(model,"跳过：两阶段幂函数要求全部x>0且y>0");
    return;
end

try
    uniqueX = unique(x);
    if numel(uniqueX) < 5
        model = mark_failed(model,"跳过：两阶段模型至少需要5个不同x值");
        return;
    end

    candidates = uniqueX(3:end-2);
    bestSSE = Inf;
    bestParameters = [];
    for i = 1:numel(candidates)
        breakPoint = candidates(i);
        if numel(unique(x(x < breakPoint))) < 2 || ...
                numel(unique(x(x >= breakPoint))) < 2
            continue;
        end

        indicator = double(x >= breakPoint);
        design = [ones(size(x)),log(x), ...
            indicator.*log(x./breakPoint)];
        beta = design\log(y);
        initial = [beta(1),beta(2),beta(2)+beta(3)];
        objective = @(theta) safe_sse(y,two_stage_prediction( ...
            [exp(theta(1)),theta(2),theta(3),breakPoint],x));
        theta = fminsearch(objective,initial,solver_options());
        parameters = [exp(theta(1)),theta(2),theta(3),breakPoint];
        currentSSE = objective(theta);
        if currentSSE < bestSSE
            bestSSE = currentSSE;
            bestParameters = parameters;
        end
    end

    if isempty(bestParameters)
        model = mark_failed(model,"跳过：找不到满足两侧数据量要求的转折点");
        return;
    end

    p = bestParameters;
    model.parameters = p;
    model.formula = sprintf([ ...
        'x < %.10g: y = %.10g*x^{%.10g}; ', ...
        'x >= %.10g: y = %.10g*%.10g^{%.10g-%.10g}*x^{%.10g}'], ...
        p(4),p(1),p(2),p(4),p(1),p(4),p(2),p(3),p(3));
    model.predict = @(xq) two_stage_prediction(p,xq);
    model.success = true;
    model.status = "成功";
catch exception
    model = mark_failed(model,string(exception.message));
end
end

function prediction = two_stage_prediction(parameters,x)
a = parameters(1);
n1 = parameters(2);
n2 = parameters(3);
breakPoint = parameters(4);
prediction = zeros(size(x));
left = x < breakPoint;
prediction(left) = a.*x(left).^n1;
prediction(~left) = a.*breakPoint.^(n1-n2).*x(~left).^n2;
end

function model = fit_two_stage_log_model(x,y)
% 严格对应文献公式：
% ln(y)=a*ln(x), x<x1
% ln(y)=a*ln(x1)+b*ln(x/x1), x>=x1
model = empty_model();
model.name = "两阶段对数模型";
model.parameter_count = 3;
if numel(x) < 6
    model = mark_failed(model,"跳过：两阶段对数模型至少需要6个数据点");
    return;
end
if any(x <= 0) || any(y <= 0)
    model = mark_failed(model,"跳过：两阶段对数模型要求全部x>0且y>0");
    return;
end

try
    uniqueX = unique(x);
    if numel(uniqueX) < 5
        model = mark_failed(model,"跳过：两阶段对数模型至少需要5个不同x值");
        return;
    end

    candidates = uniqueX(3:end-2);
    bestSSE = Inf;
    bestParameters = [];
    for i = 1:numel(candidates)
        breakPoint = candidates(i);
        left = x < breakPoint;
        right = ~left;
        if numel(unique(x(left))) < 2 || numel(unique(x(right))) < 2
            continue;
        end

        design = zeros(numel(x),2);
        design(left,1) = log(x(left));
        design(right,1) = log(breakPoint);
        design(right,2) = log(x(right)./breakPoint);
        initial = (design\log(y))';
        objective = @(theta) safe_sse(y, ...
            two_stage_log_prediction( ...
            [theta(1),theta(2),breakPoint],x));
        theta = fminsearch(objective,initial,solver_options());
        parameters = [theta(1),theta(2),breakPoint];
        currentSSE = objective(theta);
        if currentSSE < bestSSE
            bestSSE = currentSSE;
            bestParameters = parameters;
        end
    end

    if isempty(bestParameters)
        model = mark_failed(model,"跳过：找不到满足两侧数据量要求的转折点");
        return;
    end

    p = bestParameters;
    model.parameters = p;
    model.formula = sprintf([ ...
        'x < %.10g: ln(y) = %.10g*ln(x); ', ...
        'x >= %.10g: ln(y) = %.10g*ln(%.10g) + %.10g*ln(x/%.10g)'], ...
        p(3),p(1),p(3),p(1),p(3),p(2),p(3));
    model.predict = @(xq) two_stage_log_prediction(p,xq);
    model.success = true;
    model.status = "成功";
catch exception
    model = mark_failed(model,string(exception.message));
end
end

function prediction = two_stage_log_prediction(parameters,x)
a = parameters(1);
b = parameters(2);
breakPoint = parameters(3);
prediction = zeros(size(x));
left = x < breakPoint;
prediction(left) = x(left).^a;
prediction(~left) = breakPoint.^(a-b).*x(~left).^b;
end

function metrics = calculate_metrics(y,prediction,k)
n = numel(y);
residual = y-prediction;
SSE = sum(residual.^2);
TSS = sum((y-mean(y)).^2);
if TSS <= eps(max(abs(y)))
    if SSE <= eps(max(abs(y)))
        R2 = 1;
    else
        R2 = NaN;
    end
else
    R2 = 1-SSE/TSS;
end
if n-k-1 > 0 && isfinite(R2)
    adjustedR2 = 1-(1-R2)*(n-1)/(n-k-1);
else
    adjustedR2 = NaN;
end
RMSE = sqrt(SSE/n);
dataScale = max([1;abs(y(:))]);
numericMseFloor = (dataScale*1e-12)^2;
meanSquareError = max(SSE/n,numericMseFloor);
AIC = n*log(meanSquareError)+2*k;
if n-k-1 > 0
    AICc = AIC+2*k*(k+1)/(n-k-1);
else
    AICc = Inf;
end
metrics = struct('R2',R2,'AdjustedR2',adjustedR2, ...
    'RMSE',RMSE,'SSE',SSE,'AIC',AIC,'AICc',AICc);
end

function tableResult = models_to_table(models)
count = numel(models);
Rank = (1:count)';
Model = strings(count,1);
Formula = strings(count,1);
ParameterCount = zeros(count,1);
R2 = nan(count,1);
AdjustedR2 = nan(count,1);
RMSE = nan(count,1);
SSE = nan(count,1);
AIC = nan(count,1);
AICc = nan(count,1);
Status = strings(count,1);

for i = 1:count
    Model(i) = models(i).name;
    Formula(i) = models(i).formula;
    ParameterCount(i) = models(i).parameter_count;
    Status(i) = models(i).status;
    if models(i).success
        R2(i) = models(i).metrics.R2;
        AdjustedR2(i) = models(i).metrics.AdjustedR2;
        RMSE(i) = models(i).metrics.RMSE;
        SSE(i) = models(i).metrics.SSE;
        AIC(i) = models(i).metrics.AIC;
        AICc(i) = models(i).metrics.AICc;
    end
end

tableResult = table(Rank,Model,Formula,ParameterCount,R2, ...
    AdjustedR2,RMSE,SSE,AIC,AICc,Status);
end

function outputFiles = export_results(cleanedData,models,ranking,best, ...
        outputDir,exportFigures)
outputDir = char(string(outputDir));
if ~isfolder(outputDir)
    mkdir(outputDir);
end

outputFiles = strings(0,1);
rankingFile = fullfile(outputDir,'模型拟合评价表.csv');
summaryFile = fullfile(outputDir,'最优拟合函数.txt');
cleanedFile = fullfile(outputDir,'清洗后的拟合数据.csv');
writetable(ranking,rankingFile);
writetable(cleanedData,cleanedFile);
write_best_model_summary(summaryFile,best,height(cleanedData));
outputFiles = [outputFiles;string(rankingFile);string(summaryFile); ...
    string(cleanedFile)];

if exportFigures
    outputFiles = [outputFiles;export_model_figures( ...
        cleanedData.x,cleanedData.y,models,best,outputDir)];
end
end

function write_best_model_summary(filePath,best,dataCount)
fileId = fopen(filePath,'w','n','UTF-8');
if fileId < 0
    error('BestFit:OutputWriteFailed','无法写入结果文件：%s',filePath);
end
fileCleanup = onCleanup(@() fclose(fileId));
fprintf(fileId,'MATLAB通用最优拟合函数选择结果\n');
fprintf(fileId,'====================================\n');
fprintf(fileId,'最优模型：%s\n',char(best.name));
fprintf(fileId,'拟合公式：%s\n',char(best.formula));
fprintf(fileId,'参数向量：%s\n',mat2str(best.parameters,12));
fprintf(fileId,'数据点数：%d\n',dataCount);
fprintf(fileId,'R2：%.12g\n',best.metrics.R2);
fprintf(fileId,'调整R2：%.12g\n',best.metrics.AdjustedR2);
fprintf(fileId,'RMSE：%.12g\n',best.metrics.RMSE);
fprintf(fileId,'SSE：%.12g\n',best.metrics.SSE);
fprintf(fileId,'AIC：%.12g\n',best.metrics.AIC);
fprintf(fileId,'AICc：%.12g\n',best.metrics.AICc);
end

function outputFiles = export_model_figures(x,y,models,best,outputDir)
xGrid = linspace(min(x),max(x),600)';
outputFiles = strings(0,1);

figureAll = figure('Visible','off','Color','w', ...
    'Position',[100 100 1200 760]);
cleanupAll = onCleanup(@() close_valid_figure(figureAll));
axesAll = axes(figureAll);
hold(axesAll,'on');
plot(axesAll,x,y,'ko','MarkerFaceColor','k','MarkerSize',5, ...
    'DisplayName','原始数据');
successfulModels = models([models.success]);
colors = lines(max(numel(successfulModels),1));
for i = 1:numel(successfulModels)
    prediction = successfulModels(i).predict(xGrid);
    lineWidth = 1.4;
    if successfulModels(i).name == best.name
        lineWidth = 3;
    end
    plot(axesAll,xGrid,prediction,'Color',colors(i,:), ...
        'LineWidth',lineWidth,'DisplayName',successfulModels(i).name);
end
format_fit_axes(axesAll,'全部候选模型拟合对比','x','y');
legend(axesAll,'Location','best','Interpreter','none','FontSize',9);
outputFiles = [outputFiles;save_figure_formats( ...
    figureAll,outputDir,'全部模型拟合对比图')];
close(figureAll);

figureBest = figure('Visible','off','Color','w', ...
    'Position',[100 100 1200 760]);
cleanupBest = onCleanup(@() close_valid_figure(figureBest));
axesBest = axes(figureBest);
hold(axesBest,'on');
plot(axesBest,x,y,'ko','MarkerFaceColor','k','MarkerSize',6, ...
    'DisplayName','原始数据');
plot(axesBest,xGrid,best.predict(xGrid),'r-', ...
    'LineWidth',2.8,'DisplayName',best.name);
format_fit_axes(axesBest,'最优模型拟合结果','x','y');
subtitle(axesBest,sprintf('%s | AICc = %.6g', ...
    char(best.formula),best.metrics.AICc),'Interpreter','none');
legend(axesBest,'Location','best','Interpreter','none');
outputFiles = [outputFiles;save_figure_formats( ...
    figureBest,outputDir,'最优模型拟合图')];
close(figureBest);

figureResidual = figure('Visible','off','Color','w', ...
    'Position',[100 100 1200 760]);
cleanupResidual = onCleanup( ...
    @() close_valid_figure(figureResidual));
axesResidual = axes(figureResidual);
residual = y-best.predict(x);
stem(axesResidual,x,residual,'filled','LineWidth',1.1, ...
    'MarkerSize',4,'Color',[0.12 0.45 0.72]);
hold(axesResidual,'on');
yline(axesResidual,0,'k--','LineWidth',1.2);
format_fit_axes(axesResidual,'最优模型残差图','x','y - y_{fit}');
outputFiles = [outputFiles;save_figure_formats( ...
    figureResidual,outputDir,'最优模型残差图')];
close(figureResidual);
end

function format_fit_axes(axesHandle,titleText,xText,yText)
grid(axesHandle,'on');
box(axesHandle,'on');
axesHandle.FontName = 'Microsoft YaHei';
axesHandle.FontSize = 11;
xlabel(axesHandle,xText,'FontName','Microsoft YaHei');
ylabel(axesHandle,yText,'FontName','Microsoft YaHei');
title(axesHandle,titleText,'FontName','Microsoft YaHei', ...
    'FontWeight','bold');
end

function files = save_figure_formats(figureHandle,outputDir,baseName)
pngFile = fullfile(outputDir,[baseName '.png']);
tifFile = fullfile(outputDir,[baseName '.tif']);
pdfFile = fullfile(outputDir,[baseName '.pdf']);
figFile = fullfile(outputDir,[baseName '.fig']);
drawnow;
exportgraphics(figureHandle,pngFile,'Resolution',600);
exportgraphics(figureHandle,tifFile,'Resolution',600);
exportgraphics(figureHandle,pdfFile,'ContentType','vector');
savefig(figureHandle,figFile);
files = string({pngFile;tifFile;pdfFile;figFile});
end

function close_valid_figure(figureHandle)
if isgraphics(figureHandle)
    close(figureHandle);
end
end

function model = empty_model()
emptyMetrics = struct('R2',NaN,'AdjustedR2',NaN,'RMSE',NaN, ...
    'SSE',NaN,'AIC',NaN,'AICc',NaN);
model = struct('name',"",'formula',"",'parameters',[], ...
    'parameter_count',0,'predict',@(x) nan(size(x)), ...
    'success',false,'status',"尚未拟合",'metrics',emptyMetrics);
end

function model = mark_failed(model,message)
model.success = false;
model.status = string(message);
model.formula = "";
model.parameters = [];
model.predict = @(x) nan(size(x));
end

function value = safe_sse(observed,predicted)
if ~isreal(predicted) || any(~isfinite(predicted)) || ...
        numel(predicted) ~= numel(observed)
    value = realmax('double')/100;
    return;
end
residual = observed-predicted;
value = sum(residual.^2);
if ~isfinite(value)
    value = realmax('double')/100;
end
end

function options = solver_options()
options = optimset('Display','off','MaxFunEvals',20000, ...
    'MaxIter',10000,'TolX',1e-10,'TolFun',1e-12);
end

function [x,y] = read_xy_data(data_file,x_column,y_column)
if istable(data_file)
    x = get_table_variable(data_file,x_column);
    y = get_table_variable(data_file,y_column);
elseif ischar(data_file) || (isstring(data_file) && isscalar(data_file))
    data_file = char(string(data_file));
    if ~isfile(data_file)
        error('BestFit:FileNotFound','找不到数据文件：%s',data_file);
    end

    [~,~,extension] = fileparts(data_file);
    switch lower(extension)
        case '.mat'
            loaded = load(data_file);
            x = get_struct_variable(loaded,x_column);
            y = get_struct_variable(loaded,y_column);
        case {'.xlsx','.xls','.csv','.txt','.dat'}
            tableData = readtable(data_file,'VariableNamingRule','preserve');
            x = get_table_variable(tableData,x_column);
            y = get_table_variable(tableData,y_column);
        otherwise
            error('BestFit:UnsupportedFormat', ...
                '不支持文件格式%s，请使用xlsx、csv、txt或mat。',extension);
    end
else
    error('BestFit:InvalidFile','data_file必须是文件路径或table。');
end

if ~isnumeric(x) || ~isnumeric(y)
    error('BestFit:NonNumericData','x列和y列必须是数值数据。');
end
if numel(x) ~= numel(y)
    error('BestFit:LengthMismatch','x与y的数据长度不一致。');
end

x = double(x(:));
y = double(y(:));
end

function values = get_struct_variable(data,column)
if isnumeric(column) && isscalar(column)
    names = fieldnames(data);
    index = validate_column_index(column,numel(names));
    values = data.(names{index});
    return;
end

name = char(string(column));
names = fieldnames(data);
index = find(strcmpi(names,name),1);
if isempty(index)
    error('BestFit:MissingColumn','MAT文件中不存在变量%s。',name);
end
values = data.(names{index});
end

function values = get_table_variable(data,column)
if isnumeric(column) && isscalar(column)
    index = validate_column_index(column,width(data));
else
    name = char(string(column));
    index = find(strcmpi(data.Properties.VariableNames,name),1);
    if isempty(index)
        error('BestFit:MissingColumn','数据文件中不存在列%s。',name);
    end
end
values = data{:,index};
end

function index = validate_column_index(column,columnCount)
if column < 1 || column ~= fix(column) || column > columnCount
    error('BestFit:MissingColumn','列号%d超出数据列范围。',column);
end
index = double(column);
end

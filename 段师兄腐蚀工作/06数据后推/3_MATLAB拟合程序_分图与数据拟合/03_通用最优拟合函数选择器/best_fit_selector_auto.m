function batchResult = best_fit_selector_auto( ...
        data_file,output_dir,export_figures,model_choices,formula_digits)
%BEST_FIT_SELECTOR_AUTO 自动识别数据列，并批量拟合全部可识别指标。

if nargin < 2 || isempty(output_dir)
    [inputFolder,inputName] = fileparts(data_file);
    output_dir = fullfile(inputFolder,[inputName '_自动拟合结果']);
end
if nargin < 3
    export_figures = true;
end
if nargin < 4 || isempty(model_choices)
    model_choices = "auto";
end
if nargin < 5 || isempty(formula_digits)
    formula_digits = 4;
end
validateattributes(formula_digits,{'numeric'}, ...
    {'scalar','integer','nonnegative','finite'});

[tableData,inputName] = read_auto_table(data_file);
variableNames = string(tableData.Properties.VariableNames);

resultColumns = ["Material","Metric","Model","Intercept", ...
    "Slope","R2","RMSE","Formula"];
if all(ismember(lower(resultColumns),lower(variableNames)))
    error('BestFit:ResultFileNotRawData', ...
        ['当前文件是拟合参数结果表，不是原始实验数据。' ...
        '请选择包含Eta和力学指标的数据文件。']);
end

[etaName,hasEta] = find_column(variableNames,"Eta");
[etaPercentName,hasEtaPercent] = find_column(variableNames,"EtaPercent");
strainCandidates = ["EpsilonH";"EpsilonU";"EpsilonF";"E_MPa"];
strainLabels = ["硬化应变";"极限应变";"断裂应变";"弹性模量"];
[metrics,labels] = find_metrics(variableNames,strainCandidates,strainLabels);
if ~isempty(metrics)
    dataType = "腐蚀后应变弹模数据";
else
    strengthCandidates = ["Fy_MPa";"Fu_MPa";"Ff_MPa";"StrengthRatio"];
    strengthLabels = ["屈服强度";"抗拉强度";"断裂强度";"强屈比"];
    [metrics,labels] = find_metrics( ...
        variableNames,strengthCandidates,strengthLabels);
    dataType = "腐蚀后强度指标数据";
end

if ~isempty(metrics)
    if hasEta
        xColumn = etaName;
    elseif hasEtaPercent
        etaPercent = tableData{:,char(etaPercentName)};
        if ~isnumeric(etaPercent)
            error('BestFit:NonNumericData','EtaPercent列必须是数值数据。');
        end
        tableData.Eta = double(etaPercent)/100;
        xColumn = "Eta";
    else
        error('BestFit:MissingIndependentVariable', ...
            '识别到力学指标，但没有找到Eta或EtaPercent列。');
    end
elseif has_columns(variableNames,["x","y"])
    [xColumn,~] = find_column(variableNames,"x");
    [yColumn,~] = find_column(variableNames,"y");
    metrics = yColumn;
    labels = "纵坐标y";
    dataType = "通用x-y数据";
else
    numericColumns = find_numeric_columns(tableData);
    if numel(numericColumns) ~= 2
        error('BestFit:UnrecognizedSchema', ...
            ['无法自动识别数据格式。需要Eta/EtaPercent与力学指标、' ...
            'x-y列，或恰好两列数值数据。']);
    end
    xColumn = variableNames(numericColumns(1));
    metrics = variableNames(numericColumns(2));
    labels = "第2列数值";
    dataType = "通用两列数值数据";
end

if ~isfolder(output_dir)
    mkdir(output_dir);
end

selectedModels = resolve_model_choices( ...
    metrics,labels,model_choices,dataType);

results = cell(numel(metrics),1);
bestModels = strings(numel(metrics),1);
formulas = strings(numel(metrics),1);
r2 = nan(numel(metrics),1);
rmse = nan(numel(metrics),1);
aicc = nan(numel(metrics),1);

for i = 1:numel(metrics)
    metricOutputDir = fullfile(output_dir,char(metrics(i)));
    if selectedModels(i) == "均值模型"
        results{i} = summarize_mean_metric(tableData,xColumn,metrics(i), ...
            metricOutputDir,logical(export_figures));
    else
        results{i} = best_fit_selector(tableData,xColumn,metrics(i), ...
            metricOutputDir,logical(export_figures),selectedModels(i));
    end
    bestModels(i) = results{i}.best_model.name;
    formulas(i) = format_best_fit_formula( ...
        results{i}.best_model.name,results{i}.best_model.parameters, ...
        formula_digits,xColumn,metrics(i));
    r2(i) = results{i}.best_model.metrics.R2;
    rmse(i) = results{i}.best_model.metrics.RMSE;
    aicc(i) = results{i}.best_model.metrics.AICc;
end

summaryTable = table(metrics,labels,selectedModels,bestModels, ...
    formulas,r2,rmse,aicc, ...
    'VariableNames',{'Metric','ChineseName','RequestedModel', ...
    'BestModel','Formula','R2','RMSE','AICc'});
writetable(summaryTable,fullfile(output_dir,'自动拟合汇总.csv'));

batchResult = struct( ...
    'input_name',string(inputName), ...
    'data_type',dataType, ...
    'x_column',string(xColumn), ...
    'metrics',metrics, ...
    'selected_models',selectedModels, ...
    'formula_digits',formula_digits, ...
    'results',{results}, ...
    'summary_table',summaryTable, ...
    'output_dir',string(output_dir));
end

function selectedModels = resolve_model_choices( ...
        metrics,labels,modelChoices,dataType)
selectedModels = default_model_choices(metrics,dataType);

if ischar(modelChoices) || (isstring(modelChoices) && isscalar(modelChoices))
    mode = string(modelChoices);
    if strcmpi(mode,"prompt")
        for i = 1:numel(metrics)
            selectedModels(i) = prompt_for_model( ...
                metrics(i),labels(i),selectedModels(i));
        end
    elseif any(strcmpi(mode,["auto","自动","自动选择","自动选择最优函数"]))
        return;
    else
        selectedModels(:) = normalize_auto_model_choice(mode);
    end
elseif isstruct(modelChoices)
    fields = string(fieldnames(modelChoices));
    for i = 1:numel(metrics)
        fieldIndex = find(strcmpi(fields,metrics(i)),1);
        if ~isempty(fieldIndex)
            selectedModels(i) = normalize_auto_model_choice( ...
                modelChoices.(char(fields(fieldIndex))));
        end
    end
elseif isstring(modelChoices) && numel(modelChoices) == numel(metrics)
    for i = 1:numel(metrics)
        selectedModels(i) = normalize_auto_model_choice(modelChoices(i));
    end
else
    error('BestFit:InvalidModelChoices', ...
        'model_choices必须是prompt、auto、模型名称、结构体或与指标等长的字符串数组。');
end
end

function selectedModels = default_model_choices(metrics,dataType)
selectedModels = repmat("自动选择最优函数",numel(metrics),1);
if dataType == "腐蚀后强度指标数据"
    selectedModels(strcmpi(metrics,"StrengthRatio")) = "均值模型";
end
end

function selectedModel = prompt_for_model(metric,label,defaultModel)
options = available_model_choices();
defaultIndex = find(options == defaultModel,1);
if isempty(defaultIndex)
    defaultIndex = 1;
end
[selection,confirmed] = listdlg( ...
    'PromptString',sprintf('为 %s（%s）选择拟合函数：',metric,label), ...
    'SelectionMode','single', ...
    'ListString',cellstr(options), ...
    'InitialValue',defaultIndex, ...
    'ListSize',[300,300], ...
    'Name','选择拟合函数');
if ~confirmed
    error('BestFit:SelectionCancelled','已取消%s的拟合函数选择。',metric);
end
selectedModel = options(selection);
end

function selectedModel = normalize_auto_model_choice(modelChoice)
if ~(ischar(modelChoice) || ...
        (isstring(modelChoice) && isscalar(modelChoice)))
    error('BestFit:UnknownModel','拟合函数名称必须是一个字符串。');
end
modelChoice = string(modelChoice);
options = available_model_choices();
automaticAliases = ["auto","自动","自动选择","自动选择最优函数"];
if any(strcmpi(modelChoice,automaticAliases))
    selectedModel = "自动选择最优函数";
    return;
end
index = find(strcmpi(modelChoice,options),1);
if isempty(index)
    error('BestFit:UnknownModel','未知拟合函数：%s',modelChoice);
end
selectedModel = options(index);
end

function options = available_model_choices()
options = ["自动选择最优函数";"线性函数";"二次函数";"幂函数"; ...
    "对数函数";"指数函数";"指数饱和函数";"双曲线饱和函数"; ...
    "连续两阶段幂函数";"两阶段对数模型";"均值模型"];
end

function [tableData,inputName] = read_auto_table(data_file)
if ~(ischar(data_file) || (isstring(data_file) && isscalar(data_file)))
    error('BestFit:InvalidFile','data_file必须是一个文件路径。');
end
data_file = char(string(data_file));
if ~isfile(data_file)
    error('BestFit:FileNotFound','找不到数据文件：%s',data_file);
end

[~,inputName,extension] = fileparts(data_file);
switch lower(extension)
    case {'.xlsx','.xls','.csv','.txt','.dat'}
        tableData = readtable(data_file,'VariableNamingRule','preserve');
    case '.mat'
        loaded = load(data_file);
        names = string(fieldnames(loaded));
        if ~has_columns(names,["x","y"])
            error('BestFit:UnrecognizedSchema', ...
                'MAT文件自动识别目前要求包含数值变量x和y。');
        end
        [xName,~] = find_column(names,"x");
        [yName,~] = find_column(names,"y");
        x = loaded.(char(xName));
        y = loaded.(char(yName));
        tableData = table(x(:),y(:),'VariableNames',{'x','y'});
    otherwise
        error('BestFit:UnsupportedFormat', ...
            '不支持文件格式%s，请使用xlsx、csv、txt、dat或mat。',extension);
end
end

function [actualName,found] = find_column(variableNames,targetName)
index = find(strcmpi(variableNames,targetName),1);
found = ~isempty(index);
if found
    actualName = variableNames(index);
else
    actualName = "";
end
end

function tf = has_columns(variableNames,targetNames)
tf = all(ismember(lower(targetNames),lower(variableNames)));
end

function [metrics,labels] = find_metrics(variableNames,candidates,candidateLabels)
metrics = strings(0,1);
labels = strings(0,1);
for i = 1:numel(candidates)
    [actualName,found] = find_column(variableNames,candidates(i));
    if found
        metrics(end+1,1) = actualName; %#ok<AGROW>
        labels(end+1,1) = candidateLabels(i); %#ok<AGROW>
    end
end
end

function indices = find_numeric_columns(tableData)
indices = zeros(0,1);
for i = 1:width(tableData)
    if isnumeric(tableData{:,i})
        indices(end+1,1) = i; %#ok<AGROW>
    end
end
end

function result = summarize_mean_metric( ...
        tableData,xColumn,yColumn,outputDir,exportFigures)
x = get_table_column(tableData,xColumn);
y = get_table_column(tableData,yColumn);
if ~isnumeric(x) || ~isnumeric(y)
    error('BestFit:NonNumericData','均值统计的x列和y列必须是数值数据。');
end

valid = isfinite(x) & isfinite(y);
x = double(x(valid));
y = double(y(valid));
[x,order] = sort(x(:));
y = y(order);
if numel(x) < 2
    error('BestFit:InsufficientData','有效数据点少于2个，无法进行均值统计。');
end

meanValue = mean(y);
stdValue = std(y);
prediction = repmat(meanValue,size(y));
residual = y-prediction;
n = numel(y);
sse = sum(residual.^2);
rmseValue = sqrt(mean(residual.^2));
sst = sum((y-mean(y)).^2);
if sst > 0
    r2Value = 1-sse/sst;
else
    r2Value = NaN;
end
parameterCount = 1;
aic = n*log(max(sse/n,realmin))+2*parameterCount;
if n > parameterCount+1
    aiccValue = aic+2*parameterCount*(parameterCount+1) ...
        /(n-parameterCount-1);
else
    aiccValue = Inf;
end

metrics = struct('R2',r2Value,'AdjustedR2',r2Value, ...
    'RMSE',rmseValue,'SSE',sse,'AIC',aic,'AICc',aiccValue);
model = struct( ...
    'name',"均值模型", ...
    'formula',sprintf('y = %.10g (std = %.10g)',meanValue,stdValue), ...
    'parameters',[meanValue,stdValue], ...
    'parameter_count',parameterCount, ...
    'predict',@(xq) repmat(meanValue,size(xq)), ...
    'success',true, ...
    'status',"成功", ...
    'metrics',metrics);

if ~isfolder(outputDir)
    mkdir(outputDir);
end
cleanedData = table(x,y);
writetable(cleanedData,fullfile(outputDir,'清洗后的拟合数据.csv'));

modelTable = table(model.name,string(model.formula),r2Value,r2Value, ...
    rmseValue,sse,aic,aiccValue,model.status,meanValue,stdValue, ...
    'VariableNames',{'Model','Formula','R2','AdjustedR2','RMSE', ...
    'SSE','AIC','AICc','Status','Mean','Std'});
writetable(modelTable,fullfile(outputDir,'模型拟合评价表.csv'));
writetable(table(meanValue,stdValue,'VariableNames',{'Mean','Std'}), ...
    fullfile(outputDir,'均值统计结果.csv'));

textFile = fullfile(outputDir,'最优拟合函数.txt');
fileId = fopen(textFile,'w','n','UTF-8');
if fileId < 0
    error('BestFit:OutputWriteFailed','无法写入文件：%s',textFile);
end
cleanupFile = onCleanup(@() fclose(fileId));
fprintf(fileId,'模型：均值模型\n');
fprintf(fileId,'均值：%.12g\n',meanValue);
fprintf(fileId,'标准差：%.12g\n',stdValue);
fprintf(fileId,'公式：%s\n',model.formula);
clear cleanupFile;

outputFiles = string({ ...
    fullfile(outputDir,'清洗后的拟合数据.csv'); ...
    fullfile(outputDir,'模型拟合评价表.csv'); ...
    fullfile(outputDir,'均值统计结果.csv'); ...
    textFile});
if exportFigures
    figureFiles = export_mean_figure(x,y,meanValue,stdValue,outputDir);
    outputFiles = [outputFiles;figureFiles];
end

result = struct( ...
    'cleaned_data',cleanedData, ...
    'models',model, ...
    'ranking_table',modelTable, ...
    'best_model',model, ...
    'output_dir',string(outputDir), ...
    'output_files',outputFiles, ...
    'export_figures',logical(exportFigures));
end

function values = get_table_column(tableData,columnName)
names = string(tableData.Properties.VariableNames);
[actualName,found] = find_column(names,columnName);
if ~found
    error('BestFit:MissingColumn','数据文件中不存在列%s。',columnName);
end
values = tableData{:,char(actualName)};
end

function files = export_mean_figure(x,y,meanValue,stdValue,outputDir)
figureHandle = figure('Visible','off','Color','w');
cleanupFigure = onCleanup(@() close_valid_figure(figureHandle));
scatter(x,y,42,'filled','MarkerFaceColor',[0.10,0.45,0.70]);
hold on;
yline(meanValue,'-','LineWidth',1.8,'Color',[0.80,0.20,0.15]);
yline(meanValue+stdValue,'--','LineWidth',1.1,'Color',[0.35,0.35,0.35]);
yline(meanValue-stdValue,'--','LineWidth',1.1,'Color',[0.35,0.35,0.35]);
grid on;
xlabel('质量损失率 \eta');
ylabel('强屈比 F_u/F_y');
title('强屈比均值与标准差');
legend('试验数据','均值','均值 + 标准差','均值 - 标准差', ...
    'Location','best');

pngFile = fullfile(outputDir,'均值统计图.png');
tifFile = fullfile(outputDir,'均值统计图.tif');
pdfFile = fullfile(outputDir,'均值统计图.pdf');
figFile = fullfile(outputDir,'均值统计图.fig');
exportgraphics(figureHandle,pngFile,'Resolution',600);
exportgraphics(figureHandle,tifFile,'Resolution',600);
exportgraphics(figureHandle,pdfFile,'ContentType','vector');
savefig(figureHandle,figFile);
files = string({pngFile;tifFile;pdfFile;figFile});
clear cleanupFigure;
close_valid_figure(figureHandle);
end

function close_valid_figure(figureHandle)
if isgraphics(figureHandle)
    close(figureHandle);
end
end

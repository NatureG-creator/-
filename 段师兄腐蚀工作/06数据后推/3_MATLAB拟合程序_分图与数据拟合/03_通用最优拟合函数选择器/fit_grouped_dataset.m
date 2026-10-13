function fitPackage = fit_grouped_dataset(data,material_column,x_column, ...
        metric_definitions,output_dir,model_choices,formula_digits)
%FIT_GROUPED_DATASET 按材料和指标调用通用选择器并保存统一结果。

if nargin < 6 || isempty(model_choices)
    model_choices = "auto";
end
if nargin < 7 || isempty(formula_digits)
    formula_digits = 4;
end
validateattributes(formula_digits,{'numeric'}, ...
    {'scalar','integer','nonnegative','finite'});
if ~istable(data)
    error('BestFit:InvalidData','data必须是table。');
end
requiredDefinitionColumns = ["Metric","Variable","ChineseName","DefaultModel"];
if ~all(ismember(requiredDefinitionColumns, ...
        string(metric_definitions.Properties.VariableNames)))
    error('BestFit:InvalidDefinitions', ...
        'metric_definitions必须包含Metric、Variable、ChineseName和DefaultModel。');
end
if ~isfolder(output_dir)
    mkdir(output_dir);
end

if isempty(material_column) || strlength(string(material_column)) == 0
    materials = "All";
    groupMasks = {true(height(data),1)};
else
    materialValues = string(data.(char(material_column)));
    materials = unique(materialValues,'stable');
    groupMasks = cell(numel(materials),1);
    for i = 1:numel(materials)
        groupMasks{i} = materialValues == materials(i);
    end
end

recordTemplate = struct( ...
    'Material',"",'Metric',"",'Variable',"",'ChineseName',"", ...
    'XVariable',string(x_column),'RequestedModel',"",'BestModel',"", ...
    'Parameters',[],'ParameterCount',0,'FormulaFull',"", ...
    'FormulaDisplay',"",'R2',NaN,'AdjustedR2',NaN,'RMSE',NaN, ...
    'SSE',NaN,'AIC',NaN,'AICc',NaN);
records = repmat(recordTemplate,numel(materials)*height(metric_definitions),1);

row = 0;
for materialIndex = 1:numel(materials)
    current = data(groupMasks{materialIndex},:);
    for metricIndex = 1:height(metric_definitions)
        row = row+1;
        metric = string(metric_definitions.Metric(metricIndex));
        variable = string(metric_definitions.Variable(metricIndex));
        label = string(metric_definitions.ChineseName(metricIndex));
        defaultModel = string(metric_definitions.DefaultModel(metricIndex));
        xSymbol = definition_value(metric_definitions,metricIndex, ...
            "XSymbol","x");
        ySymbol = definition_value(metric_definitions,metricIndex, ...
            "YSymbol","y");
        requestedModel = resolve_choice(model_choices,materials(materialIndex), ...
            metric,defaultModel,label);
        seriesDir = fullfile(output_dir,char(materials(materialIndex)),char(metric));

        if requestedModel == "均值模型"
            fitResult = fit_mean_series(current,x_column,variable,seriesDir);
        else
            fitResult = best_fit_selector(current,x_column,variable, ...
                seriesDir,false,requestedModel);
        end
        best = fitResult.best_model;

        records(row).Material = materials(materialIndex);
        records(row).Metric = metric;
        records(row).Variable = variable;
        records(row).ChineseName = label;
        records(row).XVariable = string(x_column);
        records(row).RequestedModel = requestedModel;
        records(row).BestModel = best.name;
        records(row).Parameters = double(best.parameters(:)');
        records(row).ParameterCount = best.parameter_count;
        records(row).FormulaFull = best.formula;
        records(row).FormulaDisplay = format_best_fit_formula( ...
            best.name,best.parameters,formula_digits,xSymbol,ySymbol);
        records(row).R2 = best.metrics.R2;
        records(row).AdjustedR2 = best.metrics.AdjustedR2;
        records(row).RMSE = best.metrics.RMSE;
        records(row).SSE = best.metrics.SSE;
        records(row).AIC = best.metrics.AIC;
        records(row).AICc = best.metrics.AICc;
    end
end

recordTable = records_to_table(records);
csvFile = fullfile(output_dir,'统一拟合结果.csv');
matFile = fullfile(output_dir,'统一拟合结果.mat');
writetable(recordTable,csvFile);
fitPackage = struct('records',records,'record_table',recordTable, ...
    'formula_digits',formula_digits,'csv_file',string(csvFile), ...
    'mat_file',string(matFile));
save(matFile,'fitPackage');
end

function value = definition_value(definitions,row,columnName,defaultValue)
if ismember(columnName,string(definitions.Properties.VariableNames))
    value = string(definitions.(char(columnName))(row));
else
    value = string(defaultValue);
end
end

function choice = resolve_choice(choices,material,metric,defaultModel,label)
if ischar(choices) || (isstring(choices) && isscalar(choices))
    mode = string(choices);
    if strcmpi(mode,"auto")
        choice = defaultModel;
    elseif strcmpi(mode,"prompt")
        choice = prompt_choice(material,metric,label,defaultModel);
    else
        choice = mode;
    end
elseif isstruct(choices)
    keys = string(fieldnames(choices));
    combinedKey = matlab.lang.makeValidName(material+"__"+metric);
    metricKey = matlab.lang.makeValidName(metric);
    index = find(strcmpi(keys,combinedKey),1);
    if isempty(index)
        index = find(strcmpi(keys,metricKey),1);
    end
    if isempty(index)
        choice = defaultModel;
    else
        choice = string(choices.(char(keys(index))));
    end
else
    error('BestFit:InvalidModelChoices', ...
        'model_choices必须为auto、prompt、模型名称或结构体。');
end
end

function choice = prompt_choice(material,metric,label,defaultModel)
options = ["自动选择最优函数";"线性函数";"二次函数";"幂函数"; ...
    "对数函数";"指数函数";"指数饱和函数";"双曲线饱和函数"; ...
    "连续两阶段幂函数";"两阶段对数模型";"均值模型"];
defaultIndex = find(options == defaultModel,1);
if isempty(defaultIndex)
    defaultIndex = 1;
end
[selection,confirmed] = listdlg('SelectionMode','single', ...
    'PromptString',sprintf('%s - %s（%s）',material,metric,label), ...
    'ListString',cellstr(options),'InitialValue',defaultIndex, ...
    'ListSize',[310,300],'Name','选择拟合函数');
if ~confirmed
    error('BestFit:SelectionCancelled','已取消拟合函数选择。');
end
choice = options(selection);
end

function result = fit_mean_series(data,xColumn,yColumn,outputDir)
x = double(data.(char(xColumn)));
y = double(data.(char(yColumn)));
valid = isfinite(x) & isfinite(y);
x = x(valid);
y = y(valid);
[x,order] = sort(x(:));
y = y(order);
meanValue = mean(y);
stdValue = std(y);
prediction = repmat(meanValue,size(y));
residual = y-prediction;
n = numel(y);
sse = sum(residual.^2);
rmse = sqrt(mean(residual.^2));
aic = n*log(max(sse/n,realmin))+2;
aicc = aic+4/max(n-2,1);
metrics = struct('R2',0,'AdjustedR2',0,'RMSE',rmse, ...
    'SSE',sse,'AIC',aic,'AICc',aicc);
model = struct('name',"均值模型", ...
    'formula',sprintf('y = %.10g (std = %.10g)',meanValue,stdValue), ...
    'parameters',[meanValue,stdValue],'parameter_count',1, ...
    'success',true,'status',"成功",'metrics',metrics);
if ~isfolder(outputDir)
    mkdir(outputDir);
end
writetable(table(x,y),fullfile(outputDir,'清洗后的拟合数据.csv'));
result = struct('cleaned_data',table(x,y),'best_model',model, ...
    'output_dir',string(outputDir));
end

function output = records_to_table(records)
n = numel(records);
Material = strings(n,1);
Metric = strings(n,1);
Variable = strings(n,1);
ChineseName = strings(n,1);
XVariable = strings(n,1);
RequestedModel = strings(n,1);
BestModel = strings(n,1);
ParameterCount = zeros(n,1);
P1 = nan(n,1); P2 = nan(n,1); P3 = nan(n,1); P4 = nan(n,1);
FormulaDisplay = strings(n,1);
R2 = nan(n,1); AdjustedR2 = nan(n,1); RMSE = nan(n,1);
SSE = nan(n,1); AIC = nan(n,1); AICc = nan(n,1);
for i = 1:n
    Material(i) = records(i).Material;
    Metric(i) = records(i).Metric;
    Variable(i) = records(i).Variable;
    ChineseName(i) = records(i).ChineseName;
    XVariable(i) = records(i).XVariable;
    RequestedModel(i) = records(i).RequestedModel;
    BestModel(i) = records(i).BestModel;
    ParameterCount(i) = records(i).ParameterCount;
    parameters = records(i).Parameters;
    if numel(parameters) >= 1, P1(i) = parameters(1); end
    if numel(parameters) >= 2, P2(i) = parameters(2); end
    if numel(parameters) >= 3, P3(i) = parameters(3); end
    if numel(parameters) >= 4, P4(i) = parameters(4); end
    FormulaDisplay(i) = records(i).FormulaDisplay;
    R2(i) = records(i).R2;
    AdjustedR2(i) = records(i).AdjustedR2;
    RMSE(i) = records(i).RMSE;
    SSE(i) = records(i).SSE;
    AIC(i) = records(i).AIC;
    AICc(i) = records(i).AICc;
end
output = table(Material,Metric,Variable,ChineseName,XVariable, ...
    RequestedModel,BestModel,ParameterCount,P1,P2,P3,P4, ...
    FormulaDisplay,R2,AdjustedR2,RMSE,SSE,AIC,AICc);
end

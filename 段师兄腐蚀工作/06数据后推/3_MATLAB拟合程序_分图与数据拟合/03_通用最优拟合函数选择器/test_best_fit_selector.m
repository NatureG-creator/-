function tests = test_best_fit_selector
tests = functiontests(localfunctions);
end

function testFourInputFormats(testCase)
workDir = makeWorkDir(testCase);
x = (1:8)';
y = 2*x+3;
source = table(x,y);

csvFile = fullfile(workDir,'data.csv');
xlsxFile = fullfile(workDir,'data.xlsx');
txtFile = fullfile(workDir,'data.txt');
matFile = fullfile(workDir,'data.mat');
writetable(source,csvFile);
writetable(source,xlsxFile);
writetable(source,txtFile,'Delimiter','\t');
save(matFile,'x','y');

files = {csvFile,xlsxFile,txtFile,matFile};
for i = 1:numel(files)
    result = best_fit_selector(files{i},"x","y", ...
        fullfile(workDir,"out"+i),false);
    verifyEqual(testCase,result.cleaned_data.x,x);
    verifyEqual(testCase,result.cleaned_data.y,y);
end
end

function testColumnNumbersAndCleaning(testCase)
workDir = makeWorkDir(testCase);
first = [1;2;NaN;4;5;6];
second = [3;5;7;Inf;11;13];
file = fullfile(workDir,'numbered.csv');
writetable(table(first,second),file);

result = best_fit_selector(file,1,2,fullfile(workDir,'out'),false);
verifyEqual(testCase,result.cleaned_data.x,[1;2;5;6]);
verifyEqual(testCase,result.cleaned_data.y,[3;5;11;13]);
end

function testInputErrors(testCase)
workDir = makeWorkDir(testCase);
x = (1:6)';
y = 2*x;
file = fullfile(workDir,'data.csv');
writetable(table(x,y),file);

verifyError(testCase,@() best_fit_selector(file,"bad","y", ...
    fullfile(workDir,'bad_column'),false),'BestFit:MissingColumn');

x = (1:3)';
y = 2*x;
shortFile = fullfile(workDir,'short.csv');
writetable(table(x,y),shortFile);
verifyError(testCase,@() best_fit_selector(shortFile,"x","y", ...
    fullfile(workDir,'short_out'),false),'BestFit:InsufficientData');
end

function testKnownLinearAndPowerModels(testCase)
workDir = makeWorkDir(testCase);
x = (1:20)';

y = 2*x+3;
linearFile = fullfile(workDir,'linear.csv');
writetable(table(x,y),linearFile);
linearResult = best_fit_selector(linearFile,"x","y", ...
    fullfile(workDir,'linear_out'),false);
verifyEqual(testCase,linearResult.best_model.name,"线性函数");
verifyEqual(testCase,linearResult.best_model.parameters,[2,3], ...
    'AbsTol',1e-8);

y = 1.7*x.^0.63;
powerFile = fullfile(workDir,'power.csv');
writetable(table(x,y),powerFile);
powerResult = best_fit_selector(powerFile,"x","y", ...
    fullfile(workDir,'power_out'),false);
verifyEqual(testCase,powerResult.best_model.name,"幂函数");
verifyEqual(testCase,powerResult.best_model.parameters,[1.7,0.63], ...
    'AbsTol',1e-5);
verifyGreaterThanOrEqual(testCase,height(powerResult.ranking_table),7);
end

function testContinuousTwoStagePowerModel(testCase)
workDir = makeWorkDir(testCase);
x = (1:20)';
expectedBreak = 8;
y = zeros(size(x));
left = x < expectedBreak;
y(left) = 1.4*x(left).^0.9;
y(~left) = 1.4*expectedBreak^(0.9-0.25).*x(~left).^0.25;
file = fullfile(workDir,'two_stage.csv');
writetable(table(x,y),file);

result = best_fit_selector(file,"x","y", ...
    fullfile(workDir,'out'),false);
verifyEqual(testCase,result.best_model.name,"连续两阶段幂函数");
parameters = result.best_model.parameters;
verifyLessThanOrEqual(testCase,abs(parameters(4)-expectedBreak),1);

leftValue = parameters(1)*parameters(4)^parameters(2);
rightValue = parameters(1)*parameters(4)^(parameters(2)-parameters(3)) ...
    *parameters(4)^parameters(3);
verifyEqual(testCase,leftValue,rightValue,'AbsTol',1e-10);
verifyEqual(testCase,height(result.ranking_table),9);
end

function testStrictTwoStageLogModelFromReferenceFormula(testCase)
workDir = makeWorkDir(testCase);
x = (0.01:0.01:0.20)';
expectedA = 0.55;
expectedB = 0.15;
expectedBreak = 0.08;
left = x < expectedBreak;
y = zeros(size(x));
y(left) = x(left).^expectedA;
y(~left) = expectedBreak.^(expectedA-expectedB).*x(~left).^expectedB;
file = fullfile(workDir,'strict_two_stage_log.csv');
writetable(table(x,y),file);

result = best_fit_selector(file,"x","y", ...
    fullfile(workDir,'out'),false);
modelIndex = find([result.models.name] == "两阶段对数模型",1);

verifyNotEmpty(testCase,modelIndex);
model = result.models(modelIndex);
verifyTrue(testCase,model.success);
verifyEqual(testCase,model.parameters(1),expectedA,'AbsTol',1e-5);
verifyEqual(testCase,model.parameters(2),expectedB,'AbsTol',1e-5);
verifyEqual(testCase,model.parameters(3),expectedBreak,'AbsTol',1e-12);
end

function testPositiveDomainModelsAreSkippedTogether(testCase)
workDir = makeWorkDir(testCase);
x = (-3:4)';
y = 2*x+10;
file = fullfile(workDir,'nonpositive.csv');
writetable(table(x,y),file);

result = best_fit_selector(file,"x","y", ...
    fullfile(workDir,'out'),false);
positiveModels = ["幂函数","对数函数","连续两阶段幂函数", ...
    "两阶段对数模型"];
for modelName = positiveModels
    row = result.ranking_table.Model == modelName;
    verifyFalse(testCase,any(result.ranking_table.Status(row) == "成功"));
end
end

function testExports(testCase)
workDir = makeWorkDir(testCase);
x = (1:12)';
y = 0.8*x.^0.6;
file = fullfile(workDir,'sample.csv');
outputDir = fullfile(workDir,'out');
writetable(table(x,y),file);

result = best_fit_selector(file,"x","y",outputDir,true);
expectedFiles = [ ...
    "模型拟合评价表.csv"; ...
    "最优拟合函数.txt"; ...
    "清洗后的拟合数据.csv"; ...
    "全部模型拟合对比图.png"; ...
    "全部模型拟合对比图.tif"; ...
    "全部模型拟合对比图.pdf"; ...
    "全部模型拟合对比图.fig"; ...
    "最优模型拟合图.png"; ...
    "最优模型拟合图.tif"; ...
    "最优模型拟合图.pdf"; ...
    "最优模型拟合图.fig"; ...
    "最优模型残差图.png"; ...
    "最优模型残差图.tif"; ...
    "最优模型残差图.pdf"; ...
    "最优模型残差图.fig"];

verifyEqual(testCase,string(result.output_dir),string(outputDir));
verifyEqual(testCase,sort(result.output_files), ...
    sort(fullfile(string(outputDir),expectedFiles)));
for fileName = expectedFiles'
    filePath = fullfile(outputDir,fileName);
    verifyTrue(testCase,isfile(filePath));
    info = dir(filePath);
    verifyGreaterThan(testCase,info.bytes,0);
end
end

function testDeliveryFilesAndExample(testCase)
toolFolder = fileparts(mfilename('fullpath'));
entryFile = fullfile(toolFolder,'run_best_fit_selector.m');
exampleFile = fullfile(toolFolder,'example_fit_data.csv');
guideFile = fullfile(toolFolder,'使用说明.md');
verifyTrue(testCase,isfile(entryFile));
verifyTrue(testCase,isfile(exampleFile));
verifyTrue(testCase,isfile(guideFile));

workDir = makeWorkDir(testCase);
result = best_fit_selector(exampleFile,"x","y", ...
    fullfile(workDir,'example_out'),false);
verifyEqual(testCase,height(result.cleaned_data),9);
verifyEqual(testCase,height(result.ranking_table),9);
verifyTrue(testCase,isfile(fullfile(result.output_dir, ...
    '模型拟合评价表.csv')));
end

function testAutoDetectsAllCorrosionMechanicalMetrics(testCase)
workDir = makeWorkDir(testCase);
Eta = (0.01:0.01:0.08)';
EpsilonH = 0.02+0.01*Eta;
EpsilonU = 0.18-0.20*Eta;
EpsilonF = 0.34-0.90*Eta;
E_MPa = 195000-140000*Eta;
Material = repmat("Q370NH",numel(Eta),1);
file = fullfile(workDir,'q370.csv');
writetable(table(Material,Eta,EpsilonH,EpsilonU,EpsilonF,E_MPa),file);

result = best_fit_selector_auto(file,fullfile(workDir,'auto_out'),false);

verifyEqual(testCase,result.data_type,"腐蚀后应变弹模数据");
verifyEqual(testCase,result.x_column,"Eta");
verifyEqual(testCase,result.metrics, ...
    ["EpsilonH";"EpsilonU";"EpsilonF";"E_MPa"]);
verifyEqual(testCase,numel(result.results),4);
verifyEqual(testCase,height(result.summary_table),4);
verifyTrue(testCase,isfile(fullfile(result.output_dir,'自动拟合汇总.csv')));
for i = 1:numel(result.metrics)
    metricDir = fullfile(result.output_dir,result.metrics(i));
    verifyTrue(testCase,isfolder(metricDir));
    verifyTrue(testCase,isfile(fullfile(metricDir,'模型拟合评价表.csv')));
end
end

function testAutoConvertsEtaPercentToDecimalEta(testCase)
workDir = makeWorkDir(testCase);
EtaPercent = (1:8)';
EpsilonU = 0.18-0.002*EtaPercent;
file = fullfile(workDir,'percent.csv');
writetable(table(EtaPercent,EpsilonU),file);

result = best_fit_selector_auto(file,fullfile(workDir,'auto_out'),false);

verifyEqual(testCase,result.x_column,"Eta");
verifyEqual(testCase,result.results{1}.cleaned_data.x, ...
    EtaPercent/100,'AbsTol',1e-12);
end

function testAutoRejectsPreviouslyFittedParameterTable(testCase)
workDir = makeWorkDir(testCase);
Material = "Q370NH";
Metric = "ElasticModulus";
Model = "Linear";
Intercept = 195610;
Slope = -142430;
R2 = 0.27;
RMSE = 7264;
Formula = "y = 195610 - 142430*eta";
file = fullfile(workDir,'parameters.csv');
writetable(table(Material,Metric,Model,Intercept,Slope,R2,RMSE,Formula),file);

verifyError(testCase,@() best_fit_selector_auto( ...
    file,fullfile(workDir,'auto_out'),false), ...
    'BestFit:ResultFileNotRawData');
end

function testAutoFallsBackToGenericXYColumns(testCase)
workDir = makeWorkDir(testCase);
x = (1:8)';
y = 3*x+2;
file = fullfile(workDir,'generic.csv');
writetable(table(x,y),file);

result = best_fit_selector_auto(file,fullfile(workDir,'auto_out'),false);

verifyEqual(testCase,result.data_type,"通用x-y数据");
verifyEqual(testCase,result.metrics,"y");
verifyEqual(testCase,numel(result.results),1);
end

function testAutoDetectsAllStrengthMetricsAndUsesMeanForRatio(testCase)
workDir = makeWorkDir(testCase);
Eta = (0.01:0.01:0.08)';
Fy_MPa = 455-500*Eta;
Fu_MPa = 575-620*Eta;
Ff_MPa = 415-240*Eta;
StrengthRatio = Fu_MPa./Fy_MPa;
Material = repmat("Q370NH",numel(Eta),1);
file = fullfile(workDir,'strength.csv');
writetable(table(Material,Eta,Fy_MPa,Fu_MPa,Ff_MPa,StrengthRatio),file);

result = best_fit_selector_auto(file,fullfile(workDir,'auto_out'),false);

verifyEqual(testCase,result.data_type,"腐蚀后强度指标数据");
verifyEqual(testCase,result.metrics, ...
    ["Fy_MPa";"Fu_MPa";"Ff_MPa";"StrengthRatio"]);
verifyEqual(testCase,numel(result.results),4);
verifyEqual(testCase,result.results{4}.best_model.name,"均值模型");
verifyEqual(testCase,result.results{4}.best_model.parameters(1), ...
    mean(StrengthRatio),'AbsTol',1e-12);
verifyEqual(testCase,result.results{4}.best_model.parameters(2), ...
    std(StrengthRatio),'AbsTol',1e-12);
verifyTrue(testCase,isfile(fullfile(result.output_dir, ...
    'StrengthRatio','均值统计结果.csv')));
end

function testCoreSelectorCanForceOneModel(testCase)
workDir = makeWorkDir(testCase);
x = (1:12)';
y = 2*x.^2+3*x+1;
file = fullfile(workDir,'quadratic.csv');
writetable(table(x,y),file);

result = best_fit_selector(file,"x","y", ...
    fullfile(workDir,'forced_linear'),false,"线性函数");

verifyEqual(testCase,result.best_model.name,"线性函数");
verifyEqual(testCase,height(result.ranking_table),1);
verifyEqual(testCase,result.requested_model,"线性函数");
end

function testAutoSelectorUsesIndependentChoicesPerMetric(testCase)
workDir = makeWorkDir(testCase);
Eta = (0.01:0.01:0.08)';
EpsilonH = 0.02+0.03*Eta;
EpsilonU = 0.18-0.2*Eta+0.5*Eta.^2;
EpsilonF = 0.30-0.4*Eta;
E_MPa = 195000*exp(-0.5*Eta);
file = fullfile(workDir,'mechanical.csv');
writetable(table(Eta,EpsilonH,EpsilonU,EpsilonF,E_MPa),file);

choices = struct( ...
    'EpsilonH',"线性函数", ...
    'EpsilonU',"二次函数", ...
    'EpsilonF',"均值模型", ...
    'E_MPa',"指数函数");
result = best_fit_selector_auto( ...
    file,fullfile(workDir,'auto_out'),false,choices);

verifyEqual(testCase,result.selected_models, ...
    ["线性函数";"二次函数";"均值模型";"指数函数"]);
verifyEqual(testCase,result.results{1}.best_model.name,"线性函数");
verifyEqual(testCase,result.results{2}.best_model.name,"二次函数");
verifyEqual(testCase,result.results{3}.best_model.name,"均值模型");
verifyEqual(testCase,result.results{4}.best_model.name,"指数函数");
end

function testForcedModelRejectsUnknownName(testCase)
workDir = makeWorkDir(testCase);
x = (1:8)';
y = 2*x+1;
file = fullfile(workDir,'data.csv');
writetable(table(x,y),file);

verifyError(testCase,@() best_fit_selector(file,"x","y", ...
    fullfile(workDir,'bad'),false,"不存在的函数"), ...
    'BestFit:UnknownModel');
end

function testUnifiedModelEvaluationAndFormulaDigits(testCase)
x = [1;2;3];
models = { ...
    "线性函数",[2,3],2*x+3; ...
    "二次函数",[1,2,3],x.^2+2*x+3; ...
    "幂函数",[2,0.5],2*x.^0.5; ...
    "对数函数",[2,3],2*log(x)+3; ...
    "指数函数",[2,0.1],2*exp(0.1*x); ...
    "指数饱和函数",[2,0.1,3],2*(1-exp(-0.1*x))+3; ...
    "双曲线饱和函数",[2,0.5,3],2*x./(0.5+x)+3; ...
    "连续两阶段幂函数",[2,1,0.5,2], ...
        [2;4;2*2^(1-0.5)*3^0.5]; ...
    "两阶段对数模型",[1,0.5,2], ...
        [1;2;2^(1-0.5)*3^0.5]; ...
    "均值模型",[4,0.2],[4;4;4]};
for i = 1:size(models,1)
    actual = evaluate_best_fit_model(models{i,1},models{i,2},x);
    verifyEqual(testCase,actual,models{i,3},'AbsTol',1e-12);
end

formula2 = format_best_fit_formula( ...
    "线性函数",[1.23456,-0.34567],2,"eta","y");
formula4 = format_best_fit_formula( ...
    "线性函数",[1.23456,-0.34567],4,"eta","y");
verifyEqual(testCase,formula2,"y = 1.23*eta - 0.35");
verifyEqual(testCase,formula4,"y = 1.2346*eta - 0.3457");
end

function testGroupedDatasetSeparatesMaterialsAndSavesFullPrecision(testCase)
workDir = makeWorkDir(testCase);
x = (1:8)';
Material = [repmat("Q370NH",8,1);repmat("Q355",8,1)];
Time_day = [x;x];
Mean_percent = [2*x+1;3*x+2];
data = table(Material,Time_day,Mean_percent);
definitions = table("MassLoss","Mean_percent","质量损失率", ...
    "线性函数",'VariableNames', ...
    {'Metric','Variable','ChineseName','DefaultModel'});

package = fit_grouped_dataset(data,"Material","Time_day", ...
    definitions,workDir,"auto",3);

verifyEqual(testCase,numel(package.records),2);
verifyTrue(testCase,isfile(package.mat_file));
verifyTrue(testCase,isfile(package.csv_file));
q370 = find_best_fit_record(package,"Q370NH","MassLoss");
q355 = find_best_fit_record(package,"Q355","MassLoss");
verifyEqual(testCase,q370.Parameters,[2,1],'AbsTol',1e-10);
verifyEqual(testCase,q355.Parameters,[3,2],'AbsTol',1e-10);
verifyEqual(testCase,q370.FormulaDisplay,"y = 2.000*x + 1.000");
verifyEqual(testCase,evaluate_best_fit_model( ...
    q370.BestModel,q370.Parameters,2.5),6,'AbsTol',1e-10);
end

function workDir = makeWorkDir(testCase)
workDir = tempname;
mkdir(workDir);
testCase.addTeardown(@() removeWorkDir(workDir));
end

function removeWorkDir(workDir)
if isfolder(workDir)
    rmdir(workDir,'s');
end
end

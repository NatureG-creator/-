function result = generate_strength_property_fits( ...
        fit_target,output_dir,export_figures,model_choices,formula_digits)
%GENERATE_STRENGTH_PROPERTY_FITS 拟合腐蚀后强度指标。

if nargin < 1 || isempty(fit_target)
    fit_target = 'both';
end
if nargin < 2 || isempty(output_dir)
    output_dir = pwd;
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

[materials,outputPrefix] = parse_target(fit_target);
if ~isfolder(output_dir)
    mkdir(output_dir);
end

sourceFolder = fileparts(mfilename('fullpath'));
selectorFolder = fullfile(fileparts(sourceFolder), ...
    '03_通用最优拟合函数选择器');
addpath(selectorFolder);
sourceFile = fullfile(sourceFolder,'strength_property_data.csv');
allData = readtable(sourceFile,'TextType','string');
plotData = allData(ismember(allData.Material,materials),:);
plotData.Eta = plotData.EtaPercent/100;
plotData.StrengthRatio = plotData.Fu_MPa./plotData.Fy_MPa;

definitions = table( ...
    ["YieldStrength";"TensileStrength";"StrengthRatio";"FractureStrength"], ...
    ["Fy_MPa";"Fu_MPa";"StrengthRatio";"Ff_MPa"], ...
    ["屈服强度";"抗拉强度";"强屈比";"断裂强度"], ...
    ["自动选择最优函数";"自动选择最优函数"; ...
    "均值模型";"自动选择最优函数"], ...
    repmat("eta",4,1),["f_y";"f_u";"f_u/f_y";"f_f"], ...
    'VariableNames',{'Metric','Variable','ChineseName','DefaultModel', ...
    'XSymbol','YSymbol'});
fitOutputDir = fullfile(output_dir,'03_统一拟合结果');
fitPackage = fit_grouped_dataset(plotData,"Material","Eta", ...
    definitions,fitOutputDir,model_choices,formula_digits);
fitParameters = build_legacy_strength_table(fitPackage);
parameterFile = fullfile(output_dir, ...
    [outputPrefix '_强度指标拟合参数.csv']);
dataFile = fullfile(output_dir, ...
    [outputPrefix '_强度指标绘图数据.csv']);
writetable(fitParameters,parameterFile);
writetable(plotData,dataFile);

figureFiles = strings(0,1);
if export_figures
    figureFiles = export_strength_figures( ...
        plotData,fitPackage,materials,outputPrefix,output_dir);
end

result = struct('materials',materials,'plot_data',plotData, ...
    'fit_parameters',fitParameters, ...
    'fit_package',fitPackage, ...
    'parameter_file',string(parameterFile), ...
    'data_file',string(dataFile),'figure_files',figureFiles);
end

function [materials,outputPrefix] = parse_target(fitTarget)
target = lower(strtrim(string(fitTarget)));
switch target
    case {"q370nh","q370"}
        materials = "Q370NH";
        outputPrefix = 'Q370NH';
    case "q355"
        materials = "Q355";
        outputPrefix = 'Q355';
    case "both"
        materials = ["Q370NH";"Q355"];
        outputPrefix = 'Q370NH_Q355';
    otherwise
        error('StrengthFit:InvalidTarget', ...
            'fit_target必须为Q370NH、Q370、Q355或both。');
end
end

function fitTable = build_legacy_strength_table(fitPackage)
records = fitPackage.records;
rowCount = numel(records);
Material = strings(rowCount,1);
Metric = strings(rowCount,1);
Model = strings(rowCount,1);
Intercept = nan(rowCount,1);
Slope = nan(rowCount,1);
R2 = nan(rowCount,1);
RMSE = nan(rowCount,1);
Mean = nan(rowCount,1);
Std = nan(rowCount,1);
Formula = strings(rowCount,1);

for row = 1:rowCount
    record = records(row);
    Material(row) = record.Material;
    Metric(row) = record.Metric;
    Model(row) = record.BestModel;
    R2(row) = record.R2;
    RMSE(row) = record.RMSE;
    Formula(row) = record.FormulaDisplay;
    if record.BestModel == "线性函数"
        Slope(row) = record.Parameters(1);
        Intercept(row) = record.Parameters(2);
    elseif record.BestModel == "均值模型"
        Mean(row) = record.Parameters(1);
        if numel(record.Parameters) >= 2
            Std(row) = record.Parameters(2);
        end
    end
end

fitTable = table(Material,Metric,Model,Intercept,Slope,R2,RMSE, ...
    Mean,Std,Formula);
end

function files = export_strength_figures(data,fitPackage,materials, ...
        outputPrefix,outputDir)
definitions = { ...
    "YieldStrength","Fy_MPa",'屈服强度拟合图', ...
        'Yield strength, f_y (MPa)',[350 465]; ...
    "TensileStrength","Fu_MPa",'抗拉强度拟合图', ...
        'Tensile strength, f_u (MPa)',[480 580]; ...
    "StrengthRatio","StrengthRatio",'屈强比统计图', ...
        'Tensile-to-yield strength ratio, f_u/f_y',[1.24 1.41]; ...
    "FractureStrength","Ff_MPa",'断裂强度拟合图', ...
        'Fracture strength, f_f (MPa)',[330 445]};
files = strings(size(definitions,1)*4,1);

for definitionIndex = 1:size(definitions,1)
    metric = definitions{definitionIndex,1};
    variable = definitions{definitionIndex,2};
    figureName = definitions{definitionIndex,3};
    yLabel = definitions{definitionIndex,4};
    yLimits = definitions{definitionIndex,5};

    fig = create_figure();
    figureCleanup = onCleanup(@() close_valid_figure(fig));
    layout = tiledlayout(fig,1,1,'Padding','compact');
    ax = nexttile(layout);
    hold(ax,'on');
    legendHandles = gobjects(2*numel(materials),1);
    legendLabels = strings(2*numel(materials),1);

    for materialIndex = 1:numel(materials)
        material = materials(materialIndex);
        current = data(data.Material == material,:);
        style = material_style(material);
        record = find_best_fit_record(fitPackage,material,metric);
        values = current.(variable);
        legendHandles(2*materialIndex-1) = plot(ax, ...
            current.EtaPercent,values,style.marker, ...
            'LineStyle','none','MarkerSize',5.5, ...
            'MarkerFaceColor',style.color, ...
            'MarkerEdgeColor',style.color);

        xPercent = linspace(0,15,400)';
        eta = xPercent/100;
        fitted = evaluate_best_fit_model( ...
            record.BestModel,record.Parameters,eta);
        annotation = sprintf('%s: %s\nR^2 = %.3f', ...
            material,tex_formula(record.FormulaDisplay),record.R2);
        legendHandles(2*materialIndex) = plot(ax,xPercent,fitted, ...
            style.lineStyle,'Color',style.color,'LineWidth',1.5);
        legendLabels(2*materialIndex-1) = material+" test data";
        if metric == "StrengthRatio"
            legendLabels(2*materialIndex) = material+" mean";
        else
            legendLabels(2*materialIndex) = material+" fitting line";
        end

        textX = 1.4;
        if metric == "StrengthRatio"
            if material == "Q355"
                textX = 5.0;
                textY = yLimits(2)-0.10*range(yLimits);
            else
                textY = yLimits(1)+0.08*range(yLimits);
            end
        else
            if material == "Q355"
                textY = yLimits(1)+0.10*range(yLimits);
            else
                textY = yLimits(2)-0.10*range(yLimits);
            end
        end
        text(ax,textX,textY,annotation,'Color',style.color, ...
            'FontName','Times New Roman','FontSize',9, ...
            'Interpreter','tex');
    end

    format_axes(ax,[0 15],yLimits);
    xlabel(ax,'Mass loss rate, \eta (%)','Interpreter','tex');
    ylabel(ax,yLabel,'Interpreter','tex');
    legend(ax,legendHandles,cellstr(legendLabels), ...
        'Location','northeast','Box','off', ...
        'FontName','Times New Roman','FontSize',8.5);
    outputBase = fullfile(outputDir,[outputPrefix '_' figureName]);
    fileRows = (definitionIndex-1)*4+(1:4);
    files(fileRows) = export_figure(fig,outputBase);
    close(fig);
    clear figureCleanup;
end
end

function formula = tex_formula(formula)
formula = char(string(formula));
formula = strrep(formula,'eta','\eta');
formula = strrep(formula,'lambdaq','\lambda_q');
formula = strrep(formula,'Hq','H_q');
end

function style = material_style(material)
if material == "Q370NH"
    style = struct('color',[1 0 0],'marker','d','lineStyle','-');
else
    style = struct('color',[0 0 1],'marker','o','lineStyle','--');
end
end

function fig = create_figure()
fig = figure('Visible','off','Color','w','Units','centimeters', ...
    'Position',[5 5 14.5 10.5]);
end

function format_axes(ax,xLimits,yLimits)
xlim(ax,xLimits);
ylim(ax,yLimits);
xticks(ax,0:5:15);
set(ax,'FontName','Times New Roman','FontSize',10.5, ...
    'LineWidth',1.0,'Box','on','TickDir','in', ...
    'XMinorTick','on','YMinorTick','on');
grid(ax,'off');
end

function files = export_figure(fig,outputBase)
pngFile = [outputBase '.png'];
tifFile = [outputBase '.tif'];
pdfFile = [outputBase '.pdf'];
figFile = [outputBase '.fig'];
drawnow;
exportgraphics(fig,pngFile,'Resolution',600);
exportgraphics(fig,tifFile,'Resolution',600);
exportgraphics(fig,pdfFile,'ContentType','vector');
savefig(fig,figFile);
files = string({pngFile;tifFile;pdfFile;figFile});
end

function close_valid_figure(fig)
if isgraphics(fig)
    close(fig);
end
end

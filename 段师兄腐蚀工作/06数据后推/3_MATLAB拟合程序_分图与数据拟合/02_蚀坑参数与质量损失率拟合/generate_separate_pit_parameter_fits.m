function result = generate_separate_pit_parameter_fits( ...
    fit_target,output_dir,export_figures,model_choices,formula_digits)
%GENERATE_SEPARATE_PIT_PARAMETER_FITS 根据表格数据拟合并分别绘图。
% 蚀坑深度模型：Hq = a*eta^b
% 径深比模型：lambdaq = a-b*ln(eta)
% 两种钢材的质量损失率均采用1号、2号试件平均值。

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

source_folder = fileparts(mfilename('fullpath'));
selector_folder = fullfile(fileparts(source_folder), ...
    '03_通用最优拟合函数选择器');
addpath(selector_folder);

target = lower(strtrim(string(fit_target)));
switch target
    case "q370nh"
        selected = 1;
        output_prefix = 'Q370NH';
    case "q355"
        selected = 2;
        output_prefix = 'Q355';
    case "both"
        selected = [1,2];
        output_prefix = 'Q370NH_Q355';
    otherwise
        error('PitFit:InvalidTarget', ...
            ['fit_target必须为''Q370NH''、''Q355''或''both''，' ...
             '当前输入为''%s''。'],char(string(fit_target)));
end

if ~isfolder(output_dir)
    mkdir(output_dir);
end

%% 1. 原始数据
days = [5;10;15;20;30;40;60;80;100];

eta_Q370NH_1 = [2.01;2.35;4.05;5.23;6.42;6.44;10.13;10.09;11.46];
eta_Q370NH_2 = [1.20;2.85;4.74;5.47;6.37;6.55;9.52;9.40;10.19];
eta_Q370NH = mean([eta_Q370NH_1,eta_Q370NH_2],2);

eta_Q355_1 = [1.80;2.01;3.35;4.04;4.74;5.21;8.77;9.47;14.10];
eta_Q355_2 = [2.39;3.24;3.04;3.70;4.90;5.91;8.77;9.93;7.44];
eta_Q355 = mean([eta_Q355_1,eta_Q355_2],2);

Hq_Q370NH = [3.75;4.05;4.40;5.04;4.83;4.97;5.50;5.36;5.59];
Hq_Q355 = [3.94;4.17;4.65;4.50;4.79;5.02;5.05;5.49;5.46];

lambda_Q370NH = [3.58;3.26;2.80;2.33;2.43;2.21;1.69;1.86;1.56];
lambda_Q355 = [3.44;3.09;3.44;2.93;2.60;2.37;2.12;2.05;1.92];

data(1) = struct('name',"Q370NH",'eta',eta_Q370NH, ...
    'Hq',Hq_Q370NH,'lambda',lambda_Q370NH, ...
    'color',[0 0 1],'marker','o','lineStyle','-');
data(2) = struct('name',"Q355",'eta',eta_Q355, ...
    'Hq',Hq_Q355,'lambda',lambda_Q355, ...
    'color',[1 0 0],'marker','s','lineStyle','--');

%% 2. 使用03通用选择器拟合
fit_data = table;
for k = 1:numel(selected)
    current = data(selected(k));
    part = table(repmat(current.name,numel(days),1),days,current.eta, ...
        current.Hq,current.lambda,'VariableNames', ...
        {'Material','CorrosionTime_day','MassLossMean_percent', ...
        'Hq_mean','Lambdaq_mean'});
    fit_data = [fit_data;part]; %#ok<AGROW>
end
definitions = table( ...
    ["PitDepth";"AspectRatio"], ...
    ["Hq_mean";"Lambdaq_mean"], ...
    ["蚀坑深度";"径深比"], ...
    ["自动选择最优函数";"自动选择最优函数"], ...
    ["eta";"eta"],["Hq";"lambdaq"], ...
    'VariableNames',{'Metric','Variable','ChineseName','DefaultModel', ...
    'XSymbol','YSymbol'});
fit_output_dir = fullfile(output_dir,'03_统一拟合结果');
fit_package = fit_grouped_dataset(fit_data,"Material", ...
    "MassLossMean_percent",definitions,fit_output_dir, ...
    model_choices,formula_digits);

for k = 1:numel(selected)
    index = selected(k);
    data(index).depthRecord = find_best_fit_record( ...
        fit_package,data(index).name,"PitDepth");
    data(index).aspectRecord = find_best_fit_record( ...
        fit_package,data(index).name,"AspectRatio");
    data(index).depthP = data(index).depthRecord.Parameters;
    data(index).aspectP = data(index).aspectRecord.Parameters;
    data(index).depthR2 = data(index).depthRecord.R2;
    data(index).aspectR2 = data(index).aspectRecord.R2;
end

nSelected = numel(selected);
materials = strings(nSelected,1);

for k = 1:nSelected
    current = data(selected(k));
    materials(k) = current.name;

    fprintf('\n%s蚀坑深度模型：%s\n', ...
        current.name,current.depthRecord.BestModel);
    fprintf('公式：%s，R^2 = %.6f\n', ...
        current.depthRecord.FormulaDisplay,current.depthR2);
    fprintf('%s径深比模型：%s\n', ...
        current.name,current.aspectRecord.BestModel);
    fprintf('公式：%s，R^2 = %.6f\n', ...
        current.aspectRecord.FormulaDisplay,current.aspectR2);
end
fprintf('\n');

%% 3. 分别绘制两张图
depth_figure_files = strings(0,1);
aspect_figure_files = strings(0,1);
if export_figures
    eta_fit = linspace(1.4,11.3,500);

    depth_fig = create_figure();
    depth_ax = axes(depth_fig);
    draw_fit(depth_ax,data,selected,eta_fit,'depth');
    format_axis(depth_ax,[0 12],[3.5 5.9]);
    xlabel(depth_ax,'Mass loss rate, \eta (%)','Interpreter','tex');
    ylabel(depth_ax,'Pit depth, H_q','Interpreter','tex');
    depth_base = fullfile(output_dir, ...
        [output_prefix '_蚀坑深度与质量损失率拟合图']);
    depth_figure_files = export_figure(depth_fig,depth_base);

    aspect_fig = create_figure();
    aspect_ax = axes(aspect_fig);
    draw_fit(aspect_ax,data,selected,eta_fit,'aspect');
    format_axis(aspect_ax,[0 12],[1.2 3.9]);
    xlabel(aspect_ax,'Mass loss rate, \eta (%)','Interpreter','tex');
    ylabel(aspect_ax,'Pit aspect ratio, \lambda_q','Interpreter','tex');
    aspect_base = fullfile(output_dir, ...
        [output_prefix '_径深比与质量损失率拟合图']);
    aspect_figure_files = export_figure(aspect_fig,aspect_base);
end

%% 4. 分别保存两类拟合参数
depth_table = fit_package.record_table( ...
    fit_package.record_table.Metric == "PitDepth",:);
depth_parameter_file = fullfile(output_dir, ...
    [output_prefix '_蚀坑深度拟合参数.csv']);
writetable(depth_table,depth_parameter_file);

aspect_table = fit_package.record_table( ...
    fit_package.record_table.Metric == "AspectRatio",:);
aspect_parameter_file = fullfile(output_dir, ...
    [output_prefix '_径深比拟合参数.csv']);
writetable(aspect_table,aspect_parameter_file);

plot_data = table;
for k = 1:nSelected
    current = data(selected(k));
    part = table(repmat(current.name,numel(days),1),days,current.eta, ...
        current.Hq,current.lambda, ...
        'VariableNames',{'Material','CorrosionTime_day', ...
        'MassLossMean_percent','Hq_mean','Lambdaq_mean'});
    plot_data = [plot_data;part]; %#ok<AGROW>
end
data_file = fullfile(output_dir, ...
    [output_prefix '_蚀坑参数拟合数据.csv']);
writetable(plot_data,data_file);

depth_coefficients = struct;
aspect_coefficients = struct;
for k = 1:nSelected
    current = data(selected(k));
    depth_coefficients.(char(current.name)) = current.depthP;
    aspect_coefficients.(char(current.name)) = current.aspectP;
end

result = struct('materials',materials, ...
    'mass_loss_Q370NH',eta_Q370NH, ...
    'mass_loss_Q355',eta_Q355, ...
    'depth_coefficients',depth_coefficients, ...
    'aspect_coefficients',aspect_coefficients, ...
    'fit_package',fit_package, ...
    'depth_parameter_file',string(depth_parameter_file), ...
    'aspect_parameter_file',string(aspect_parameter_file), ...
    'data_file',string(data_file), ...
    'depth_figure_files',depth_figure_files, ...
    'aspect_figure_files',aspect_figure_files);

disp(['结果已保存到：' char(output_dir)]);
end

function fig = create_figure()
fig = figure('Color','w','Units','centimeters', ...
    'Position',[5 5 14.5 10.5]);
end

function draw_fit(ax,data,selected,eta_fit,parameter_type)
hold(ax,'on');
nSelected = numel(selected);
handles = gobjects(2*nSelected,1);
labels = strings(2*nSelected,1);

for k = 1:nSelected
    current = data(selected(k));
    if strcmp(parameter_type,'depth')
        observed = current.Hq;
        fitted = evaluate_best_fit_model(current.depthRecord.BestModel, ...
            current.depthRecord.Parameters,eta_fit);
    else
        observed = current.lambda;
        fitted = evaluate_best_fit_model(current.aspectRecord.BestModel, ...
            current.aspectRecord.Parameters,eta_fit);
    end

    handles(2*k-1) = plot(ax,current.eta,observed,current.marker, ...
        'LineStyle','none','MarkerSize',6.0, ...
        'MarkerFaceColor',current.color,'MarkerEdgeColor',current.color);
    handles(2*k) = plot(ax,eta_fit,fitted,current.lineStyle, ...
        'Color',current.color,'LineWidth',1.5);
    labels(2*k-1) = current.name + " data";
    labels(2*k) = current.name + " fitting curve";
end

legend(ax,handles,cellstr(labels),'Location','best', ...
    'Box','off','FontName','Times New Roman','FontSize',9);
end

function format_axis(ax,xLimits,yLimits)
xlim(ax,xLimits);
ylim(ax,yLimits);
xticks(ax,0:2:12);
set(ax,'FontName','Times New Roman','FontSize',11, ...
    'LineWidth',1.0,'Box','on','TickDir','in', ...
    'XMinorTick','off','YMinorTick','off');
grid(ax,'off');
end

function files = export_figure(fig,output_base)
exportgraphics(fig,[output_base '.png'],'Resolution',600);
exportgraphics(fig,[output_base '.tif'],'Resolution',600);
exportgraphics(fig,[output_base '.pdf'],'ContentType','vector');
savefig(fig,[output_base '.fig']);
files = string(output_base) + [".png";".tif";".pdf";".fig"];
end

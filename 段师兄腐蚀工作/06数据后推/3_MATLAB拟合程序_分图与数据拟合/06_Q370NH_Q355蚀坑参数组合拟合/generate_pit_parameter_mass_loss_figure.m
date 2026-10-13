function result = generate_pit_parameter_mass_loss_figure( ...
    fit_target,mass_loss_mode,output_dir,export_figures, ...
    model_choices,formula_digits)
%GENERATE_PIT_PARAMETER_MASS_LOSS_FIGURE 绘制蚀坑参数与质量损失率关系。
% 拟合公式取自第2章Word文档：
% Q370NH: Hq = 3.31*eta^0.22
% Q355:   Hq = 3.50*eta^0.18
% Q370NH: lambdaq = 5.52 - 1.60*eta^0.39
% Q355:   lambdaq = 5.48 - 1.54*eta^0.34

if nargin < 1 || isempty(fit_target)
    fit_target = 'both';
end
if nargin < 2 || isempty(mass_loss_mode)
    mass_loss_mode = 'original_figure';
end
if nargin < 3 || isempty(output_dir)
    output_dir = pwd;
end
if nargin < 4
    export_figures = true;
end
if nargin < 5 || isempty(model_choices)
    model_choices = "auto";
end
if nargin < 6 || isempty(formula_digits)
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

mode = lower(strtrim(string(mass_loss_mode)));
if mode ~= "original_figure" && mode ~= "mean"
    error('PitFit:InvalidMassLossMode', ...
        ['mass_loss_mode必须为''original_figure''或''mean''，' ...
         '当前输入为''%s''。'],char(string(mass_loss_mode)));
end

if ~isfolder(output_dir)
    mkdir(output_dir);
end

%% 1. 质量损失率数据
days = [5;10;15;20;30;40;60;80;100];

eta_Q370NH_1 = [2.01;2.35;4.05;5.23;6.42;6.44;10.13;10.09;11.46];
eta_Q370NH_2 = [1.20;2.85;4.74;5.47;6.37;6.55;9.52;9.40;10.19];
eta_Q370NH_mean = mean([eta_Q370NH_1,eta_Q370NH_2],2);

eta_Q355_1 = [1.80;2.01;3.35;4.04;4.74;5.21;8.77;9.47;14.10];
eta_Q355_2 = [2.39;3.24;3.04;3.70;4.90;5.91;8.77;9.93;7.44];
eta_Q355_mean = mean([eta_Q355_1,eta_Q355_2],2);

% 原图中Q370NH采用两试件平均值，Q355点位与1号试件相符。
if mode == "original_figure"
    eta_Q370NH = eta_Q370NH_mean;
    eta_Q355 = eta_Q355_1;
    mode_suffix = '';
else
    eta_Q370NH = eta_Q370NH_mean;
    eta_Q355 = eta_Q355_mean;
    mode_suffix = '_两试件平均';
end

%% 2. 表2-5蚀坑参数整体统计结果
Hq_Q355 = [3.94;4.17;4.65;4.50;4.79;5.02;5.05;5.49;5.46];
Hq_sigma_Q355 = [0.23;0.24;0.26;0.34;0.27;0.22;0.29;0.29;0.23];
lambda_Q355 = [3.44;3.09;3.44;2.93;2.60;2.37;2.12;2.05;1.92];
lambda_sigma_Q355 = [0.54;0.58;0.54;0.65;0.72;0.63;0.61;0.66;0.64];

Hq_Q370NH = [3.75;4.05;4.40;5.04;4.83;4.97;5.50;5.36;5.59];
Hq_sigma_Q370NH = [0.23;0.23;0.33;0.49;0.47;0.46;0.45;0.45;0.36];
lambda_Q370NH = [3.58;3.26;2.80;2.33;2.43;2.21;1.69;1.86;1.56];
lambda_sigma_Q370NH = [0.50;0.60;0.64;0.72;0.78;0.66;0.57;0.71;0.62];

data(1) = struct('name',"Q370NH",'eta',eta_Q370NH, ...
    'Hq',Hq_Q370NH,'HqSigma',Hq_sigma_Q370NH, ...
    'lambda',lambda_Q370NH,'lambdaSigma',lambda_sigma_Q370NH, ...
    'color',[0 0 1],'marker','o','lineStyle','-');
data(2) = struct('name',"Q355",'eta',eta_Q355, ...
    'Hq',Hq_Q355,'HqSigma',Hq_sigma_Q355, ...
    'lambda',lambda_Q355,'lambdaSigma',lambda_sigma_Q355, ...
    'color',[1 0 0],'marker','s','lineStyle','--');

%% 3. 使用03通用选择器拟合
fit_data = table;
for k = 1:numel(selected)
    current = data(selected(k));
    part = table(repmat(current.name,numel(days),1),days,current.eta, ...
        current.Hq,current.lambda,'VariableNames', ...
        {'Material','CorrosionTime_day','MassLoss_percent', ...
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
    "MassLoss_percent",definitions,fit_output_dir, ...
    model_choices,formula_digits);

depth_coefficients = struct;
aspect_coefficients = struct;
for k = 1:numel(selected)
    index = selected(k);
    data(index).depthRecord = find_best_fit_record( ...
        fit_package,data(index).name,"PitDepth");
    data(index).aspectRecord = find_best_fit_record( ...
        fit_package,data(index).name,"AspectRatio");
    depth_coefficients.(char(data(index).name)) = ...
        data(index).depthRecord.Parameters;
    aspect_coefficients.(char(data(index).name)) = ...
        data(index).aspectRecord.Parameters;
end

%% 4. 计算曲线
eta_fit = linspace(1.5,14.2,500);
nSelected = numel(selected);
materials = strings(nSelected,1);
depth_curves = cell(nSelected,1);
aspect_curves = cell(nSelected,1);

for k = 1:nSelected
    current = data(selected(k));
    depth_curves{k} = evaluate_best_fit_model( ...
        current.depthRecord.BestModel, ...
        current.depthRecord.Parameters,eta_fit);
    aspect_curves{k} = evaluate_best_fit_model( ...
        current.aspectRecord.BestModel, ...
        current.aspectRecord.Parameters,eta_fit);

    materials(k) = current.name;
    fprintf('\n%s蚀坑深度模型：%s\n', ...
        current.name,current.depthRecord.BestModel);
    fprintf('公式：%s，R^2 = %.6f\n', ...
        current.depthRecord.FormulaDisplay,current.depthRecord.R2);
    fprintf('%s径深比模型：%s\n', ...
        current.name,current.aspectRecord.BestModel);
    fprintf('公式：%s，R^2 = %.6f\n', ...
        current.aspectRecord.FormulaDisplay,current.aspectRecord.R2);
end
fprintf('\n');

%% 5. 绘制双子图
figure_files = strings(0,1);
if export_figures
    fig = figure('Color','w','Units','centimeters', ...
        'Position',[3 3 20.0 8.5]);
    layout = tiledlayout(fig,1,2,'TileSpacing','compact','Padding','compact');

    ax1 = nexttile(layout,1);
    hold(ax1,'on');
    [legend_handles_1,legend_text_1] = draw_panel( ...
        ax1,data,selected,eta_fit,depth_curves,'Hq');
    format_axis(ax1,[0 14.3],[3.5 5.9]);
    xlabel(ax1,'Mass loss rate, \eta (%)','Interpreter','tex');
    ylabel(ax1,'Pit depth, H_q','Interpreter','tex');
    text(ax1,0.04,0.95,'(a)','Units','normalized', ...
        'FontName','Times New Roman','FontSize',10,'FontWeight','bold');
    legend(ax1,legend_handles_1,cellstr(legend_text_1), ...
        'Location','northwest','Box','off','FontSize',8);

    ax2 = nexttile(layout,2);
    hold(ax2,'on');
    [legend_handles_2,legend_text_2] = draw_panel( ...
        ax2,data,selected,eta_fit,aspect_curves,'lambda');
    format_axis(ax2,[0 14.3],[1.2 3.9]);
    xlabel(ax2,'Mass loss rate, \eta (%)','Interpreter','tex');
    ylabel(ax2,'Pit aspect ratio, \lambda_q','Interpreter','tex');
    text(ax2,0.04,0.95,'(b)','Units','normalized', ...
        'FontName','Times New Roman','FontSize',10,'FontWeight','bold');
    legend(ax2,legend_handles_2,cellstr(legend_text_2), ...
        'Location','northeast','Box','off','FontSize',8);

    output_base = fullfile(output_dir, ...
        [output_prefix '_蚀坑参数与质量损失率拟合图' mode_suffix]);
    exportgraphics(fig,[output_base '.png'],'Resolution',600);
    exportgraphics(fig,[output_base '.tif'],'Resolution',600);
    exportgraphics(fig,[output_base '.pdf'],'ContentType','vector');
    savefig(fig,[output_base '.fig']);
    figure_files = string(output_base) + [".png";".tif";".pdf";".fig"];
end

%% 6. 保存拟合参数与绘图数据
parameter_table = fit_package.record_table;
parameter_table.MassLossMode = repmat(mode,height(parameter_table),1);
parameter_file = fullfile(output_dir, ...
    [output_prefix '_蚀坑参数与质量损失率拟合参数' mode_suffix '.csv']);
writetable(parameter_table,parameter_file);

plot_data_table = table;
for k = 1:nSelected
    current = data(selected(k));
    part = table(repmat(current.name,numel(days),1),days,current.eta, ...
        current.Hq,current.HqSigma,current.lambda,current.lambdaSigma, ...
        'VariableNames',{'Material','CorrosionTime_day','MassLoss_percent', ...
        'Hq_mean','Hq_sigma','Lambdaq_mean','Lambdaq_sigma'});
    plot_data_table = [plot_data_table;part]; %#ok<AGROW>
end
data_file = fullfile(output_dir, ...
    [output_prefix '_蚀坑参数绘图数据' mode_suffix '.csv']);
writetable(plot_data_table,data_file);

result = struct('materials',materials, ...
    'mass_loss_mode',mode, ...
    'mass_loss_Q370NH',eta_Q370NH, ...
    'mass_loss_Q355',eta_Q355, ...
    'depth_coefficients',depth_coefficients, ...
    'aspect_coefficients',aspect_coefficients, ...
    'fit_package',fit_package, ...
    'parameter_file',string(parameter_file), ...
    'data_file',string(data_file), ...
    'figure_files',figure_files);

disp(['结果已保存到：' char(output_dir)]);
end

function [handles,labels] = draw_panel( ...
    ax,data,selected,eta_fit,curves,parameter_name)
nSelected = numel(selected);
handles = gobjects(2*nSelected,1);
labels = strings(2*nSelected,1);

for k = 1:nSelected
    current = data(selected(k));
    if strcmp(parameter_name,'Hq')
        y = current.Hq;
    else
        y = current.lambda;
    end

    handles(2*k-1) = plot(ax,current.eta,y,current.marker, ...
        'LineStyle','none','MarkerSize',4.5, ...
        'MarkerFaceColor',current.color,'MarkerEdgeColor',current.color);
    handles(2*k) = plot(ax,eta_fit,curves{k},current.lineStyle, ...
        'Color',current.color,'LineWidth',1.25);
    labels(2*k-1) = current.name + " data";
    labels(2*k) = current.name + " fitting curve";
end
end

function format_axis(ax,xLimits,yLimits)
xlim(ax,xLimits);
ylim(ax,yLimits);
xticks(ax,0:2:14);
set(ax,'FontName','Times New Roman','FontSize',9, ...
    'LineWidth',0.8,'Box','on','TickDir','in', ...
    'XMinorTick','off','YMinorTick','off');
grid(ax,'off');
end

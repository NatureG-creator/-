function result = generate_corrosion_time_fit( ...
        fit_target,output_dir,export_figures,model_choices,formula_digits)
%GENERATE_CORROSION_TIME_FIT 按指定钢材拟合腐蚀率-时间关系。
% fit_target可取'Q370NH'、'Q355'或'both'。

if nargin < 1 || isempty(fit_target)
    fit_target = 'Q370NH';
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
        error('CorrosionFit:InvalidTarget', ...
            ['fit_target必须为''Q370NH''、''Q355''或''both''，' ...
             '当前输入为''%s''。'],char(string(fit_target)));
end

if ~isfolder(output_dir)
    mkdir(output_dir);
end

%% 原始数据：T为腐蚀时间/day，eta为质量损失率/%
% Q370NH原数据表题为Q370qENH，此处沿用目标图中的Q370NH名称。
T_Q370NH = [5;10;15;20;30;40;60;80;100];
eta_Q370NH_1 = [2.01;2.35;4.05;5.23;6.42;6.44;10.13;10.09;11.46];
eta_Q370NH_2 = [1.20;2.85;4.74;5.47;6.37;6.55;9.52;9.40;10.19];
eta_Q370NH = mean([eta_Q370NH_1,eta_Q370NH_2],2);

% Q355同样采用同一腐蚀时间下1号和2号试件的平均值进行拟合。
T_Q355 = [5;10;15;20;30;40;60;80;100];
eta_Q355_1 = [1.80;2.01;3.35;4.04;4.74;5.21;8.77;9.47;14.10];
eta_Q355_2 = [2.39;3.24;3.04;3.70;4.90;5.91;8.77;9.93;7.44];
eta_Q355 = mean([eta_Q355_1,eta_Q355_2],2);

data(1) = struct('name',"Q370NH",'T',T_Q370NH, ...
    'eta',eta_Q370NH,'color',[0 0 1]);
data(2) = struct('name',"Q355",'T',T_Q355, ...
    'eta',eta_Q355,'color',[1 0 0]);

%% 使用03通用选择器按材料独立拟合
T_fit = linspace(5,100,500);
nSelected = numel(selected);
material = strings(nSelected,1);
R2 = zeros(nSelected,1);
RMSE = zeros(nSelected,1);
etaFit = cell(nSelected,1);

fit_data = table;
for k = 1:nSelected
    current = data(selected(k));
    part = table(repmat(current.name,numel(current.T),1), ...
        current.T,current.eta,'VariableNames', ...
        {'Material','Time_day','Mean_percent'});
    fit_data = [fit_data;part]; %#ok<AGROW>
end
definitions = table("MassLoss","Mean_percent","质量损失率", ...
    "自动选择最优函数","T","eta",'VariableNames', ...
    {'Metric','Variable','ChineseName','DefaultModel','XSymbol','YSymbol'});
fit_output_dir = fullfile(output_dir,'03_统一拟合结果');
fit_package = fit_grouped_dataset(fit_data,"Material","Time_day", ...
    definitions,fit_output_dir,model_choices,formula_digits);

for k = 1:nSelected
    current = data(selected(k));
    record = find_best_fit_record(fit_package,current.name,"MassLoss");

    material(k) = current.name;
    R2(k) = record.R2;
    RMSE(k) = record.RMSE;
    etaFit{k} = evaluate_best_fit_model( ...
        record.BestModel,record.Parameters,T_fit);

    fprintf('\n%s最优模型：%s\n',current.name,record.BestModel);
    fprintf('公式：%s\n',record.FormulaDisplay);
    fprintf('%s: R^2 = %.6f, RMSE = %.6f %%\n', ...
        current.name,R2(k),RMSE(k));
end
fprintf('\n');

%% 绘图及图像导出
figure_files = strings(0,1);
if export_figures
    fig = figure('Color','w','Units','centimeters', ...
        'Position',[5 5 14.5 11.0]);
    ax = axes(fig);
    hold(ax,'on');

    legend_handles = gobjects(2*nSelected,1);
    legend_text = strings(2*nSelected,1);
    for k = 1:nSelected
        current = data(selected(k));
        legend_handles(2*k-1) = plot(ax,current.T,current.eta,'o', ...
            'LineStyle','none','MarkerSize',6.5, ...
            'MarkerFaceColor',current.color, ...
            'MarkerEdgeColor',current.color);
        legend_handles(2*k) = plot(ax,T_fit,etaFit{k},'-', ...
            'Color',current.color,'LineWidth',1.6);
        legend_text(2*k-1) = current.name + " data";
        legend_text(2*k) = current.name + " fitting curve";
    end

    xlim(ax,[0 106]);
    ylim(ax,[0.5 14.6]);
    xticks(ax,20:20:100);
    yticks(ax,2:2:14);
    xlabel(ax,'T/day','FontName','Times New Roman','FontSize',12);
    ylabel(ax,'\eta/%','Interpreter','tex', ...
        'FontName','Times New Roman','FontSize',12);
    set(ax,'FontName','Times New Roman','FontSize',11, ...
        'LineWidth',1.0,'Box','on','TickDir','in', ...
        'XMinorTick','off','YMinorTick','off');
    legend(ax,legend_handles,cellstr(legend_text), ...
        'Location','northwest','Box','off', ...
        'FontName','Times New Roman','FontSize',9);

    output_base = fullfile(output_dir, ...
        [output_prefix '_时间腐蚀率拟合图']);
    exportgraphics(fig,[output_base '.png'],'Resolution',600);
    exportgraphics(fig,[output_base '.tif'],'Resolution',600);
    exportgraphics(fig,[output_base '.pdf'],'ContentType','vector');
    savefig(fig,[output_base '.fig']);
    figure_files = string(output_base) + [".png";".tif";".pdf";".fig"];
end

%% 保存拟合参数和原始数据
fit_table = fit_package.record_table;
parameter_file = fullfile(output_dir, ...
    [output_prefix '_时间腐蚀率拟合参数.csv']);
writetable(fit_table,parameter_file);

if any(selected == 1)
    Q370NH_data_table = table( ...
        T_Q370NH,eta_Q370NH_1,eta_Q370NH_2,eta_Q370NH, ...
        'VariableNames',{'Time_day','Specimen_1_percent', ...
        'Specimen_2_percent','Mean_percent'});
    writetable(Q370NH_data_table,fullfile(output_dir, ...
        'Q370NH_质量损失率原始数据及平均值.csv'));
end

if any(selected == 2)
    Q355_data_table = table( ...
        T_Q355,eta_Q355_1,eta_Q355_2,eta_Q355, ...
        'VariableNames',{'Time_day','Specimen_1_percent', ...
        'Specimen_2_percent','Mean_percent'});
    writetable(Q355_data_table,fullfile(output_dir, ...
        'Q355_质量损失率原始数据及平均值.csv'));
end

result = struct('fit_target',string(fit_target), ...
    'materials',material,'parameters',fit_table, ...
    'fit_package',fit_package, ...
    'parameter_file',string(parameter_file), ...
    'figure_files',figure_files);

disp(['结果已保存到：' char(output_dir)]);
end

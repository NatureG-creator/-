%% MATLAB通用拟合函数选择器（自动识别数据并逐指标选择函数）
% 选择数据后，将为每个识别到的指标分别弹出拟合函数菜单。

data_file = '';       % 留空时弹出文件选择窗口
export_figures = true; % true输出图片，false只输出数据与拟合结果
formula_digits = 4;   % 公式参数保留的小数位数
 
if isempty(data_file)
    [fileName,folderName] = uigetfile( ...
        {'*.xlsx;*.xls;*.csv;*.txt;*.dat;*.mat', ...
        '数据文件 (*.xlsx,*.csv,*.txt,*.mat)'}, ...
        '选择需要自动识别的拟合数据');
    if isequal(fileName,0)
        error('BestFit:SelectionCancelled','未选择数据文件。');
    end
    data_file = fullfile(folderName,fileName);
end

result = best_fit_selector_auto( ...
    data_file,[],export_figures,"prompt",formula_digits);

fprintf('\n识别数据类型：%s\n',result.data_type);
fprintf('识别横坐标：%s\n',result.x_column);
fprintf('识别到%d个拟合指标：%s\n', ...
    numel(result.metrics),strjoin(result.metrics,', '));
fprintf('各指标选择的函数：\n');
for i = 1:numel(result.metrics)
    fprintf('  %s：%s\n',result.metrics(i),result.selected_models(i));
end
fprintf('结果文件夹：%s\n\n',result.output_dir);
disp(result.summary_table);

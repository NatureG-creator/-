%% =========================================================
% Batch processing
% Keep fenbujianyan(data) unchanged
% Only modify figure background, legend position and export settings
%
% Input:
% c5d2, c10d2, c15d2, c20d2, c30d2, c40d2, c60d2, c80d2, c100d2
%
% Output:
% c5d_fb.fig,   c5d_fb.tif
% c10d_fb.fig,  c10d_fb.tif
% ...
% c100d_fb.fig, c100d_fb.tif
%% =========================================================

clc; close all;

day_list = [5 10 15 20 30 40 60 80 100];

for i = 1:length(day_list)

    day_num = day_list(i);

    % Data variable name, for example: c5d2, c10d2
    var_name = sprintf('c%dd2', day_num);

    % Output name, for example: c5d_fb, c10d_fb
    out_name = sprintf('c%dd_fb', day_num);

    %% ===================== Get data =====================
    if evalin('base', sprintf('exist(''%s'', ''var'')', var_name))
        data = evalin('base', var_name);

    elseif isfile([var_name, '.mat'])
        S = load([var_name, '.mat']);
        names = fieldnames(S);

        data = [];

        for j = 1:length(names)
            temp = S.(names{j});

            if isnumeric(temp) && ~isempty(temp)
                data = temp;
                break;
            end
        end

        if isempty(data)
            warning('%s.mat has no numeric data. Skipped.', var_name);
            continue;
        end

    else
        warning('%s does not exist in workspace or as .mat file. Skipped.', var_name);
        continue;
    end

    %% ===================== Keep original plotting logic =====================
    fenbujianyan(data);

    %% ===================== Only modify background, legend and export =====================
    fig = gcf;

    % Set figure window background from gray to white
    set(fig, 'Color', 'w');

    % Set axes background to white
    ax = findall(fig, 'Type', 'axes');
    for k = 1:length(ax)
        set(ax(k), 'Color', 'w');
    end

    % Move legend to upper-left corner
    lgd = findall(fig, 'Type', 'Legend');
    for k = 1:length(lgd)
        set(lgd(k), ...
            'Location', 'northwest', ...
            'FontName', 'Times New Roman');
    end

    % Export setting
    set(fig, 'PaperUnits', 'centimeters');
    set(fig, 'PaperPositionMode', 'auto');
    set(fig, 'InvertHardcopy', 'off');

    % Save editable MATLAB figure
    savefig(fig, [out_name, '.fig']);

    % Save 600 dpi TIFF
    print(fig, [out_name, '.tif'], '-dtiff', '-r600');

    fprintf('%s.fig and %s.tif have been exported.\n', out_name, out_name);

    close(fig);
end

fprintf('\nAll figures have been exported.\n');
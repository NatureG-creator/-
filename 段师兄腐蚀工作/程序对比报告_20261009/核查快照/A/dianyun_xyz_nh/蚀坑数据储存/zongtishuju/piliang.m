%% =========================================================
% Batch processing
% Keep fenbujianyan(data) unchanged
% Only modify figure background and export settings
%
% Output:
% n20d_fb.fig,  n20d_fb.tif
% n30d_fb.fig,  n30d_fb.tif
% ...
%% =========================================================

clc; close all;

day_list = [20 30 40 60 80 100];

for i = 1:length(day_list)

    day_num = day_list(i);

    % Data variable name, for example: n20d2
    var_name = sprintf('n%dd2', day_num);

    % Output name, for example: n20d_fb
    out_name = sprintf('n%dd_fb', day_num);

    %% ===================== Get data =====================
    % First try to read variable from workspace
    if evalin('base', sprintf('exist(''%s'', ''var'')', var_name))
        data = evalin('base', var_name);

    % If no workspace variable exists, try to load .mat file
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

    %% ===================== Only modify background and export =====================
    fig = gcf;

    % Set figure window background from gray to white
    set(fig, 'Color', 'w');

    % Set axes background to white
    ax = findall(fig, 'Type', 'axes');
    for k = 1:length(ax)
        set(ax(k), 'Color', 'w');
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
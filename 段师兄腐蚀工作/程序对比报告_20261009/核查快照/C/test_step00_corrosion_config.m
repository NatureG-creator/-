function tests = test_step00_corrosion_config
% 统一参数中心的回归测试。
tests = functiontests(localfunctions);
end

function testDefaultValues(testCase)
cfg = step00_corrosion_config();

verifyEqual(testCase, cfg.preprocessing.grid_resolution_mm, 0.3);
verifyEqual(testCase, cfg.preprocessing.trim_edge_rows, 3);
verifyEqual(testCase, cfg.preprocessing.main_gaussian_sigma, 2.0);
verifyEqual(testCase, cfg.pit_detection.min_prominence, 0.001);
verifyEqual(testCase, cfg.pit_detection.min_distance, 15);
verifyEqual(testCase, cfg.pit_detection.neighborhood, [12, 12]);
verifyEqual(testCase, cfg.watershed.threshold, 0.3);
verifyEqual(testCase, cfg.distribution.hist_bin_width, 0.1);
verifyEqual(testCase, cfg.apdl.dx_mm, cfg.preprocessing.grid_resolution_mm);
verifyEqual(testCase, cfg.apdl.dy_mm, cfg.preprocessing.grid_resolution_mm);
end

function testRequiredGroupsExist(testCase)
cfg = step00_corrosion_config();
required = {'input','preprocessing','reference','pit_detection', ...
    'watershed','distribution','figure','apdl','output'};

for k = 1:numel(required)
    verifyTrue(testCase, isfield(cfg, required{k}), ...
        ['缺少配置分组: ', required{k}]);
end
end

function testInputFilesResolveFromProjectRoot(testCase)
cfg = step00_corrosion_config();
verifyTrue(testCase, isfolder(cfg.project_root));
verifyEqual(testCase, cfg.input.point_cloud_50_file, ...
    fullfile(cfg.project_root, 'C17_100d_z_50_chongxin.txt'));
end

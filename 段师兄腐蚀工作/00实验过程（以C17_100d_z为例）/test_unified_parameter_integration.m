function tests = test_unified_parameter_integration
% 统一参数接入后的轻量集成测试。
tests = functiontests(localfunctions);
end

function setupOnce(testCase)
testCase.TestData.oldVisible = get(groot, 'defaultFigureVisible');
set(groot, 'defaultFigureVisible', 'off');
end

function teardownOnce(testCase)
close all force;
set(groot, 'defaultFigureVisible', testCase.TestData.oldVisible);
end

function testJisuan190UsesConfiguredRegions(testCase)
cfg = step00_corrosion_config();
Z = ones(3, 400);
Z(1,1) = 0;
Z(1,2) = 10;

[depth, flatHeight, corrosionHeight] = jisuan_190(Z, cfg);

verifyEqual(testCase, flatHeight, 2, 'AbsTol', 1e-12);
verifyEqual(testCase, corrosionHeight, 1, 'AbsTol', 1e-12);
verifyEqual(testCase, depth, 1, 'AbsTol', 1e-12); % 正向口径：中央最高高程减参考高度。
end

function testPitExtractionKeepsLegacyFormula(testCase)
cfg = step00_corrosion_config();
data = zeros(5, 5);
data(2,2) = 2;
pits = {[1,1,0; 3,1,0; 3,3,0; 1,3,0]};
maxLoc = [2,2];

[depth, ratio, diameter] = fushikengtiqu( ...
    data, pits, maxLoc, cfg.preprocessing.grid_resolution_mm, cfg);

verifyEqual(testCase, depth, 2, 'AbsTol', 1e-12);
verifyEqual(testCase, diameter, 0.6, 'AbsTol', 1e-12);
verifyEqual(testCase, ratio, 2/0.6, 'AbsTol', 1e-12);
end

function testDistributionFunctionAcceptsConfig(testCase)
cfg = step00_corrosion_config();
fenbujianyan([1.0; 1.1; 1.2; 1.3; 1.4], cfg);
verifyGreaterThanOrEqual(testCase, numel(findall(groot, 'Type', 'figure')), 2);
close all force;
end

function testAllProductionFilesReferenceConfig(testCase)
cfg = step00_corrosion_config();
files = {'untitled.m','shujuguiyi.m','jixiantiqu_3D.m', ...
    'fenshuiling_boundry.m','fushikengtiqu.m','fenbujianyan.m', ...
    'jisuan_190.m','bianyunchuli.m','bianyunchuli_fanzhuan.m', ...
    'matlab_apdl.m'};

for k = 1:numel(files)
    content = fileread(fullfile(cfg.project_root, files{k}));
    verifyNotEmpty(testCase, regexp(content, ...
        'step00_corrosion_config|\bcfg\b', 'once'), ...
        ['文件尚未接入统一参数: ', files{k}]);
end
end

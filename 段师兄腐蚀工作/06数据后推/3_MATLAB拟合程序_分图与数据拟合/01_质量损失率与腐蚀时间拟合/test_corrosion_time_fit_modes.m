function tests = test_corrosion_time_fit_modes
tests = functiontests(localfunctions);
end

function testQ370NHOnly(testCase)
outputDir = makeOutputDir(testCase);
result = generate_corrosion_time_fit('Q370NH', outputDir, false);

verifyEqual(testCase, result.materials, "Q370NH");
verifyTrue(testCase, isfile(fullfile(outputDir, ...
    'Q370NH_时间腐蚀率拟合参数.csv')));

fitTable = readtable(fullfile(outputDir, ...
    'Q370NH_时间腐蚀率拟合参数.csv'), 'TextType', 'string');
verifyEqual(testCase, height(fitTable), 1);
verifyEqual(testCase, fitTable.Material, "Q370NH");
verifyTrue(testCase,isfile(result.fit_package.mat_file));
verifyTrue(testCase,isfile(result.fit_package.csv_file));
verifyEqual(testCase,result.fit_package.formula_digits,4);
end

function testFormulaDigitsAndForcedModel(testCase)
outputDir = makeOutputDir(testCase);
result = generate_corrosion_time_fit( ...
    'Q370NH',outputDir,false,"线性函数",2);
record = find_best_fit_record(result.fit_package,"Q370NH","MassLoss");
verifyEqual(testCase,record.BestModel,"线性函数");
verifyEqual(testCase,record.FormulaDisplay, ...
    format_best_fit_formula(record.BestModel,record.Parameters,2,"T","eta"));
verifyEqual(testCase,record.FormulaDisplay,"eta = 0.09*T + 2.65");
end

function testQ355Only(testCase)
outputDir = makeOutputDir(testCase);
result = generate_corrosion_time_fit('Q355', outputDir, false);

verifyEqual(testCase, result.materials, "Q355");
verifyTrue(testCase, isfile(fullfile(outputDir, ...
    'Q355_时间腐蚀率拟合参数.csv')));

fitTable = readtable(fullfile(outputDir, ...
    'Q355_时间腐蚀率拟合参数.csv'), 'TextType', 'string');
verifyEqual(testCase, height(fitTable), 1);
verifyEqual(testCase, fitTable.Material, "Q355");

rawTable = readtable(fullfile(outputDir, ...
    'Q355_质量损失率原始数据及平均值.csv'));
verifyEqual(testCase, rawTable.Specimen_1_percent, ...
    [1.80;2.01;3.35;4.04;4.74;5.21;8.77;9.47;14.10], ...
    'AbsTol',1e-12);
verifyEqual(testCase, rawTable.Specimen_2_percent, ...
    [2.39;3.24;3.04;3.70;4.90;5.91;8.77;9.93;7.44], ...
    'AbsTol',1e-12);
verifyEqual(testCase, rawTable.Mean_percent(end),10.77, ...
    'AbsTol',1e-12);
end

function testBothMaterials(testCase)
outputDir = makeOutputDir(testCase);
result = generate_corrosion_time_fit('both', outputDir, false);

verifyEqual(testCase, result.materials, ["Q370NH"; "Q355"]);
verifyTrue(testCase, isfile(fullfile(outputDir, ...
    'Q370NH_Q355_时间腐蚀率拟合参数.csv')));

fitTable = readtable(fullfile(outputDir, ...
    'Q370NH_Q355_时间腐蚀率拟合参数.csv'), 'TextType', 'string');
verifyEqual(testCase, height(fitTable), 2);
verifyEqual(testCase, fitTable.Material, ["Q370NH"; "Q355"]);
end

function testInvalidTarget(testCase)
outputDir = makeOutputDir(testCase);
verifyError(testCase, ...
    @() generate_corrosion_time_fit('Q345', outputDir, false), ...
    'CorrosionFit:InvalidTarget');
end

function outputDir = makeOutputDir(testCase)
outputDir = tempname;
mkdir(outputDir);
testCase.addTeardown(@() removeOutputDir(outputDir));
end

function removeOutputDir(outputDir)
if isfolder(outputDir)
    rmdir(outputDir, 's');
end
end

function tests = test_pit_parameter_mass_loss_figure
tests = functiontests(localfunctions);
end

function testOriginalFigureMode(testCase)
outputDir = makeOutputDir(testCase);
result = generate_pit_parameter_mass_loss_figure( ...
    'both','original_figure',outputDir,false);

verifyEqual(testCase,result.materials,["Q370NH";"Q355"]);
verifyEqual(testCase,result.mass_loss_Q355(end),14.10,'AbsTol',1e-12);
verifyEqual(testCase,result.mass_loss_Q370NH(end),10.825,'AbsTol',1e-12);
verifyTrue(testCase,isfile(result.fit_package.mat_file));
verifyTrue(testCase,isfile(result.fit_package.csv_file));
verifyEqual(testCase,numel(result.fit_package.records),4);
verifyEqual(testCase,result.depth_coefficients.Q370NH, ...
    find_best_fit_record(result.fit_package,"Q370NH","PitDepth").Parameters, ...
    'AbsTol',1e-12);
verifyEqual(testCase,result.aspect_coefficients.Q355, ...
    find_best_fit_record(result.fit_package,"Q355","AspectRatio").Parameters, ...
    'AbsTol',1e-12);
verifyTrue(testCase,isfile(fullfile(outputDir, ...
    'Q370NH_Q355_蚀坑参数与质量损失率拟合参数.csv')));
end

function testForcedModelsAndFormulaDigits(testCase)
outputDir = makeOutputDir(testCase);
choices = struct('PitDepth',"幂函数",'AspectRatio',"对数函数");
result = generate_pit_parameter_mass_loss_figure( ...
    'Q370NH','mean',outputDir,false,choices,3);
depth = find_best_fit_record(result.fit_package,"Q370NH","PitDepth");
aspect = find_best_fit_record(result.fit_package,"Q370NH","AspectRatio");
verifyEqual(testCase,depth.BestModel,"幂函数");
verifyEqual(testCase,aspect.BestModel,"对数函数");
verifyEqual(testCase,result.fit_package.formula_digits,3);
verifyThat(testCase,depth.FormulaDisplay, ...
    matlab.unittest.constraints.ContainsSubstring("3.332"));
end

function testMeanMassLossMode(testCase)
outputDir = makeOutputDir(testCase);
result = generate_pit_parameter_mass_loss_figure( ...
    'Q355','mean',outputDir,false);

verifyEqual(testCase,result.materials,"Q355");
verifyEqual(testCase,result.mass_loss_Q355(end),10.77,'AbsTol',1e-12);
verifyEqual(testCase,result.mass_loss_Q355(1),2.095,'AbsTol',1e-12);
end

function testInvalidMaterial(testCase)
outputDir = makeOutputDir(testCase);
verifyError(testCase,@() generate_pit_parameter_mass_loss_figure( ...
    'Q345','mean',outputDir,false),'PitFit:InvalidTarget');
end

function testInvalidMassLossMode(testCase)
outputDir = makeOutputDir(testCase);
verifyError(testCase,@() generate_pit_parameter_mass_loss_figure( ...
    'both','median',outputDir,false),'PitFit:InvalidMassLossMode');
end

function outputDir = makeOutputDir(testCase)
outputDir = tempname;
mkdir(outputDir);
testCase.addTeardown(@() removeOutputDir(outputDir));
end

function removeOutputDir(outputDir)
if isfolder(outputDir)
    rmdir(outputDir,'s');
end
end

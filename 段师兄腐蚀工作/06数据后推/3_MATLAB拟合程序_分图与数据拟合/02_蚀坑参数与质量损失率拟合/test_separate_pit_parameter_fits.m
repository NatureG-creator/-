function tests = test_separate_pit_parameter_fits
tests = functiontests(localfunctions);
end

function testFitsAreCalculatedFromMeanData(testCase)
outputDir = makeOutputDir(testCase);
result = generate_separate_pit_parameter_fits('both',outputDir,false);

verifyEqual(testCase,result.materials,["Q370NH";"Q355"]);
verifyEqual(testCase,result.mass_loss_Q370NH(end),10.825,'AbsTol',1e-12);
verifyEqual(testCase,result.mass_loss_Q355(end),10.77,'AbsTol',1e-12);

verifyTrue(testCase,isfile(result.fit_package.mat_file));
verifyTrue(testCase,isfile(result.fit_package.csv_file));
verifyEqual(testCase,numel(result.fit_package.records),4);
verifyEqual(testCase,find_best_fit_record( ...
    result.fit_package,"Q370NH","PitDepth").BestModel,"幂函数");
verifyEqual(testCase,find_best_fit_record( ...
    result.fit_package,"Q355","PitDepth").BestModel,"对数函数");
verifyEqual(testCase,find_best_fit_record( ...
    result.fit_package,"Q370NH","AspectRatio").BestModel,"指数函数");
verifyEqual(testCase,find_best_fit_record( ...
    result.fit_package,"Q355","AspectRatio").BestModel,"对数函数");
end

function testIndependentModelChoiceAndFormulaDigits(testCase)
outputDir = makeOutputDir(testCase);
choices = struct('PitDepth',"幂函数",'AspectRatio',"对数函数");
result = generate_separate_pit_parameter_fits( ...
    'Q370NH',outputDir,false,choices,2);
depth = find_best_fit_record(result.fit_package,"Q370NH","PitDepth");
aspect = find_best_fit_record(result.fit_package,"Q370NH","AspectRatio");
verifyEqual(testCase,depth.BestModel,"幂函数");
verifyEqual(testCase,aspect.BestModel,"对数函数");
verifyThat(testCase,depth.FormulaDisplay, ...
    matlab.unittest.constraints.ContainsSubstring("3.33"));
end

function testSeparateParameterFiles(testCase)
outputDir = makeOutputDir(testCase);
result = generate_separate_pit_parameter_fits('Q355',outputDir,false);

verifyTrue(testCase,isfile(result.depth_parameter_file));
verifyTrue(testCase,isfile(result.aspect_parameter_file));
verifyNotEqual(testCase,result.depth_parameter_file,result.aspect_parameter_file);
verifyEqual(testCase,height(readtable(result.depth_parameter_file)),1);
verifyEqual(testCase,height(readtable(result.aspect_parameter_file)),1);
end

function testInvalidTarget(testCase)
outputDir = makeOutputDir(testCase);
verifyError(testCase,@() generate_separate_pit_parameter_fits( ...
    'Q345',outputDir,false),'PitFit:InvalidTarget');
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

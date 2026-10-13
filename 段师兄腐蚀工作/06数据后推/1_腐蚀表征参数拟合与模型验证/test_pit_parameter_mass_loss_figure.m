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
verifyEqual(testCase,result.depth_coefficients.Q370NH,[3.31,0.22], ...
    'AbsTol',1e-12);
verifyEqual(testCase,result.aspect_coefficients.Q355,[5.48,1.54,0.34], ...
    'AbsTol',1e-12);
verifyTrue(testCase,isfile(fullfile(outputDir, ...
    'Q370NH_Q355_蚀坑参数与质量损失率拟合参数.csv')));
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

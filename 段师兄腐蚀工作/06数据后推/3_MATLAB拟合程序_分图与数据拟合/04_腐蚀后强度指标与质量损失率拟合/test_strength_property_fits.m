function tests = test_strength_property_fits
tests = functiontests(localfunctions);
end

function testMaterialSelectionAndRegression(testCase)
workDir = make_work_dir(testCase);
linearChoices = struct('YieldStrength',"线性函数", ...
    'TensileStrength',"线性函数", ...
    'FractureStrength',"线性函数", ...
    'StrengthRatio',"均值模型");

q370 = generate_strength_property_fits( ...
    'Q370NH',fullfile(workDir,'q370'),false,linearChoices,4);
verifyEqual(testCase,q370.materials,"Q370NH");
verifyEqual(testCase,height(q370.plot_data),18);
verify_fit(testCase,q370.fit_parameters,"YieldStrength", ...
    456.80,-528.0,0.791,[0.05,0.5,0.002]);
verify_fit(testCase,q370.fit_parameters,"TensileStrength", ...
    577.53,-630.0,0.830,[0.15,2.0,0.01]);
verify_fit(testCase,q370.fit_parameters,"FractureStrength", ...
    413.4443,-241.6853,0.1963,[0.01,0.02,0.001]);
ratioRow = q370.fit_parameters.Metric == "StrengthRatio";
verifyEqual(testCase,q370.fit_parameters.Mean(ratioRow),1.27013, ...
    'AbsTol',0.0001);

q355 = generate_strength_property_fits( ...
    'Q355',fullfile(workDir,'q355'),false,linearChoices,4);
verifyEqual(testCase,q355.materials,"Q355");
verifyEqual(testCase,height(q355.plot_data),18);
verify_fit(testCase,q355.fit_parameters,"YieldStrength", ...
    409.1536,-330.3812,0.543,[0.01,0.02,0.001]);
verify_fit(testCase,q355.fit_parameters,"TensileStrength", ...
    557.75,-512.0,0.620,[0.15,2.0,0.01]);
verify_fit(testCase,q355.fit_parameters,"FractureStrength", ...
    428.5210,-465.1765,0.4767,[0.01,0.02,0.001]);
ratioRow = q355.fit_parameters.Metric == "StrengthRatio";
verifyEqual(testCase,q355.fit_parameters.Mean(ratioRow),1.35415, ...
    'AbsTol',0.0001);

both = generate_strength_property_fits( ...
    'both',fullfile(workDir,'both'),false,linearChoices,4);
verifyEqual(testCase,both.materials,["Q370NH";"Q355"]);
verifyEqual(testCase,height(both.plot_data),36);

alias = generate_strength_property_fits( ...
    'Q370',fullfile(workDir,'alias'),false,linearChoices,4);
verifyEqual(testCase,alias.materials,"Q370NH");
end

function testUnifiedBestFitAndFormulaDigits(testCase)
workDir = make_work_dir(testCase);
result = generate_strength_property_fits( ...
    'Q370NH',workDir,false,"auto",2);
verifyTrue(testCase,isfile(result.fit_package.mat_file));
verifyEqual(testCase,numel(result.fit_package.records),4);
ratio = find_best_fit_record(result.fit_package,"Q370NH","StrengthRatio");
verifyEqual(testCase,ratio.BestModel,"均值模型");
verifyThat(testCase,ratio.FormulaDisplay, ...
    matlab.unittest.constraints.ContainsSubstring("1.27"));
end

function testInvalidTarget(testCase)
workDir = make_work_dir(testCase);
verifyError(testCase,@() generate_strength_property_fits( ...
    'other',workDir,false),'StrengthFit:InvalidTarget');
end

function testExports(testCase)
workDir = make_work_dir(testCase);
result = generate_strength_property_fits('Q370NH',workDir,true);
baseNames = ["屈服强度拟合图";"抗拉强度拟合图"; ...
    "屈强比统计图";"断裂强度拟合图"];
expected = strings(0,1);
extensions = [".png";".tif";".pdf";".fig"];
for baseName = baseNames'
    expected = [expected; ...
        fullfile(string(workDir),"Q370NH_"+baseName+extensions)]; %#ok<AGROW>
end
verifyEqual(testCase,sort(result.figure_files),sort(expected));
verifyEqual(testCase,numel(result.figure_files),16);
verify_output_files(testCase,[result.figure_files; ...
    result.parameter_file;result.data_file]);
end

function testDeliveryFiles(testCase)
folder = fileparts(mfilename('fullpath'));
verifyTrue(testCase,isfile(fullfile(folder, ...
    'plot_strength_property_fits.m')));
verifyTrue(testCase,isfile(fullfile(folder,'使用说明.md')));
verifyTrue(testCase,isfile(fullfile(folder,'strength_property_data.csv')));
end

function verify_fit(testCase,fitTable,metric,intercept,slope,r2,tolerance)
row = fitTable.Metric == metric;
verifyEqual(testCase,sum(row),1);
verifyEqual(testCase,fitTable.Intercept(row),intercept, ...
    'AbsTol',tolerance(1));
verifyEqual(testCase,fitTable.Slope(row),slope, ...
    'AbsTol',tolerance(2));
verifyEqual(testCase,fitTable.R2(row),r2, ...
    'AbsTol',tolerance(3));
end

function verify_output_files(testCase,files)
for filePath = files'
    verifyTrue(testCase,isfile(filePath));
    information = dir(filePath);
    verifyGreaterThan(testCase,information.bytes,0);
end
end

function workDir = make_work_dir(testCase)
workDir = tempname;
mkdir(workDir);
testCase.addTeardown(@() remove_work_dir(workDir));
end

function remove_work_dir(workDir)
if isfolder(workDir)
    rmdir(workDir,'s');
end
end

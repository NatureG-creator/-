function tests = test_strain_modulus_fits
tests = functiontests(localfunctions);
end

function testMaterialSelectionAndRegression(testCase)
workDir = make_work_dir(testCase);

q370 = generate_strain_modulus_fits( ...
    'Q370NH',fullfile(workDir,'q370'),false,"线性函数",4);
verifyEqual(testCase,q370.materials,"Q370NH");
verifyEqual(testCase,height(q370.plot_data),18);
verify_fit(testCase,q370.fit_parameters,"HardeningStrain", ...
    0.02,0.01,0.043,[0.005,0.03,0.01]);
verify_fit(testCase,q370.fit_parameters,"UltimateStrain", ...
    0.18,-0.23,0.360,[0.005,0.03,0.01]);
verify_fit(testCase,q370.fit_parameters,"FractureStrain", ...
    0.34,-0.95,0.468,[0.005,0.04,0.01]);
verify_fit(testCase,q370.fit_parameters,"ElasticModulus", ...
    195610.16,-142430.24,0.269,[5,80,0.01]);

q355 = generate_strain_modulus_fits( ...
    'Q355',fullfile(workDir,'q355'),false,"线性函数",4);
verifyEqual(testCase,q355.materials,"Q355");
verifyEqual(testCase,height(q355.plot_data),18);
verify_fit(testCase,q355.fit_parameters,"HardeningStrain", ...
    0.01,-0.02,0.030,[0.005,0.03,0.01]);
verify_fit(testCase,q355.fit_parameters,"UltimateStrain", ...
    0.16345,-0.16524,0.48608,[0.0001,0.0002,0.001]);
verify_fit(testCase,q355.fit_parameters,"FractureStrain", ...
    0.33,-0.63,0.316,[0.005,0.04,0.01]);
verify_fit(testCase,q355.fit_parameters,"ElasticModulus", ...
    189244.32,-71173.86,0.109,[5,80,0.01]);

both = generate_strain_modulus_fits( ...
    'both',fullfile(workDir,'both'),false,"线性函数",4);
verifyEqual(testCase,both.materials,["Q370NH";"Q355"]);
verifyEqual(testCase,height(both.plot_data),36);

alias = generate_strain_modulus_fits( ...
    'Q370',fullfile(workDir,'alias'),false,"线性函数",4);
verifyEqual(testCase,alias.materials,"Q370NH");
end

function testUnifiedBestFitAndFormulaDigits(testCase)
workDir = make_work_dir(testCase);
result = generate_strain_modulus_fits( ...
    'Q370NH',workDir,false,"auto",3);
verifyTrue(testCase,isfile(result.fit_package.mat_file));
verifyEqual(testCase,numel(result.fit_package.records),4);
record = find_best_fit_record(result.fit_package,"Q370NH","UltimateStrain");
verifyEqual(testCase,record.FormulaDisplay, ...
    format_best_fit_formula(record.BestModel,record.Parameters,3,"eta","epsilon_u"));
end

function testInvalidTarget(testCase)
workDir = make_work_dir(testCase);
verifyError(testCase,@() generate_strain_modulus_fits( ...
    'other',workDir,false),'StrainFit:InvalidTarget');
end

function testExports(testCase)
workDir = make_work_dir(testCase);
result = generate_strain_modulus_fits('Q355',workDir,true);
baseNames = ["硬化应变拟合图";"极限应变拟合图"; ...
    "断裂应变拟合图";"弹性模量拟合图"];
expected = strings(0,1);
extensions = [".png";".tif";".pdf";".fig"];
for baseName = baseNames'
    expected = [expected; ...
        fullfile(string(workDir),"Q355_"+baseName+extensions)]; %#ok<AGROW>
end
verifyEqual(testCase,sort(result.figure_files),sort(expected));
verifyEqual(testCase,numel(result.figure_files),16);
verify_output_files(testCase,[result.figure_files; ...
    result.parameter_file;result.data_file]);
end

function testDeliveryFiles(testCase)
folder = fileparts(mfilename('fullpath'));
verifyTrue(testCase,isfile(fullfile(folder, ...
    'plot_strain_modulus_fits.m')));
verifyTrue(testCase,isfile(fullfile(folder,'使用说明.md')));
verifyTrue(testCase,isfile(fullfile(folder,'strain_modulus_data.csv')));
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

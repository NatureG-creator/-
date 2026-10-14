function tests = test_site_parameter_contract
% 网站副本组件验证；不代表真实点云全流程已通过。
tests = functiontests(localfunctions);
end

function testSmallConfigurableReference(testCase)
cfg.reference = struct('flat_column_count',2,'corrosion_column_count',3,'flat_height_ratio',0.2);
Z = repmat(1:10,4,1);
[uniform, reference, corrosion, columns] = jisuan_190(Z,cfg);
verifyEqual(testCase,columns,5:7);
verifyEqual(testCase,reference,1.2,'AbsTol',1e-12);
verifyEqual(testCase,corrosion,7);
verifyEqual(testCase,uniform,5.8,'AbsTol',1e-12);
end

function testNoAbsoluteValueForNegativeReference(testCase)
cfg.reference = struct('flat_column_count',2,'corrosion_column_count',3,'flat_height_ratio',0.2);
Z = repmat([10 11 9 8 1 2 3 8 9 10],4,1);
[uniform,reference,corrosion] = jisuan_190(Z,cfg);
verifyLessThan(testCase,uniform,0);
verifyEqual(testCase,uniform,corrosion-reference,'AbsTol',1e-12);
end

function testFractionalColumnsRejected(testCase)
cfg.reference = struct('flat_column_count',2.5,'corrosion_column_count',3,'flat_height_ratio',0.2);
verifyError(testCase,@()jisuan_190(ones(4,10),cfg),'reference:InvalidColumns');
end

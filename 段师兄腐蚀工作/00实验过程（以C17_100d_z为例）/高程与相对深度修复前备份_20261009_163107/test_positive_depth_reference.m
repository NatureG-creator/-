function tests=test_positive_depth_reference
tests=functiontests(localfunctions);
end

function testSharedReferenceAndCrop(testCase)
cfg=step00_corrosion_config();
cfg.reference.flat_column_count=4;
cfg.reference.corrosion_column_count=6;
cfg.preprocessing.main_gaussian_sigma=0;
Z=repmat([1 1 1 1 1 1 1 2 3 4 5 6 7 1 1 1 1 1 1 1],3,1);
[D,raw,uniform,flat,meta]=prepare_positive_corrosion_surface(Z,cfg);
verifyEqual(testCase,flat,1);
verifyEqual(testCase,raw,Z(:,meta.crop_columns)-flat);
verifyEqual(testCase,D,raw);
verifyEqual(testCase,uniform,min(D(:)));
verifyEqual(testCase,mean(D(:)),uniform+mean(D(:)-uniform),'AbsTol',1e-12);
end

function testReferenceIsRangeFractionNotQuantile(testCase)
cfg=step00_corrosion_config();cfg.reference.flat_column_count=4;
cfg.reference.corrosion_column_count=2;
cfg.preprocessing.main_gaussian_sigma=0;
Z=[0 0 0 10 12 13 14 15 16 17 18 19];
[~,~,~,flat]=prepare_positive_corrosion_surface(Z,cfg);
verifyEqual(testCase,flat,2);
end

function testNegativeNotHidden(testCase)
cfg=step00_corrosion_config();cfg.reference.flat_column_count=2;
cfg.reference.corrosion_column_count=2;cfg.preprocessing.main_gaussian_sigma=0;
Z=[10 10 10 2 3 10 10 10];
[D,raw,uniform]=prepare_positive_corrosion_surface(Z,cfg);
verifyLessThan(testCase,uniform,0);
verifyEqual(testCase,D,raw);
end

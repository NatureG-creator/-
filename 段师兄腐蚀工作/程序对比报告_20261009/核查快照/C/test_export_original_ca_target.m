function tests=test_export_original_ca_target
tests=functiontests(localfunctions);
end

function testExportPreservesOriginalValues(testCase)
cfg=step00_corrosion_config();
raw=reshape(1:80,8,10)/1000;
smooth=imgaussfilt(raw,cfg.preprocessing.main_gaussian_sigma);
pit_depth=[.01;.02];diameter=[.1;.15];ratio=pit_depth./diameter;
folder=tempname;mkdir(folder);cleanup=onCleanup(@()rmdir(folder,'s')); %#ok<NASGU>
source=fullfile(folder,'fixture.txt');writematrix([1 2 3;4 5 6],source);
sources=struct('point_cloud_190',source,'point_cloud_50',source);
[path,result]=export_original_ca_target(raw,smooth,min(smooth(:)),pit_depth,ratio,diameter,[2 3;6 7],cfg,sources,folder);
verifyTrue(testCase,isfile(path));
verifyEqual(testCase,result.depth_um,raw*1000,'AbsTol',1e-10);
verifyEqual(testCase,result.target_data(2),mean(smooth(:)-min(smooth(:)))*1000,'AbsTol',1e-10);
verifyEqual(testCase,result.target_data(1),mean(smooth(:))*1000,'AbsTol',1e-10);
verifyEqual(testCase,result.extraction_method,'original_matlab_positive_depth_v2');
verifyEqual(testCase,result.log_depth,log(pit_depth*1000),'AbsTol',1e-12);
verifyEqual(testCase,result.log_ratio,log(1./ratio),'AbsTol',1e-12);
verifyTrue(testCase,result.calibration_ready);
verifyEqual(testCase,result.original_Z_filled_raw,raw);
end

function testNegativeUniformNotClamped(testCase)
cfg=step00_corrosion_config();raw=reshape(1:80,8,10)/1000;
smooth=imgaussfilt(raw,cfg.preprocessing.main_gaussian_sigma);
folder=tempname;mkdir(folder);cleanup=onCleanup(@()rmdir(folder,'s')); %#ok<NASGU>
source=fullfile(folder,'fixture.txt');writematrix([1 2 3;4 5 6],source);
[~,result]=export_original_ca_target(raw,smooth,-.05,[.01;.02],[.1;.2],[.1;.1],[2 3;6 7],cfg, ...
    struct('point_cloud_190',source,'point_cloud_50',source),folder);
verifyFalse(testCase,result.calibration_ready);
verifyEqual(testCase,result.uniform_depth_um,-50);
end

function testAdapterCallsOriginalPitAlgorithm(testCase)
cfg=step00_corrosion_config();
[x,y]=meshgrid(1:50,1:40);
raw=.1+.05*exp(-((x-15).^2+(y-12).^2)/35)+.08*exp(-((x-35).^2+(y-28).^2)/50);
analysis=struct('gaussian_sigma',2,'min_prominence_um',1,'min_distance',15, ...
    'neighborhood',12,'watershed_threshold',.3,'watershed_sigma',.5,'edge_margin',1);
old_visible=get(groot,'defaultFigureVisible');cleanup=onCleanup(@()restore_visible(old_visible)); %#ok<NASGU>
set(groot,'defaultFigureVisible','off');
data=imgaussfilt(raw,cfg.preprocessing.main_gaussian_sigma);
params={'MinProminence',cfg.pit_detection.min_prominence,'MinDistance',cfg.pit_detection.min_distance, ...
    'Neighborhood',cfg.pit_detection.neighborhood};
[h,sjb,diameter,peaks]=jixiantiqu_3D(data,params,.3,.3,cfg);
actual=extract_original_ca_metrics(raw*1000,300,analysis,true(size(raw)),cfg);
good=isfinite(log(h*1000))&isfinite(log(1./sjb))&diameter>0;
verifyEqual(testCase,actual.log_depth,log(h(good)*1000),'AbsTol',1e-10);
verifyEqual(testCase,actual.log_ratio,log(1./sjb(good)),'AbsTol',1e-10);
verifyEqual(testCase,actual.pit_centers_rc_matlab,peaks(good,:));
verifyEqual(testCase,actual.processed_depth_um,data*1000,'AbsTol',1e-10);
verifyGreaterThanOrEqual(testCase,actual.pit_count,2);
end

function restore_visible(visible)
set(groot,'defaultFigureVisible',visible);close all force;
end

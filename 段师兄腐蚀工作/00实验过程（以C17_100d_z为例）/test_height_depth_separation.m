function tests=test_height_depth_separation
tests=functiontests(localfunctions);
end

function testReferenceUnknownDoesNotInventTotalDepth(t)
H=[.6 .4;.2 .3];
c=height_depth_components(H);
verifyEqual(t,c.relative_depth_mm,max(H(:))-H,'AbsTol',1e-12);
verifyEqual(t,c.nonuniform_depth_mm,max(H(:))-mean(H(:)),'AbsTol',1e-12);
verifyTrue(t,isnan(c.uniform_depth_mm));
verifyTrue(t,isnan(c.mean_total_depth_mm));
verifyFalse(t,c.reference_verified);
end

function testVerifiedSameFrameReferenceFollowsDiagram(t)
H=[.6 .4;.2 .3];H0=.8;
c=height_depth_components(H,H0,true);
verifyEqual(t,c.total_depth_mm,H0-H,'AbsTol',1e-12);
verifyEqual(t,c.uniform_depth_mm,H0-max(H(:)),'AbsTol',1e-12);
verifyEqual(t,c.mean_total_depth_mm,c.uniform_depth_mm+c.nonuniform_depth_mm,'AbsTol',1e-12);
end

function testDisplayOffsetDoesNotChangePits(t)
cfg=step00_corrosion_config();
[x,y]=meshgrid(1:50,1:40);
H=.3-.05*exp(-((x-15).^2+(y-12).^2)/35)-.08*exp(-((x-35).^2+(y-28).^2)/50);
old=get(groot,'defaultFigureVisible');cleanup=onCleanup(@()restore_figures(old)); %#ok<NASGU>
set(groot,'defaultFigureVisible','off');
[d,r,w,p]=jixiantiqu_3D(-H,[],[],[],cfg);
[d2,r2,w2,p2]=jixiantiqu_3D(-H,[],[],[],cfg,max(H(:))-H);
verifyEqual(t,{d2,r2,w2,p2},{d,r,w,p});
s=findall(gcf,'Type','surface');
verifyEqual(t,s.ZData,max(H(:))-H,'AbsTol',1e-12);
end

function testRelativeExportIsDiagnosticOnly(t)
cfg=step00_corrosion_config();folder=tempname;mkdir(folder);
cleanup=onCleanup(@()rmdir(folder,'s')); %#ok<NASGU>
file=fullfile(folder,'scan.txt');writematrix([1 2 3;4 5 6],file);
H=reshape(1:80,8,10)/1000;D=max(H(:))-H;
sources=struct('point_cloud_190',file,'point_cloud_50',file, ...
    'depth_kind','relative_to_surface_top','height_raw_mm',H,'height_smoothed_mm',H);
[~,result]=export_original_ca_target(D,D,NaN,[.01;.02],[.1;.2],[.1;.1],[2 3;6 7],cfg,sources,folder);
verifyFalse(t,result.calibration_ready);
verifyTrue(t,isnan(result.target_data(1)));
verifyEqual(t,result.target_data(2),mean(D(:))*1000,'AbsTol',1e-12);
verifyEqual(t,result.height_smoothed_mm,H);
verifyEqual(t,result.relative_depth_um,D*1000);
verifyTrue(t,all(isnan(result.processed_depth_um(:))));
end

function restore_figures(old)
close all force;set(groot,'defaultFigureVisible',old);
end

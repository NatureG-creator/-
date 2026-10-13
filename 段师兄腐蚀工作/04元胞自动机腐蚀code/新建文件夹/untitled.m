N=1;
[baseline, ~,~,depth_map] = moving_avg_3D(a ...
    , 85,2400,280,100);
bj_depth=mean(depth_map(:)-min(depth_map(:)))*space;
%baseline=shujuxiugai(baseline,6);
jicha=mean(baseline(:)-min(baseline(:)));
disp(['不均匀腐蚀深度=',num2str(bj_depth)])
params = {'MinProminence', 0.8, 'MinDistance', 30,'Neighborhood', [40,40]};
yuzhi=0.3;
[shengdu,sjb,zhijin,max_locs, min_locs, boundaries,boundary_coords]=Copy_of_jixiantiqu_3D(baseline,n,params,yuzhi);
shengdu=log(shengdu.*space);
sjb=sjb./10;
jsb=log(1./sjb);
fenbujianyan(jsb)
fenbujianyan(shengdu/1.0)
%quality_loss=(w*l*n-sum(sum(sum(a_output==1))))/(w*l*n);
%Average_depth=quality_loss*n*space;

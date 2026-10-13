N=1;
[baseline, ~,~,depth_map] = moving_avg_3D(a_output ...
    , 5, 100,100,100);
[baseline] = expandMatrix(baseline, N);
bj_depth=mean(depth_map(:)-min(depth_map(:)))*space;
%baseline=shujuxiugai(baseline,6);
jicha=mean(baseline(:)-min(baseline(:)))*space;
disp(['不均匀腐蚀深度=',num2str(jicha)])
params = {'MinProminence', 1, 'MinDistance', 10,'Neighborhood', [10,10]};
yuzhi=0.3;
[shengdu,sjb,zhijin,max_locs, min_locs, boundaries,boundary_coords]=Copy_of_jixiantiqu_3D(baseline,n,params,yuzhi);
shengdu=log(shengdu.*space);
sjb=sjb./10;
jsb=log(1./sjb);
fenbujianyan(jsb)
fenbujianyan(shengdu/1.04)
quality_loss=(w*l*n-sum(sum(sum(a_output==1))))/(w*l*n);
Average_depth=quality_loss*n*space
wucha=0.1*perfect_result(1)+0.3*perfect_result(2)+0.2*perfect_result(3)+0.4*perfect_result(4)
function [shengdu,sjb,zhijin]=fushikengtiqu(data,pits,max_loc,grid_resolution)
num_pits=size(pits,1);
%锈坑数据统计
xiukeng_depth=zeros(size(pits,1),1);
xiukeng_bianjieX=zeros(size(pits,1),1);
xiukeng_bianjieY=zeros(size(pits,1),1);
xiukeng_sjb=zeros(size(pits,1),1);
zhijin=zeros(size(pits,1),1);
for k = 1:num_pits
%提取锈坑深度
     % 4. 计算当前pit的参考面（最小值）
    %xiukeng_cankaomian=min(pits{k}(:,3));
    xiukeng_cankaomian=min(data(:));
    xiukeng_depth(k)= (data(sub2ind(size(data), max_loc(k,1), max_loc(k,2)))-xiukeng_cankaomian);
    xiukeng_bianjieX(k) = range(pits{k}(:,1)).*grid_resolution; 
    xiukeng_bianjieY(k) = range(pits{k}(:,2)).*grid_resolution;
    xiukeng_sjb(k)=(xiukeng_depth(k))/((xiukeng_bianjieX(k)+xiukeng_bianjieY(k))*0.5);
    zhijin(k)=(xiukeng_bianjieX(k)+xiukeng_bianjieY(k))*0.5;
end
shengdu=xiukeng_depth;
sjb=xiukeng_sjb;

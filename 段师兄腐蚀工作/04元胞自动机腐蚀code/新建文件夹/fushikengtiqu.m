function [shengdu,sjb,zhijin]=fushikengtiqu(data,pits,max_loc)
num_pits=size(pits,1);
%锈坑数据统计
xiukeng_depth=zeros(size(pits,1),1);
xiukeng_bianjieX=zeros(size(pits,1),1);
xiukeng_bianjieY=zeros(size(pits,1),1);
xiukeng_sjb=zeros(size(pits,1),1);
zhijin=zeros(size(pits,1),1);
for k = 1:num_pits
%提取锈坑深度
    xiukeng_cankaomian=min(data(:));
    xiukeng_depth(k)= (data(sub2ind(size(data), max_loc(k,1), max_loc(k,2)))-xiukeng_cankaomian+1);
    xiukeng_bianjieX(k) = max(pits{k}(:,1))-min(pits{k}(:,1))+1; 
    xiukeng_bianjieY(k) = max(pits{k}(:,2))-min(pits{k}(:,2))+1;
    xiukeng_sjb(k)=(xiukeng_depth(k))/((xiukeng_bianjieX(k)+xiukeng_bianjieY(k))*0.5);
    zhijin(k)=(xiukeng_bianjieX(k)+xiukeng_bianjieY(k))*0.5;
end
shengdu=xiukeng_depth;
sjb=xiukeng_sjb;

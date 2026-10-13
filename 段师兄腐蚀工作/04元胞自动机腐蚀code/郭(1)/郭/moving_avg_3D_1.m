function [baseline, smoothed_data,retention_ratio,depth_map] = moving_avg_3D(a, window_size, w,l,n)
% 输入参数:
%   a            : 三维逻辑数组 (n×n×(n+1))，0表示腐蚀区域
%   window_size  : 滑动窗口尺寸 (建议奇数)
%   n            : 空间分辨率

% 腐蚀深度提取
	depth_map = zeros(w, l);
for i = 1:w
    for j = 1:l
        % 寻找第一个腐蚀层（从表面向下）
        depth = find(squeeze(a(i,j,:)) == 1, 1, 'first');
        if isempty(depth)
            depth_map(i,j) = n + 1; % 如果没有腐蚀层，设置为最大深度
        else
            depth_map(i,j) = depth; % 存储找到的腐蚀层深度
        end
    end
end

data=depth_map;

% 二维高斯滤波
sigma = 1;
smoothed_data = imgaussfilt(data, sigma);

% 镜像边界扩展
half_win = floor(window_size/2);
data_ext = padarray(smoothed_data, [half_win, half_win], 'symmetric');

% 二维移动平均
kernel = ones(window_size) / window_size^2;
baseline_ext = conv2(data_ext, kernel, 'same');

% 裁剪有效部分
baseline = baseline_ext(half_win+1:end-half_win, half_win+1:end-half_win);

% 基线校正
corrected_data = data - baseline;

% 特征保留度评估（需要安装Image Processing Toolbox）
if license('test','image_toolbox')
    original_peaks = imregionalmax(data);
    corrected_peaks = imregionalmax(corrected_data);
    retention_ratio = sum(corrected_peaks(:))/sum(original_peaks(:));
    %disp(['特征保留率: ', num2str(retention_ratio*100, '%.1f'), '%']);
end
%figure;
%colormap(jet)
 
%subplot(2,2,1)
%surf(1:n, 1:n, data, 'EdgeColor','none')
%title('原始腐蚀深度'), axis tight, view(-45,30)
 
%subplot(2,2,2)
%surf(1:n, 1:n, baseline, 'EdgeColor','none')
%title('估计基线'), axis tight, view(-45,30)
 
%subplot(2,2,3)
%surf(1:n, 1:n, corrected_data, 'EdgeColor','none')
%title('校正后表面'), axis tight, view(-45,30)

%subplot(2,2,4)
%surf(1:n, 1:n, smoothed_data, 'EdgeColor','none')
%title('平滑后表面'), axis tight, view(-45,30)
%subplot(2,2,4)

% 对数据进行处理
end



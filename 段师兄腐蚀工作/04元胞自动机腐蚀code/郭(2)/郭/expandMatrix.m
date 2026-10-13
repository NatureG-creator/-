function [expandedMatrix] = expandMatrix(originalMatrix, N)
    % 获取原始矩阵的尺寸
    [rows, cols] = size(originalMatrix);
    
    % 计算新的尺寸
    newRows = rows * N;
    newCols = cols * N;
    
    % 使用imresize函数扩展矩阵
    expandedMatrix = imresize(originalMatrix, [newRows, newCols], 'nearest');
    
    % 显示原始图像和扩展后的图像
    %figure;
    %subplot(1, 2, 1);
    %imagesc(originalMatrix);
    %colormap(jet);
    %colorbar;
    %title('原始图像');
    
    %subplot(1, 2, 2);
    %imagesc(expandedMatrix);
    %colormap(jet);
    %colorbar;
    %title(['扩展后的图像，尺寸为 ', num2str(newRows), 'x', num2str(newCols)]);
end
function record = find_best_fit_record(package_or_records,material,metric)
%FIND_BEST_FIT_RECORD 按材料和指标查找一条统一拟合记录。

if isstruct(package_or_records) && isscalar(package_or_records) && ...
        isfield(package_or_records,'records')
    records = package_or_records.records;
else
    records = package_or_records;
end
if isempty(records)
    error('BestFit:MissingRecord','统一拟合结果中没有记录。');
end

materials = string({records.Material})';
metrics = string({records.Metric})';
index = find(strcmpi(materials,string(material)) & ...
    strcmpi(metrics,string(metric)));
if numel(index) ~= 1
    error('BestFit:MissingRecord', ...
        '无法唯一找到材料%s、指标%s的拟合记录。',material,metric);
end
record = records(index);
end

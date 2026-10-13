function y = evaluate_best_fit_model(model_name,parameters,x)
%EVALUATE_BEST_FIT_MODEL 使用统一模型名称和完整参数计算预测值。

model_name = string(model_name);
parameters = double(parameters(:)');
x = double(x);

switch model_name
    case "线性函数"
        require_parameters(parameters,2,model_name);
        y = parameters(1).*x+parameters(2);
    case "二次函数"
        require_parameters(parameters,3,model_name);
        y = parameters(1).*x.^2+parameters(2).*x+parameters(3);
    case "幂函数"
        require_parameters(parameters,2,model_name);
        y = parameters(1).*x.^parameters(2);
    case "对数函数"
        require_parameters(parameters,2,model_name);
        y = parameters(1).*log(x)+parameters(2);
    case "指数函数"
        require_parameters(parameters,2,model_name);
        y = parameters(1).*exp(parameters(2).*x);
    case "指数饱和函数"
        require_parameters(parameters,3,model_name);
        y = parameters(1).*(1-exp(-parameters(2).*x))+parameters(3);
    case "双曲线饱和函数"
        require_parameters(parameters,3,model_name);
        y = parameters(1).*x./(parameters(2)+x)+parameters(3);
    case "连续两阶段幂函数"
        require_parameters(parameters,4,model_name);
        a = parameters(1);
        n1 = parameters(2);
        n2 = parameters(3);
        breakPoint = parameters(4);
        y = zeros(size(x));
        left = x < breakPoint;
        y(left) = a.*x(left).^n1;
        y(~left) = a.*breakPoint.^(n1-n2).*x(~left).^n2;
    case "两阶段对数模型"
        require_parameters(parameters,3,model_name);
        a = parameters(1);
        b = parameters(2);
        breakPoint = parameters(3);
        y = zeros(size(x));
        left = x < breakPoint;
        y(left) = x(left).^a;
        y(~left) = breakPoint.^(a-b).*x(~left).^b;
    case "均值模型"
        require_parameters(parameters,1,model_name);
        y = repmat(parameters(1),size(x));
    otherwise
        error('BestFit:UnknownModel','未知拟合函数：%s',model_name);
end
end

function require_parameters(parameters,count,modelName)
if numel(parameters) < count || any(~isfinite(parameters(1:count)))
    error('BestFit:InvalidParameters', ...
        '%s至少需要%d个有限参数。',modelName,count);
end
end

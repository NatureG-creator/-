function formula = format_best_fit_formula( ...
        model_name,parameters,digits,x_name,y_name)
%FORMAT_BEST_FIT_FORMULA 按指定小数位数生成显示公式。

if nargin < 3 || isempty(digits)
    digits = 4;
end
if nargin < 4 || isempty(x_name)
    x_name = "x";
end
if nargin < 5 || isempty(y_name)
    y_name = "y";
end
validateattributes(digits,{'numeric'}, ...
    {'scalar','integer','nonnegative','finite'});

model_name = string(model_name);
parameters = double(parameters(:)');
x_name = string(x_name);
y_name = string(y_name);
number = @(value) string(sprintf(['%.' num2str(digits) 'f'],value));

switch model_name
    case "线性函数"
        formula = y_name+" = "+number(parameters(1))+"*"+x_name+ ...
            signed_constant(parameters(2),number);
    case "二次函数"
        formula = y_name+" = "+number(parameters(1))+"*"+x_name+"^2"+ ...
            signed_term(parameters(2),"*"+x_name,number)+ ...
            signed_constant(parameters(3),number);
    case "幂函数"
        formula = y_name+" = "+number(parameters(1))+"*"+x_name+ ...
            "^"+number(parameters(2));
    case "对数函数"
        formula = y_name+" = "+number(parameters(1))+"*ln("+x_name+")"+ ...
            signed_constant(parameters(2),number);
    case "指数函数"
        formula = y_name+" = "+number(parameters(1))+"*exp("+ ...
            number(parameters(2))+"*"+x_name+")";
    case "指数饱和函数"
        formula = y_name+" = "+number(parameters(1))+"*(1-exp(-"+ ...
            number(parameters(2))+"*"+x_name+"))"+ ...
            signed_constant(parameters(3),number);
    case "双曲线饱和函数"
        formula = y_name+" = "+number(parameters(1))+"*"+x_name+ ...
            "/("+number(parameters(2))+"+"+x_name+")"+ ...
            signed_constant(parameters(3),number);
    case "连续两阶段幂函数"
        breakPoint = number(parameters(4));
        formula = x_name+" < "+breakPoint+": "+y_name+" = "+ ...
            number(parameters(1))+"*"+x_name+"^"+number(parameters(2))+ ...
            "; "+x_name+" >= "+breakPoint+": "+y_name+" = "+ ...
            number(parameters(1))+"*"+breakPoint+"^("+ ...
            number(parameters(2))+"-"+number(parameters(3))+ ")*"+ ...
            x_name+"^"+number(parameters(3));
    case "两阶段对数模型"
        breakPoint = number(parameters(3));
        formula = x_name+" < "+breakPoint+": ln("+y_name+") = "+ ...
            number(parameters(1))+"*ln("+x_name+"); "+ ...
            x_name+" >= "+breakPoint+": ln("+y_name+") = "+ ...
            number(parameters(1))+"*ln("+breakPoint+") + "+ ...
            number(parameters(2))+"*ln("+x_name+"/"+breakPoint+")";
    case "均值模型"
        formula = y_name+" = "+number(parameters(1));
        if numel(parameters) >= 2 && isfinite(parameters(2))
            formula = formula+" (std = "+number(parameters(2))+")";
        end
    otherwise
        error('BestFit:UnknownModel','未知拟合函数：%s',model_name);
end
end

function text = signed_constant(value,number)
if value < 0
    text = " - "+number(abs(value));
else
    text = " + "+number(value);
end
end

function text = signed_term(value,suffix,number)
if value < 0
    text = " - "+number(abs(value))+suffix;
else
    text = " + "+number(value)+suffix;
end
end

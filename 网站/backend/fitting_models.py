"""显式回归模型和不执行 Python 源码的安全表达式解释器。"""
import ast
import operator
from dataclasses import dataclass
import numpy as np
from scipy.special import expit


FUNCTIONS = {'exp': np.exp, 'log': np.log, 'sqrt': np.sqrt, 'sin': np.sin,
             'cos': np.cos, 'tanh': np.tanh, 'abs': np.abs}
BINARY = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
          ast.Div: operator.truediv, ast.Pow: operator.pow}


def expression(formula, parameters):
    if not isinstance(formula, str) or not formula.strip() or len(formula)>400:
        raise ValueError('自定义公式不能为空且不得超过400字符')
    if not parameters or len(parameters)>8 or len(set(parameters))!=len(parameters):
        raise ValueError('自定义参数需为1–8个不重复名称')
    for p in parameters:
        if not isinstance(p,str) or not p.isidentifier() or p.startswith('_') or p in {'x', *FUNCTIONS}:
            raise ValueError('自定义参数名称非法')
    try: tree=ast.parse(formula, mode='eval')
    except (SyntaxError, RecursionError) as exc: raise ValueError('自定义公式语法错误') from exc
    if len(list(ast.walk(tree)))>120: raise ValueError('自定义公式过于复杂')
    def check(node, depth=0):
        if depth>20: raise ValueError('自定义公式嵌套过深')
        if isinstance(node,ast.Constant) and type(node.value) in (int,float) and np.isfinite(node.value) and abs(node.value)<=1e6: return
        if isinstance(node,ast.Name) and node.id in {'x',*parameters}: return
        if isinstance(node,ast.BinOp) and type(node.op) in BINARY:
            check(node.left,depth+1); check(node.right,depth+1); return
        if isinstance(node,ast.UnaryOp) and isinstance(node.op,(ast.UAdd,ast.USub)):
            check(node.operand,depth+1); return
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id in FUNCTIONS and len(node.args)==1 and not node.keywords:
            check(node.args[0],depth+1); return
        raise ValueError('自定义公式包含禁用语法；仅支持参数、x、四则运算、幂与白名单函数')
    check(tree.body)
    def interpret(node, env):
        if isinstance(node,ast.Constant): return float(node.value)
        if isinstance(node,ast.Name): return env[node.id]
        if isinstance(node,ast.BinOp): return BINARY[type(node.op)](interpret(node.left,env),interpret(node.right,env))
        if isinstance(node,ast.UnaryOp): return (-1 if isinstance(node.op,ast.USub) else 1)*interpret(node.operand,env)
        return FUNCTIONS[node.func.id](interpret(node.args[0],env))
    def function(x,p): return interpret(tree.body,dict(zip(parameters,p),x=x))
    return function


@dataclass
class Model:
    id: str
    label: str
    formula: str
    parameters: list
    function: object
    positive_x: bool=False


MODELS = [
    Model('linear','线性','a*x+b',['a','b'],lambda x,p:p[0]*x+p[1]),
    Model('polynomial2','二阶多项式','a*x^2+b*x+c',['a','b','c'],lambda x,p:np.polyval(p,x)),
    Model('polynomial3','三阶多项式','a*x^3+b*x^2+c*x+d',['a','b','c','d'],lambda x,p:np.polyval(p,x)),
    Model('power','幂函数','a*x^b',['a','b'],lambda x,p:p[0]*np.power(x,p[1]),True),
    Model('exponential','指数','a*exp(b*x)',['a','b'],lambda x,p:p[0]*np.exp(p[1]*x)),
    Model('logarithmic','对数','a*log(x)+b',['a','b'],lambda x,p:p[0]*np.log(x)+p[1],True),
    Model('saturation','饱和','a*x/(b+x)',['a','b'],lambda x,p:p[0]*x/(p[1]+x),True),
    Model('logistic','Logistic','a/(1+exp(-b*(x-c)))',['a','b','c'],lambda x,p:p[0]*expit(p[1]*(x-p[2]))),
    Model('gompertz','Gompertz','a*exp(-exp(-b*(x-c)))',['a','b','c'],lambda x,p:p[0]*np.exp(-np.exp(-p[1]*(x-p[2])))),
    Model('piecewise','连续分段线性','a+b*x+c*max(0,x-d)',['a','b','c','d'],lambda x,p:p[0]+p[1]*x+p[2]*np.maximum(0,x-p[3])),
]


def model_catalog():
    return [dict(id=m.id,label=m.label,formula=m.formula,parameters=m.parameters,positive_x=m.positive_x) for m in MODELS]+[dict(id='custom',label='自定义安全公式',formula='',parameters=[])]

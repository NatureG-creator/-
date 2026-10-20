"""Two-predictor regression for the fitting workbench.

The module is intentionally separate from the established one-predictor engine:
existing fitting results and contracts remain unchanged while ``Y=f(X1, X2)``
gets a small, auditable response-surface implementation.
"""
from __future__ import annotations

import ast
import math
import operator

import numpy as np


METRICS = ('cv_rmse', 'cv_mae', 'rmse', 'mae', 'r2', 'adjusted_r2', 'aicc', 'bic')


def profile_multivariate_data(dataset, labels=None):
    """Return explainable, non-binding data and plot suggestions before fitting."""
    x1 = np.asarray(dataset.get('x1', []), dtype=float)
    x2 = np.asarray(dataset.get('x2', []), dtype=float)
    y = np.asarray(dataset.get('y', []), dtype=float)
    names = [str(value).lower() for value in (labels or [])]
    name_text = ' '.join(names)
    monotonic = all(np.all(np.diff(values) >= 0) or np.all(np.diff(values) <= 0) for values in (x1, x2) if len(values) > 1)
    positive = bool(len(x1) and np.all(x1 > 0) and np.all(x2 > 0))
    if any(token in name_text for token in ('time', 'day', 'age', '腐蚀', '退化')) and monotonic:
        kind = '时间/退化响应面'; reason = '依据：列名包含时间或退化提示，且两个自变量整体单调。'
        models = ['linear2', 'interaction2', 'quadratic2']; plots = ['三维响应面', '等高线', '时间切片', '残差图']
    elif any(token in name_text for token in ('depth', 'height', 'position', 'x', 'y', 'z', '点云')):
        kind = '点云剖面响应面'; reason = '依据：列名包含位置、深度或点云提示，优先保留低阶响应面并检查外推。'
        models = ['linear2', 'interaction2', 'quadratic2']; plots = ['三维散点与曲面', '等高线', '剖面切片', '残差图']
    else:
        kind = '通用双自变量'; reason = f'依据：未识别明确物理语义；样本{len(y)}行，正值={positive}，整体单调={monotonic}，采用通用候选池。'
        models = ['linear2', 'interaction2', 'quadratic2']; plots = ['三维散点与曲面', '等高线', '切片图', '残差图']
    return {'type': kind, 'reason': reason, 'recommended_models': models, 'recommended_plots': plots,
            'features': {'rows': int(len(y)), 'x1_positive': positive, 'x2_positive': positive, 'monotonic': monotonic,
                         'x1_range': [float(np.min(x1)), float(np.max(x1))] if len(x1) else [],
                         'x2_range': [float(np.min(x2)), float(np.max(x2))] if len(x2) else [],
                         'y_range': [float(np.min(y)), float(np.max(y))] if len(y) else []}}


def _safe_formula(formula, parameters):
    if not isinstance(formula, str) or not formula.strip() or len(formula) > 400:
        raise ValueError('自定义二元公式不能为空且不得超过400字符')
    if not isinstance(parameters, list) or not 1 <= len(parameters) <= 8:
        raise ValueError('自定义二元公式参数数量须为1–8')
    if len(set(parameters)) != len(parameters):
        raise ValueError('自定义二元公式参数不能重复')
    functions = {'exp': np.exp, 'log': np.log, 'sqrt': np.sqrt, 'sin': np.sin,
                 'cos': np.cos, 'tanh': np.tanh, 'abs': np.abs}
    binary = {ast.Add: operator.add, ast.Sub: operator.sub,
              ast.Mult: operator.mul, ast.Div: operator.truediv,
              ast.Pow: operator.pow}
    for name in parameters:
        if not isinstance(name, str) or not name.isidentifier() or name.startswith('_') or name in {'x1', 'x2', *functions}:
            raise ValueError('自定义二元公式参数名称非法')
    try:
        tree = ast.parse(formula, mode='eval')
    except (SyntaxError, RecursionError) as exc:
        raise ValueError('自定义二元公式语法错误') from exc
    if len(list(ast.walk(tree))) > 120:
        raise ValueError('自定义二元公式过于复杂')

    def check(node, depth=0):
        if depth > 20:
            raise ValueError('自定义二元公式嵌套过深')
        if isinstance(node, ast.Constant) and type(node.value) in (int, float) and np.isfinite(node.value) and abs(node.value) <= 1e6:
            return
        if isinstance(node, ast.Name) and node.id in {'x1', 'x2', *parameters}:
            return
        if isinstance(node, ast.BinOp) and type(node.op) in binary:
            check(node.left, depth + 1); check(node.right, depth + 1); return
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            check(node.operand, depth + 1); return
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in functions and len(node.args) == 1 and not node.keywords:
            check(node.args[0], depth + 1); return
        raise ValueError('自定义二元公式包含禁用语法')

    check(tree.body)

    def interpret(node, env):
        if isinstance(node, ast.Constant):
            return float(node.value)
        if isinstance(node, ast.Name):
            return env[node.id]
        if isinstance(node, ast.BinOp):
            return binary[type(node.op)](interpret(node.left, env), interpret(node.right, env))
        if isinstance(node, ast.UnaryOp):
            return (-1 if isinstance(node.op, ast.USub) else 1) * interpret(node.operand, env)
        return functions[node.func.id](interpret(node.args[0], env))

    def evaluate(x1, x2, params):
        value = interpret(tree.body, dict(zip(parameters, params), x1=x1, x2=x2))
        return np.asarray(value, dtype=float)

    return evaluate


def normalise_multivariate_options(options=None):
    raw = dict(options or {})
    result = dict(models=['linear2', 'interaction2', 'quadratic2'], metric='cv_rmse', folds=5, seed=42)
    allowed = set(result) | {'custom_formula', 'custom_parameters', 'custom_initial', 'custom_lower', 'custom_upper'}
    unknown = set(raw) - allowed
    if unknown:
        raise ValueError('未知双自变量拟合选项：' + ', '.join(sorted(map(str, unknown))))
    result.update(raw)
    known = {'linear2', 'interaction2', 'quadratic2', 'custom2'}
    if not isinstance(result['models'], list) or not 1 <= len(result['models']) <= 8 or len(set(result['models'])) != len(result['models']):
        raise ValueError('双自变量候选模型须为1–8个且不能重复')
    if any(model not in known for model in result['models']):
        raise ValueError('未知双自变量模型')
    if result['metric'] not in METRICS:
        raise ValueError('未知双自变量评价指标')
    if isinstance(result['folds'], bool) or not isinstance(result['folds'], int) or not 2 <= result['folds'] <= 5:
        raise ValueError('双自变量交叉验证折数须为2–5')
    if isinstance(result['seed'], bool) or not isinstance(result['seed'], int) or not 0 <= result['seed'] <= 2**32 - 1:
        raise ValueError('双自变量随机种子非法')
    if 'custom2' in result['models']:
        params = result.get('custom_parameters', ['a', 'b', 'c'])
        if isinstance(params, str):
            params = [part.strip() for part in params.split(',') if part.strip()]
        result['custom_parameters'] = params
        _safe_formula(result.get('custom_formula', ''), params)
        size = len(params)
        for key, default in [('custom_initial', [1.0] * size), ('custom_lower', [None] * size), ('custom_upper', [None] * size)]:
            value = result.get(key, default)
            if isinstance(value, str):
                value = [float(part.strip()) for part in value.split(',')]
            if value is None or len(value) != size:
                raise ValueError('自定义二元公式参数边界长度不一致')
            result[key] = value
    return result


def multivariate_model_catalog():
    return [
        {'id': 'linear2', 'label': '二元线性', 'formula': 'a*x1+b*x2+c', 'parameters': ['a', 'b', 'c']},
        {'id': 'interaction2', 'label': '二元交互项', 'formula': 'a*x1+b*x2+c*x1*x2+d', 'parameters': ['a', 'b', 'c', 'd']},
        {'id': 'quadratic2', 'label': '二元二次响应面', 'formula': 'a*x1^2+b*x2^2+c*x1*x2+d*x1+e*x2+f', 'parameters': ['a', 'b', 'c', 'd', 'e', 'f']},
        {'id': 'custom2', 'label': '自定义二元安全公式', 'formula': '', 'parameters': []},
    ]


def _model(model_id, options):
    if model_id == 'linear2':
        return ['a', 'b', 'c'], 'a*x1+b*x2+c', lambda x1, x2: np.column_stack([x1, x2, np.ones(len(x1))])
    if model_id == 'interaction2':
        return ['a', 'b', 'c', 'd'], 'a*x1+b*x2+c*x1*x2+d', lambda x1, x2: np.column_stack([x1, x2, x1 * x2, np.ones(len(x1))])
    if model_id == 'quadratic2':
        return ['a', 'b', 'c', 'd', 'e', 'f'], 'a*x1^2+b*x2^2+c*x1*x2+d*x1+e*x2+f', lambda x1, x2: np.column_stack([x1**2, x2**2, x1*x2, x1, x2, np.ones(len(x1))])
    params = options['custom_parameters']
    expression = _safe_formula(options['custom_formula'], params)
    return params, options['custom_formula'], lambda x1, x2: _custom_design(expression, x1, x2, len(params))


def _custom_design(expression, x1, x2, count):
    base = np.zeros((len(x1), count), dtype=float)
    for column in range(count):
        params = np.zeros(count, dtype=float); params[column] = 1.0
        plus = expression(x1, x2, params)
        params[column] = -1.0
        minus = expression(x1, x2, params)
        base[:, column] = (plus - minus) / 2.0
    # A custom formula is linear in its declared parameters for this first release.
    zero = expression(x1, x2, np.zeros(count, dtype=float))
    return np.column_stack([base, zero])


def _finite_prediction(matrix, params):
    output = np.asarray(matrix @ params, dtype=float)
    if output.ndim != 1 or not np.all(np.isfinite(output)):
        raise ValueError('模型产生非有限预测值')
    return output


def _metrics(y, fitted, cv_predictions, parameter_count):
    residual = fitted - y
    rmse = float(np.sqrt(np.mean(residual**2)))
    mae = float(np.mean(np.abs(residual)))
    centered = y - np.mean(y)
    total = float(np.sum(centered**2))
    r2 = None if total <= np.finfo(float).eps * max(float(np.sum(y**2)), 1.0) else float(1.0 - np.sum(residual**2) / total)
    adjusted = None if r2 is None or len(y) <= parameter_count + 1 else float(1.0 - (1.0 - r2) * (len(y) - 1) / (len(y) - parameter_count - 1))
    cv = np.asarray(cv_predictions, dtype=float)
    valid = np.isfinite(cv)
    cv_rmse = float(np.sqrt(np.mean((cv[valid] - y[valid])**2))) if np.all(valid) else None
    cv_mae = float(np.mean(np.abs(cv[valid] - y[valid]))) if np.all(valid) else None
    rss = max(float(np.sum(residual**2)), np.finfo(float).tiny)
    n = len(y); k = parameter_count + 1
    bic = float(n * np.log(rss / n) + k * np.log(n)) if n > k else None
    aicc = None
    if n > k + 1:
        aic = n * np.log(rss / n) + 2 * k
        aicc = float(aic + 2 * k * (k + 1) / (n - k - 1))
    return {'cv_rmse': cv_rmse, 'cv_mae': cv_mae, 'rmse': rmse, 'mae': mae, 'r2': r2, 'adjusted_r2': adjusted, 'aicc': aicc, 'bic': bic}


def _fit_one(model_id, x1, x2, y, options):
    params, formula, design_builder = _model(model_id, options)
    design = design_builder(x1, x2)
    # The custom design includes its intercept as the last column; built-ins already do too.
    if design.shape[1] != len(params):
        raise ValueError('自定义二元公式必须对参数线性可识别，且参数数量与设计矩阵一致')
    if len(y) <= len(params):
        raise ValueError(f'数据点不足：至少需要多于{len(params)}个观测')
    rank = int(np.linalg.matrix_rank(design))
    if rank < len(params):
        raise ValueError('自变量共线或参数不可识别')
    condition_number = float(np.linalg.cond(design))
    coefficient, _, _, _ = np.linalg.lstsq(design, y, rcond=None)
    fitted = _finite_prediction(design, coefficient)
    folds = min(options['folds'], len(y))
    indices = np.arange(len(y)); rng = np.random.default_rng(options['seed'])
    rng.shuffle(indices)
    predictions = np.full(len(y), np.nan, dtype=float)
    for test in np.array_split(indices, folds):
        train = np.setdiff1d(indices, test, assume_unique=False)
        train_design = design_builder(x1[train], x2[train])
        if np.linalg.matrix_rank(train_design) < len(params):
            raise ValueError('交叉验证训练折参数不可识别')
        fold_params, _, _, _ = np.linalg.lstsq(train_design, y[train], rcond=None)
        predictions[test] = _finite_prediction(design_builder(x1[test], x2[test]), fold_params)
    metrics = _metrics(y, fitted, predictions, len(params) - 1)
    warnings = []
    if not np.isfinite(condition_number) or condition_number > 1e10:
        warnings.append(f'设计矩阵条件数为{condition_number:.3g}，建议统一X1/X2单位或中心化后复核。')
    return {
        'id': model_id, 'label': next((item['label'] for item in multivariate_model_catalog() if item['id'] == model_id), model_id),
        'formula': formula, 'status': 'ok', 'error': None, 'parameters': dict(zip(params, coefficient.tolist())),
        'metrics': metrics, 'cv_valid': bool(np.all(np.isfinite(predictions))), 'cv_predictions': predictions.tolist(),
        'y_fitted': fitted.tolist(), 'residuals': (fitted - y).tolist(), 'parameter_count': len(params), 'jacobian_rank': rank,
        'condition_number': condition_number, 'warnings': warnings,
    }


def fit_multivariate_dataset(dataset, options=None, progress=None):
    options = normalise_multivariate_options(options)
    x1 = np.asarray(dataset.get('x1', []), dtype=float); x2 = np.asarray(dataset.get('x2', []), dtype=float); y = np.asarray(dataset.get('y', []), dtype=float)
    if x1.ndim != 1 or x2.shape != x1.shape or y.shape != x1.shape or not 3 <= len(y) <= 5000 or not np.all(np.isfinite(x1)) or not np.all(np.isfinite(x2)) or not np.all(np.isfinite(y)):
        raise ValueError('X1、X2、Y必须是长度一致的3–5000个有限数')
    if np.ptp(x1) == 0 or np.ptp(x2) == 0:
        # Keep the error at the candidate level so other groups/candidates remain auditable.
        constant_predictor = True
    else:
        constant_predictor = False
    labels = dataset.get('groups') or ['全部数据'] * len(y)
    if len(labels) != len(y):
        raise ValueError('双自变量分类标签长度不匹配')
    labels = [str(value) for value in labels]
    unique = list(dict.fromkeys(labels))
    if len(unique) > 10:
        raise ValueError('每次最多10个分类组')
    row_ids = dataset.get('row_ids', list(range(1, len(y) + 1)))
    if len(row_ids) != len(y):
        raise ValueError('双自变量原始行号长度不匹配')
    result = {'mode': 'multivariate2', 'metric': options['metric'], 'options': options, 'groups': [], 'warnings': ['双自变量推荐仅限所选响应面模型和验证规则；不代表外推物理定律']}
    total = len(unique) * len(options['models']); completed = 0
    for label in unique:
        indices = np.flatnonzero(np.asarray(labels) == label)
        gx1, gx2, gy = x1[indices], x2[indices], y[indices]
        group = {'label': label, 'x1': gx1.tolist(), 'x2': gx2.tolist(), 'y': gy.tolist(), 'row_ids': [row_ids[i] for i in indices], 'recommended_id': None, 'reason': '', 'candidates': []}
        for model_id in options['models']:
            try:
                if constant_predictor:
                    raise ValueError('X1或X2为常量，参数不可识别')
                candidate = _fit_one(model_id, gx1, gx2, gy, options)
            except Exception as exc:
                params, formula, _ = _model(model_id, options)
                candidate = {'id': model_id, 'label': next(item['label'] for item in multivariate_model_catalog() if item['id'] == model_id), 'formula': formula, 'status': 'failed', 'error': str(exc), 'parameters': {}, 'metrics': {metric: None for metric in METRICS}, 'cv_valid': False, 'cv_predictions': [None] * len(gy), 'y_fitted': [], 'residuals': [], 'parameter_count': len(params), 'jacobian_rank': 0, 'condition_number': None, 'warnings': []}
            group['candidates'].append(candidate); completed += 1
            if progress:
                progress({'phase': 'fitting', 'progress': completed / total, 'message': f'完成 {label} / {candidate["label"]}'})
        eligible = [c for c in group['candidates'] if c['status'] == 'ok' and c['cv_valid'] and c['metrics'].get(options['metric']) is not None and c.get('jacobian_rank') == c.get('parameter_count')]
        if eligible:
            sign = -1 if options['metric'] in {'r2', 'adjusted_r2'} else 1
            eligible.sort(key=lambda c: (sign * c['metrics'][options['metric']], c['parameter_count']))
            best = eligible[0]
            if options['metric'] in {'cv_rmse', 'cv_mae', 'rmse', 'mae'}:
                score = float(best['metrics'][options['metric']])
                tolerance = np.finfo(float).eps * max(float(np.max(np.abs(gy))), 1.0)
                near = [candidate for candidate in eligible if candidate['metrics'][options['metric']] <= score * (1.0 + 1e-8) + tolerance]
                best = min(near, key=lambda candidate: candidate['parameter_count'])
            group['recommended_id'] = best['id']; group['reason'] = f'按{options["metric"]}比较，优先选择验证有效且参数满秩的候选；近似并列时选择更简单模型'
        else:
            group['reason'] = '缺少有效且可比较的双自变量候选模型'
        result['groups'].append(group)
    return result

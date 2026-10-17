"""有预算限制、原始Y尺度误差及训练内重拟合的显式函数比较。"""
import math
import numpy as np
from scipy.optimize import least_squares
from scipy.stats import t
from .fitting_models import MODELS, Model, expression, model_catalog

METRICS=('cv_rmse','cv_mae','aicc','bic','rmse','mae','r2','adjusted_r2')


def _normalise_fit_options(options=None):
    raw=dict(options or {})
    o=dict(models=['linear','polynomial2','power','exponential'],metric='cv_rmse',validation='kfold',folds=5,seed=42,loss='linear',prediction_points=201)
    allowed=set(o)|{'custom_formula','custom_parameters','custom_initial','custom_lower','custom_upper','prediction_min','prediction_max'}
    if set(raw)-allowed: raise ValueError('未知拟合选项：'+', '.join(str(k) for k in set(raw)-allowed))
    o.update(raw)
    if not isinstance(o['models'],list) or any(not isinstance(m,str) for m in o['models']): raise ValueError('models必须为模型名称列表')
    if not isinstance(o['models'],list) or not 1<=len(o['models'])<=12 or len(set(o['models']))!=len(o['models']): raise ValueError('候选模型数量须为1–12且不能重复')
    known={m.id for m in MODELS}|{'custom'}
    if any(m not in known for m in o['models']): raise ValueError('未知模型')
    if o['metric'] not in METRICS: raise ValueError('未知评价指标')
    if o['validation'] not in ('kfold','loo','time','group'): raise ValueError('未知验证方式')
    if o['loss'] not in ('linear','soft_l1'): raise ValueError('未知损失函数')
    for name,lo,hi in [('folds',2,5),('prediction_points',2,501),('seed',0,2**32-1)]:
        value=o[name]
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or int(value)!=value or not lo<=value<=hi: raise ValueError(f'{name}超出允许范围')
        o[name]=int(value)
    for key in ('prediction_min','prediction_max'):
        if o.get(key) is not None:
            if isinstance(o[key],bool): raise ValueError('预测范围不能为布尔值')
            o[key]=float(o[key])
            if not np.isfinite(o[key]): raise ValueError('预测范围须为有限数')
    if o.get('prediction_min') is not None and o.get('prediction_max') is not None and o['prediction_min']>=o['prediction_max']: raise ValueError('预测范围上下界错误')
    if 'custom' in o['models']:
        parameters=o.get('custom_parameters',['a','b'])
        if isinstance(parameters,str): parameters=[p.strip() for p in parameters.split(',') if p.strip()]
        expression(o.get('custom_formula',''),parameters)
        o['custom_parameters']=parameters
        k=len(parameters)
        for key,default in [('custom_initial',[1.]*k),('custom_lower',[-np.inf]*k),('custom_upper',[np.inf]*k)]:
            values=o.get(key,default)
            if values is None: values=default
            if isinstance(values,str): values=[float(s.strip()) for s in values.split(',')]
            if len(values)!=k: raise ValueError('自定义参数、初值和边界长度不一致')
            if key in ('custom_lower','custom_upper'):
                values=[(-np.inf if key=='custom_lower' else np.inf) if v is None else v for v in values]
            arr=np.asarray(values,float)
            if np.any(np.isnan(arr)) or (key=='custom_initial' and not np.all(np.isfinite(arr))): raise ValueError('自定义初值/边界非法')
            o[key]=arr.tolist()
        if np.any(np.asarray(o['custom_lower'])>=o['custom_upper']): raise ValueError('参数下界必须小于上界')
        if np.any(np.asarray(o['custom_initial'])<o['custom_lower']) or np.any(np.asarray(o['custom_initial'])>o['custom_upper']): raise ValueError('初值必须位于参数边界内')
        o['custom_lower']=[v if np.isfinite(v) else None for v in o['custom_lower']]
        o['custom_upper']=[v if np.isfinite(v) else None for v in o['custom_upper']]
    return o


def normalise_fit_options(options=None):
    try:
        return _normalise_fit_options(options)
    except (TypeError, OverflowError, AttributeError) as exc:
        raise ValueError('拟合选项类型或数值非法') from exc


def _predict(model,x,p):
    try:
        with np.errstate(all='ignore'):
            raw=np.asarray(model.function(np.asarray(x,float),p))
            if np.iscomplexobj(raw): raise ValueError('模型产生复数；仅支持实数回归')
            out=np.asarray(raw,float)
            out=np.broadcast_to(out,np.shape(x)).copy()
    except (ArithmeticError,TypeError) as exc:
        raise ValueError('模型计算失败：'+str(exc)) from exc
    if not np.all(np.isfinite(out)): raise ValueError('模型计算产生非有限值或超出函数定义域')
    return out


def _fit(model,x,y,sigma,o):
    k=len(model.parameters)
    if len(x)<=k: raise ValueError(f'数据点不足：需要多于{k}个观测')
    if np.ptp(x)==0: raise ValueError('X为常量，参数不可识别')
    if model.positive_x and np.any(x<=0): raise ValueError('该模型要求X严格为正数')
    lower=np.full(k,-np.inf); upper=np.full(k,np.inf)
    scale=max(float(np.ptp(x)),1e-8); amplitude=max(float(np.max(np.abs(y))),1.)
    slope=float(np.polyfit(x,y,1)[0]); intercept=float(np.mean(y)-slope*np.mean(x))
    if model.id.startswith('polynomial') or model.id=='linear': initial=np.polyfit(x,y,k-1)
    elif model.id=='logarithmic': initial=np.polyfit(np.log(x),y,1)
    elif model.id=='power': initial=[amplitude,1.]
    elif model.id=='exponential': initial=[float(np.median(y)),slope/amplitude]
    elif model.id=='saturation':
        initial=[amplitude,float(np.median(x))]; lower[1]=max(1e-12,scale*1e-10)
    elif model.id in ('logistic','gompertz'): initial=[amplitude,2/scale,float(np.median(x))]
    elif model.id=='piecewise':
        initial=[intercept,slope,0.,float(np.median(x))]; lower[3]=np.min(x); upper[3]=np.max(x)
    else:
        initial=o['custom_initial']; lower=np.asarray([-np.inf if v is None else v for v in o['custom_lower']]); upper=np.asarray([np.inf if v is None else v for v in o['custom_upper']])
    initial=np.asarray(initial,float)
    starts=[initial]
    if model.id in ('power','exponential','saturation','logistic','gompertz','piecewise','custom'):
        rng=np.random.default_rng(o['seed'])
        for factor in (-1.,.3,3.):
            p=initial.copy()
            if model.id in ('logistic','gompertz'): p[1]*=factor; p[2]=np.quantile(x,.25 if factor<1 else .75)
            elif model.id=='piecewise': p[2]=slope*factor; p[3]=np.quantile(x,.25 if factor<1 else .75)
            elif model.id=='power': p[1]=factor
            else: p=p+rng.normal(size=k)*np.maximum(np.abs(p),.1)*.3
            starts.append(np.maximum(np.minimum(p,upper-1e-10),lower+1e-10))
    def residual(p):
        try: r=_predict(model,x,p)-y
        except (ValueError,OverflowError,FloatingPointError): return np.full(len(x),1e100)
        return r if sigma is None else r/sigma
    fits=[]
    exact_jac=None
    if model.id=='linear' or model.id.startswith('polynomial'):
        design=np.vander(x,k)
        exact_jac=lambda p: design.copy() if sigma is None else design/sigma[:,None]
    elif model.id=='logarithmic':
        design=np.column_stack([np.log(x),np.ones(len(x))])
        exact_jac=lambda p: design.copy() if sigma is None else design/sigma[:,None]
    for start in starts:
        try:
            result=least_squares(residual,start,bounds=(lower,upper),loss=o['loss'],max_nfev=1500,x_scale='jac',jac=exact_jac if exact_jac is not None else '2-point')
            if result.success and np.isfinite(result.cost) and result.cost<1e190:
                _predict(model,x,result.x); fits.append(result)
        except (ValueError,RuntimeError,OverflowError,FloatingPointError): continue
    if not fits: raise ValueError('所有初值均未收敛或模型不满足定义域')
    best=min(fits,key=lambda r:r.cost)
    best['parameter_lower']=lower; best['parameter_upper']=upper
    return best,len(starts)


def _folds(x,o,validation_groups):
    n=len(x); mode=o['validation']; rng=np.random.default_rng(o['seed'])
    if mode=='loo':
        if n>100: raise ValueError('留一验证最多100行；请选择最多5折验证')
        tests=[np.array([i]) for i in range(n)]
    elif mode=='time':
        levels=np.unique(x)
        if len(levels)<3: raise ValueError('时间验证至少需要3个不同X')
        blocks=np.array_split(levels,min(o['folds']+1,len(levels)))
        return [(np.flatnonzero(x<block[0]),np.flatnonzero(np.isin(x,block))) for block in blocks[1:] if len(block)]
    elif mode=='group':
        labels=list(dict.fromkeys(validation_groups))
        if len(labels)<2: raise ValueError('分组验证至少需要两个独立试件')
        shuffled=rng.permutation(len(labels)); chunks=np.array_split(shuffled,min(o['folds'],len(labels)))
        tests=[np.flatnonzero(np.isin(validation_groups,[labels[i] for i in chunk])) for chunk in chunks]
    else: tests=list(np.array_split(rng.permutation(n),min(o['folds'],n)))
    return [(np.setdiff1d(np.arange(n),test),test) for test in tests]


def _finite(value):
    if isinstance(value,np.ndarray): return _finite(value.tolist())
    if isinstance(value,dict): return {k:_finite(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)): return [_finite(v) for v in value]
    if isinstance(value,(float,np.floating)): return float(value) if np.isfinite(value) else None
    if isinstance(value,np.integer): return int(value)
    return value


def _scaled_jacobian(jac):
    norms=np.maximum(np.linalg.norm(jac,axis=0),np.finfo(float).tiny)
    scaled=jac/norms
    singular=np.linalg.svd(scaled,compute_uv=False)
    rank=int(np.sum(singular>singular[0]*1e-7)) if len(singular) and singular[0]>0 else 0
    return norms,scaled,rank


def _prediction_jacobian(model,grid,fit,base):
    """边界内有限差分，最多8次缩步；不创建观测数×预测数矩阵。"""
    p=fit.x; jac=np.empty((len(grid),len(p)))
    for j in range(len(p)):
        left=p[j]-fit.parameter_lower[j]; right=fit.parameter_upper[j]-p[j]
        h=np.cbrt(np.finfo(float).eps)*max(1,abs(p[j]))
        if left>0 and right>0: h=min(h,left/2,right/2)
        found=False
        for attempt in range(8):
            step=h*0.1**attempt
            if step<=0 or (p[j]+step==p[j] and p[j]-step==p[j]): break
            plus=minus=None
            if step<=right and p[j]+step!=p[j]:
                pp=p.copy(); pp[j]+=step
                try: plus=_predict(model,grid,pp)
                except ValueError: pass
            if step<=left and p[j]-step!=p[j]:
                pm=p.copy(); pm[j]-=step
                try: minus=_predict(model,grid,pm)
                except ValueError: pass
            if plus is not None and minus is not None: derivative=(plus-minus)/(2*step)
            elif plus is not None: derivative=(plus-base)/step
            elif minus is not None: derivative=(base-minus)/step
            else: continue
            if np.all(np.isfinite(derivative)):
                jac[:,j]=derivative; found=True; break
        if not found: raise ValueError('参数边界或函数定义域内无法计算有限差分')
    return jac


def _candidate(model,x,y,sigma,validation_groups,o):
    c=dict(id=model.id,label=model.label,formula=model.formula,status='failed',error=None,parameters={},metrics={m:None for m in METRICS},metric_reasons={},warnings=[],cv_predictions=[None]*len(x),validation_folds=[],curve=None,residuals=[],y_fitted=[])
    try:
        xmin=o.get('prediction_min'); xmax=o.get('prediction_max')
        grid=np.linspace(float(np.min(x)) if xmin is None else xmin,float(np.max(x)) if xmax is None else xmax,o['prediction_points'])
        if grid[0]>=grid[-1]: raise ValueError('预测范围上下界错误')
        if model.positive_x and np.any(grid<=0): raise ValueError('预测范围要求X严格为正数')
        fit,starts=_fit(model,x,y,sigma,o)
        pred=_predict(model,x,fit.x); residual=y-pred; n=len(y); k=len(fit.x)
        # Compare sums of squares in actual Y units normalized to max|Y|.
        # Logs reconstruct the Gaussian likelihood without squaring huge/tiny Y.
        y_scale=float(np.max(np.abs(y)))
        statistic_scale=y_scale if y_scale>0 else 1.
        scaled_y=y/statistic_scale; scaled_residual=residual/statistic_scale
        rss_scaled=float(scaled_residual@scaled_residual)
        sst_scaled=float(np.sum((scaled_y-np.mean(scaled_y))**2))
        c.update(status='ok',parameters=dict(zip(model.parameters,fit.x)),y_fitted=pred,residuals=residual,multistart_count=starts)
        column_norms,scaled_jac,rank=_scaled_jacobian(fit.jac)
        c['jacobian_rank']=int(rank)
        if rank<k: c['warnings'].append('雅可比矩阵秩不足，参数不可唯一识别')
        if fit.optimality>1e-3: c['warnings'].append('优化一阶条件较弱，需检查收敛与参数尺度')
        m=c['metrics']; reasons=c['metric_reasons']
        numerical_zero=n*(10*np.finfo(float).eps)**2
        m.update(rmse=math.sqrt(rss_scaled/n)*statistic_scale,mae=float(np.mean(np.abs(scaled_residual)))*statistic_scale)
        if sst_scaled>numerical_zero:
            m['r2']=1-rss_scaled/sst_scaled; m['adjusted_r2']=1-(1-m['r2'])*(n-1)/(n-k)
        else:
            reasons['r2']=reasons['adjusted_r2']='Y为常量或数值上近似常量'
        if o['loss']=='linear' and sigma is None:
            # Gaussian likelihood estimates the residual variance: K includes that parameter.
            K=k+1
            if rss_scaled>numerical_zero:
                likelihood=n*(math.log(2*math.pi)+1+math.log(rss_scaled/n)+2*math.log(statistic_scale))
                m['bic']=likelihood+K*math.log(n)
                if n>K+1: m['aicc']=likelihood+2*K+2*K*(K+1)/(n-K-1)
                else: reasons['aicc']='样本量不足：AICc要求 n > 参数数(含方差)+1'
            else:
                reasons['aicc']=reasons['bic']='残差接近零，未知方差高斯似然退化；不可可靠比较信息准则'
        else: reasons['aicc']=reasons['bic']='仅普通无权重、linear损失的同方差最小二乘可比较'
        cv=np.full(n,np.nan); cv_errors=[]
        for train,test in _folds(x,o,validation_groups):
            c['validation_folds'].append(dict(train_indices=train.tolist(),test_indices=test.tolist()))
            try:
                trained,_=_fit(model,x[train],y[train],None if sigma is None else sigma[train],o)
                if _scaled_jacobian(trained.jac)[2]<k: raise ValueError('训练折雅可比秩不足，参数不可识别')
                cv[test]=_predict(model,x[test],trained.x)
            except Exception as exc: cv_errors.append(str(exc))
        c['cv_predictions']=cv
        if cv_errors:
            reasons['cv_rmse']=reasons['cv_mae']='部分验证折失败：'+cv_errors[0]; c['cv_valid']=False
        elif np.any(np.isfinite(cv)):
            delta=y[np.isfinite(cv)]-cv[np.isfinite(cv)]
            scaled_delta=delta/statistic_scale
            m['cv_rmse']=float(np.sqrt(np.mean(scaled_delta**2)))*statistic_scale; m['cv_mae']=float(np.mean(np.abs(scaled_delta)))*statistic_scale; c['cv_valid']=True
        else: c['cv_valid']=False; reasons['cv_rmse']=reasons['cv_mae']='没有可计算的验证预测'
        curve=dict(x=grid,y=_predict(model,grid,fit.x),confidence_lower=None,confidence_upper=None,prediction_lower=None,prediction_upper=None)
        interval_reason='仅限无权重linear损失、独立同分布误差、满秩且残差自由度为正的delta近似95%区间'
        if o['loss']=='linear' and sigma is None and o['validation'] in ('kfold','loo') and rank==k and n>k:
            try:
                jac=_prediction_jacobian(model,grid,fit,curve['y'])
                variance=(rss_scaled/(n-k)*statistic_scale)*statistic_scale
                if not np.isfinite(variance) or (variance==0 and rss_scaled>numerical_zero): raise ValueError('残差方差超出浮点数表示范围')
                cov=np.linalg.pinv(scaled_jac.T@scaled_jac)*variance/np.outer(column_norms,column_norms)
                v=np.maximum(0,np.einsum('ij,jk,ik->i',jac,cov,jac)); q=t.ppf(.975,n-k)
                band=q*np.sqrt(v); prediction=q*np.sqrt(v+variance)
                bands=dict(confidence_lower=curve['y']-band,confidence_upper=curve['y']+band,prediction_lower=curve['y']-prediction,prediction_upper=curve['y']+prediction)
                if not all(np.all(np.isfinite(a)) for a in bands.values()): raise ValueError('区间数值溢出')
                curve.update(bands)
                c['interval_method']='delta_95_iid'; c['interval_assumptions']='误差独立同分布、近似正态、局部线性化；未验证这些假设'
            except Exception as exc:
                interval_reason='未计算区间：'+str(exc)
        else: interval_reason='未计算区间：加权/稳健/时间/分组验证或秩/自由度条件不满足iid近似'
        c['interval_reason']=interval_reason; c['curve']=curve
        for metric,value in m.items():
            if value is not None and not np.isfinite(value):
                m[metric]=None; reasons[metric]='指标数值溢出，无法可靠计算'
    except Exception as exc:
        c['status']='failed'; c['error']=str(exc)
    return _finite(c)


def fit_dataset(dataset,options=None,progress=None):
    o=normalise_fit_options(options)
    x=np.asarray(dataset.get('x',[]),float); y=np.asarray(dataset.get('y',[]),float)
    if x.ndim!=1 or y.shape!=x.shape or not 3<=len(x)<=5000 or not np.all(np.isfinite(x)) or not np.all(np.isfinite(y)): raise ValueError('X/Y须为3–5000个有限数且长度一致')
    raw_sigma=dataset.get('sigma'); sigma=None if raw_sigma is None else np.asarray(raw_sigma,float)
    if sigma is not None and (sigma.shape!=x.shape or not np.all(np.isfinite(sigma)) or np.any(sigma<=0)): raise ValueError('sigma须为与数据等长的正有限数')
    labels=dataset.get('groups'); labels=['全部']*len(x) if labels is None else labels
    if len(labels)!=len(x): raise ValueError('分类标签长度不匹配')
    labels=[str(label) for label in labels]; unique=list(dict.fromkeys(labels))
    if len(unique)>10: raise ValueError('分类最多10组')
    validation_groups=dataset.get('validation_groups')
    if o['validation']=='group' and (validation_groups is None or len(validation_groups)!=len(x) or any(v is None for v in validation_groups)): raise ValueError('分组验证必须选择独立试件列validation_groups，分类列不能替代试件列')
    row_ids=dataset.get('row_ids',list(range(1,len(x)+1)))
    if len(row_ids)!=len(x): raise ValueError('原始行号长度不匹配')
    models={m.id:m for m in MODELS}
    if 'custom' in o['models']:
        models['custom']=Model('custom','自定义公式',o['custom_formula'],o['custom_parameters'],expression(o['custom_formula'],o['custom_parameters']))
    result=dict(groups=[],metric=o['metric'],options=_finite(o),warnings=['最佳仅限所选候选模型和验证规则；区间依赖未验证的统计假设'])
    total=len(unique)*len(o['models']); completed=0
    for label in unique:
        indices=np.flatnonzero(np.asarray(labels)==label); gx=x[indices]; gy=y[indices]
        group=dict(label=label,x=gx,y=gy,row_ids=[row_ids[i] for i in indices],recommended_id=None,reason='',candidates=[])
        for model_id in o['models']:
            c=_candidate(models[model_id],gx,gy,None if sigma is None else sigma[indices],None if validation_groups is None else np.asarray(validation_groups)[indices],o)
            group['candidates'].append(c); completed+=1
            if progress: progress(dict(phase='fitting',progress=completed/total,message=f'完成 {label} / {c["label"]}'))
        eligible=[c for c in group['candidates'] if c['status']=='ok' and c.get('cv_valid') and c['metrics'][o['metric']] is not None and c.get('jacobian_rank')==len(c['parameters'])]
        if eligible:
            sign=-1 if o['metric'] in ('r2','adjusted_r2') else 1
            eligible.sort(key=lambda c:(sign*c['metrics'][o['metric']],len(c['parameters'])))
            best=eligible[0]
            # Y-unit invariant roundoff plus relative score ties favor parsimony.
            if o['metric'] in ('cv_rmse','cv_mae','rmse','mae'):
                resolution=np.finfo(float).eps*float(np.max(np.abs(gy)))
                near=[c for c in eligible if c['metrics'][o['metric']]<=best['metrics'][o['metric']]*(1+1e-8)+resolution]
                best=min(near,key=lambda c:len(c['parameters']))
            group['recommended_id']=best['id']; group['reason']=f'按{o["metric"]}比较，仅推荐验证全部成功且参数满秩的候选'
        else: group['reason']='缺少有效且可比较的指标或验证失败，不强制推荐'
        result['groups'].append(group)
    return _finite(result)

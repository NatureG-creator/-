"""原MATLAB程序导出合同；不再用代码6重写算法重提取实测值。"""
import hashlib
import json
from pathlib import Path
import numpy as np
from scipy.io import loadmat
from unified_config import ANALYSIS_CONFIG


def verify_sources(mat):
    paths=np.asarray(mat['original_source_paths'],dtype=object).reshape(-1)
    hashes=np.asarray(mat['original_source_sha256'],dtype=object).reshape(-1)
    if not len(paths) or len(paths)!=len(hashes):
        raise ValueError('原MATLAB来源校验表无效。')
    for path,digest in zip(paths,hashes):
        source=Path(str(path))
        if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest()!=str(digest):
            raise ValueError(f'原MATLAB来源已变化，请重新提取目标：{source}')


def validate_original_target(mat):
    if str(mat.get('extraction_method',''))!='original_matlab_positive_depth_v2':
        raise ValueError('仅接受正向共同参考面v2目标；请重新运行原untitled.m，不可混用旧口径。')
    if not bool(mat.get('calibration_ready',False)):
        raise ValueError('原目标仅为诊断，尚不能校准：'+str(mat.get('calibration_issues','')))
    uniform=float(mat['uniform_depth_um'])
    if not np.isfinite(uniform) or uniform<0:
        raise ValueError('原均匀深度为负或无效；不自动取绝对值。')
    if 'original_uniform_mm' in mat and not np.isclose(uniform,float(mat['original_uniform_mm'])*1000):
        raise ValueError('导出均匀深度与原计算值不一致，不允许暗中改符号。')
    if mat['source_provenance'].get('source_type')!='measured_pointcloud':
        raise ValueError('模拟文件不得冒充实测来源。')
    cfg=mat['original_config'];prep=cfg['preprocessing'];pit=cfg['pit_detection'];ws=cfg['watershed']
    if not np.isclose(float(mat['spacing_um']),prep['grid_resolution_mm']*1000):
        raise ValueError('原网格与导出间距不同。')
    expected=dict(gaussian_sigma=prep['main_gaussian_sigma'],min_prominence_um=pit['min_prominence']*1000,
        min_distance=pit['min_distance'],neighborhood=ANALYSIS_CONFIG['neighborhood'],
        watershed_threshold=ws['threshold'],watershed_sigma=ws['gaussian_sigma'],edge_margin=pit['edge_margin'])
    if not np.all(np.asarray(pit['neighborhood'])==ANALYSIS_CONFIG['neighborhood']) or any(
            not np.isclose(expected[k],v) for k,v in ANALYSIS_CONFIG.items()):
        raise ValueError('原MATLAB识别设置与Python不同，先统一设置并重新导出。')
    depth=np.asarray(mat['depth_um'],float);smooth=np.asarray(mat['processed_depth_um'],float)
    mask=np.asarray(mat['valid_mask'],bool)
    if depth.ndim!=2 or depth.shape!=smooth.shape or mask.shape!=depth.shape or not mask.all() or not np.isfinite(depth).all() or not np.isfinite(smooth).all():
        raise ValueError('原算法要求完整补齐矩阵；不得擅自改成有效掩膜统计。')
    if np.any(depth<0) or np.any(smooth<0):
        raise ValueError('共同参考深度含负值；核对参考区，不以平滑、绝对值或额外平移掩盖。')
    ld=np.asarray(mat['log_depth'],float).reshape(-1);lr=np.asarray(mat['log_ratio'],float).reshape(-1)
    if len(ld)<2 or len(ld)!=len(lr) or not np.isfinite(ld).all() or not np.isfinite(lr).all():
        raise ValueError('原对数样本需要至少两个一一对应有效坑。')
    vector=np.asarray(mat['target_data'],float).reshape(-1)
    check=np.array([smooth.mean(),(smooth-uniform).mean(),lr.mean(),ld.mean(),lr.std(ddof=1),ld.std(ddof=1)])
    if vector.shape!=(6,) or not np.isfinite(vector).all() or not np.allclose(vector,check,rtol=1e-9,atol=1e-8) or not np.isclose(smooth.min(),uniform):
        raise ValueError('原六值与保存矩阵、均匀深度或坑样本不对应。')
    verify_sources(mat)


def load_original_target(source):
    from native_metric_client import native_result
    source=Path(source)
    if not source.is_file():raise FileNotFoundError(f'原程序目标不存在：{source}')
    mat=loadmat(source,simplify_cells=True)
    validate_original_target(mat)
    result=native_result(mat)
    cfg=mat['original_config'];ref=cfg['reference']
    result.update(extraction_method='original_matlab_positive_depth_v2',extraction_backend='MATLAB_native',
        original_config=cfg,original_source_paths=mat['original_source_paths'],original_source_sha256=mat['original_source_sha256'],
        source_path=str(source),raw_depth_um=np.asarray(mat['depth_um'],float),
        reference_metadata=mat['reference_metadata'],
        reference_metadata_json=json.dumps(mat['reference_metadata'],default=lambda x:x.tolist() if isinstance(x,np.ndarray) else x.item(),ensure_ascii=False),
        reference_rule=('original_matlab_positive_depth_v2',float(ref['flat_height_ratio']),int(ref['flat_column_count']),int(ref['corrosion_column_count'])),
        reference_validation_basis='one 190 mm frame, inward depth relative to flat baseline; no abs; reference not independently verified',
        fingerprint=hashlib.sha256(source.read_bytes()+repr(sorted(ANALYSIS_CONFIG.items())).encode()).hexdigest())
    return result

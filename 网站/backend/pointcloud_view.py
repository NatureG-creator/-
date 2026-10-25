"""Read-only previews of saved scans; no calibration or processing is run here."""
from pathlib import Path
import json
import hashlib

import numpy as np
from scipy.io import loadmat

from .pointcloud_preview import grid_preview
from .pointcloud_runner import inspect_xyz, POINT_EXTENSIONS


def _common_preview(folder, spec):
    from .reference_chain import digest, validate_reference

    full_path=folder/'outputs/pointcloud/reference_surface_190mm.mat'
    full_hash=digest(full_path)
    input_hashes={name:digest(folder/'inputs'/(name+'.txt')) for name in ('reference','detail')}
    if input_hashes!=spec.get('input_hashes'):
        raise ValueError('完整或局部原始扫描已变化，不能复用共同坐标链')
    selected=None
    for path in (folder/'outputs/pointcloud/reference_chain').glob('*/reference_calibration.json'):
        report=json.loads(path.read_text(encoding='utf-8'))
        key=hashlib.sha256(json.dumps(dict(inputs=input_hashes,config=spec['pointcloud_config'],
            stored_sha256=full_hash,thickness=report['original_thickness_mm'],algorithm=1),sort_keys=True).encode()).hexdigest()[:24]
        if path.parent.name==key and report.get('source_job_id')==folder.name and report.get('source_hashes')==input_hashes and report.get('complete_surface_sha256')==full_hash:
            selected=(path,report);break
    if selected is None:
        raise ValueError('没有与当前来源匹配的已验证共同坐标缓存；本预览不会自动重算配准或校准')
    path,report=selected
    local_data=loadmat(path.parent/'empirical_surface.mat')
    embedded=json.loads(str(local_data['reference_calibration_json'].reshape(-1)[0]))
    if embedded!=report:
        raise ValueError('共同坐标缓存的矩阵与来源报告不一致')
    depth=np.asarray(local_data['Z_filled'],dtype=np.float64)
    validate_reference(depth,report,report)
    if report['reference_columns_zero_based']!=[0,200] or report['reference_ratio']!=.2:
        raise ValueError('此对照视图要求已验证的前200列、20%经验参考链')
    data=loadmat(full_path);height=np.asarray(data['height_matrix_mm'],dtype=float)
    x=np.asarray(data['x_coordinates_mm'],dtype=float).reshape(-1)
    y=np.asarray(data['y_coordinates_mm'],dtype=float).reshape(-1)
    if height.shape!=(len(y),len(x)) or len(x)<200 or not np.isfinite(height).all():
        raise ValueError('完整参考矩阵与坐标不匹配')
    for coordinates,key in ((x,'dx_mm'),(y,'dy_mm')):
        if not np.allclose(coordinates-coordinates[0],np.arange(len(coordinates))*report[key],rtol=0,atol=1e-8):
            raise ValueError('完整参考表面的网格与已验证共同坐标相位不一致')
    roi=height[:,:200]
    flat=float(roi.min()+.2*(roi.max()-roi.min()))
    if flat!=report['reference_height_mm']:
        raise ValueError('前200列20%参考高度与已验证报告不一致')
    lx=x[0]+report['origin_x_mm']+np.arange(depth.shape[1])*report['dx_mm']
    ly=y[0]+report['origin_y_mm']+np.arange(depth.shape[0])*report['dy_mm']
    xi=np.rint((lx-x[0])/report['dx_mm']).astype(int)
    yi=np.rint((ly-y[0])/report['dy_mm']).astype(int)
    if xi.min()<0 or xi.max()>=len(x) or yi.min()<0 or yi.max()>=len(y) or not np.allclose(x[xi],lx,rtol=0,atol=1e-8) or not np.allclose(y[yi],ly,rtol=0,atol=1e-8):
        raise ValueError('局部共同坐标超出完整扫描网格或相位不一致')
    local_height=depth+flat
    local_points,_=grid_preview(lx,ly,local_height,max_points=local_height.size)
    base,_=grid_preview(x,y,height,max_points=4000)
    rmin,cmin=np.unravel_index(roi.argmin(),roi.shape);rmax,cmax=np.unravel_index(roi.argmax(),roi.shape)
    rows=np.unique(np.r_[np.searchsorted(y,base[:,1]),rmin,rmax,yi[0],yi[-1]])
    cols=np.unique(np.r_[np.searchsorted(x,base[:,0]),199,min(200,len(x)-1),cmin,cmax,xi[0],xi[-1]])
    X,Y=np.meshgrid(x[cols],y[rows]);points=np.column_stack((X.ravel(),Y.ravel(),height[np.ix_(rows,cols)].ravel()))
    bounds=lambda u,v,h:[[float(u.min()),float(u.max())],[float(v.min()),float(v.max())],[float(min(h.min(),flat)),float(max(h.max(),flat))]]
    return dict(source_job_id=folder.name,view='common_reference',points=points.tolist(),grid=True,
        point_count=height.size,bounds_mm=bounds(x,y,height),inward_positive=True,
        physical_pristine_reference_verified=False,
        common_reference=dict(reference_height_mm=flat,reference_min_height_mm=float(roi.min()),reference_max_height_mm=float(roi.max()),
            section_grid=dict(x=x.tolist(),y=y.tolist(),grid=height.tolist()),
            reference_ratio=.2,reference_columns_one_based=[1,200],reference_column_count=200,
            reference_x_range_mm=[float(x[0]),float(x[199])],reference_y_range_mm=[float(y[0]),float(y[-1])],
            local_x_range_mm=[float(lx[0]),float(lx[-1])],local_y_range_mm=[float(ly[0]),float(ly[-1])],
            numerical_chain_verified=True,physical_pristine_reference_verified=False,
            full_reproduction_max_error_mm=report['full_reproduction_max_error_mm'],
            mean_depth_mm=report['mean_depth_mm'],min_depth_mm=report['min_depth_mm'],max_depth_mm=report['max_depth_mm'],
            cache_key=path.parent.name,source_hashes=input_hashes,depth_sha256=report['depth_sha256'],
            complete_surface_sha256=full_hash,original_thickness_mm=report['original_thickness_mm'],
            overlap_height_max_difference_mm=float(np.max(np.abs(height[np.ix_(yi,xi)]-local_height))),
            local_surface=dict(points=local_points.tolist(),grid=True,point_count=depth.size,
                bounds_mm=bounds(lx,ly,local_height),inward_positive=True,
                note='已验证共同坐标局部形貌；H=缓存经验深度+H_flat，不重新找平或平滑。')),
        note='复用已验证共同坐标链：前200列为有轻微腐蚀的经验参考区，H_flat=min(H)+0.2×[max(H)−min(H)]。共同高程H向内为正，图中向下；经验深度d=H−H_flat。未知参考区损失未补偿，不代表已验证的真实零腐蚀面。')


def saved_preview(service, payload):
    job_id=str(payload.get('source_job_id',''))
    service.validate_id(job_id)
    folder=Path(service.runtime)/'jobs'/job_id
    status=json.loads((folder/'status.json').read_text(encoding='utf-8'))
    spec=json.loads((folder/'spec.json').read_text(encoding='utf-8'))
    if spec.get('kind')!='pointcloud' or status.get('state')!='completed':
        raise ValueError('只能查看已完成点云任务；不会读取运行中任务或启动处理')
    view=payload.get('view','detail_processed')
    if view=='common_reference':
        return _common_preview(folder,spec)
    if view in {'reference_raw','detail_raw'}:
        kind=view.split('_')[0]
        extension=spec.get(kind+'_extension','.txt')
        if extension not in POINT_EXTENSIONS:
            raise ValueError('点云来源扩展名不受支持')
        source=folder/'inputs'/(kind+extension)
        if not source.is_file():
            raise ValueError('该任务没有保存此原始扫描文件')
        info=inspect_xyz(source)
        return dict(source_job_id=job_id,view=view,points=info['sample_points'],
            point_count=info['points'],bounds_mm=list(zip(info['minimum'],info['maximum'])),
            grid=False,physical_pristine_reference_verified=False,
            note='原始扫描坐标；仅抽样散点，不找平、不插值、不连面。颜色为原始Z高程，不是腐蚀深度。')
    names={'detail_processed':'measured_surface_smoothed.mat',
           'reference_processed':'reference_surface_190mm.mat'}
    if view not in names:
        raise ValueError('不支持的点云预览类型')
    source=folder/'outputs'/'pointcloud'/names[view]
    if not source.is_file():
        raise ValueError('该任务没有保存此处理后表面')
    data=loadmat(source)
    height=np.asarray(data['height_matrix_mm'],dtype=float)
    x=np.asarray(data['x_coordinates_mm'],dtype=float).reshape(-1)
    y=np.asarray(data['y_coordinates_mm'],dtype=float).reshape(-1)
    if height.shape!=(len(y),len(x)) or min(height.shape)<2 or not all(
            np.isfinite(v).all() for v in (height,x,y)):
        raise ValueError('表面坐标和高程矩阵不匹配或包含无效值')
    # Preview only: keep existing grid nodes, including edges, with no resampling.
    points,_=grid_preview(x,y,height,max_points=4000)
    return dict(source_job_id=job_id,view=view,points=points.tolist(),grid=True,
        point_count=height.size,matrix_shape=list(height.shape),
        bounds_mm=[[float(x.min()),float(x.max())],[float(y.min()),float(y.max())],
                   [float(height.min()),float(height.max())]],
        physical_pristine_reference_verified=False,
        note=('完整参考扫描独立找平；与局部扫描不自动配准或拼接。' if view=='reference_processed' else
              '局部处理后表面，保留原MAT高程；不重新平滑、归零或校准。')+
             '颜色和剖面均为高程，不代表已验证的绝对腐蚀深度或剩余厚度。')

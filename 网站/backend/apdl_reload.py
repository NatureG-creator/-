"""Restore an editable APDL draft from task-owned, hash-checked source copies."""
import copy
from pathlib import Path

from .job_history import history_guard
from .system_info import sha256


def reload_apdl_config(service, job_id):
    with history_guard(service):
        job=service.get_job(job_id)
        if job.get('kind')!='apdl_tension':
            raise ValueError('仅 APDL 任务支持载入有限元配置')
        spec=job['spec']
        root=(service.runtime/'jobs'/job_id).resolve()
        hashes={}
        def source(relative, digest):
            path=root/relative
            if (path.is_symlink() or not path.resolve().is_relative_to(root/'inputs') or
                    not path.is_file() or not digest or sha256(path)!=digest):
                raise ValueError('任务冻结输入缺失、路径不合法或校验失败，请重新上传原文件')
            hashes[path]=digest
            return path
        draft=dict(preset_id=spec.get('preset_id',''),case_name=job.get('display_name') or spec.get('case_name',''),
                   options=copy.deepcopy(spec['options']),registration_confirmed=False)
        plans={}
        for face,record in spec.get('faces',{}).items():
            metadata=record['metadata']
            if record['source_kind']=='coordinates':
                paths={axis:source(relative,record['coordinate_sha256'][axis])
                       for axis,relative in record['coordinate_input_paths'].items()}
                plans[face]=dict(origin='coordinates',source_kind='coordinates',mapping={},
                                 coordinate_direction=record['coordinate_direction'],paths=paths)
            else:
                path=source(record['input_path'],metadata['sha256'])
                mapping=copy.deepcopy(record['mapping'])
                inherited=record.get('inherited_geometry',{})
                if record['source_kind']=='measured':
                    for key in ('dx_mm','dy_mm','origin_x_mm','origin_y_mm'):
                        if mapping.get(key) in (None,''):
                            axis=({'dx_mm':'dy_mm','dy_mm':'dx_mm'}.get(key,key)
                                  if metadata.get('transpose') else key)
                            mapping[key]=inherited.get(key,metadata.get(axis,0))
                    if mapping.get('layout','auto')=='auto':mapping['layout']=metadata['input_layout']
                    plans[face]=dict(origin='upload',source_kind='measured',mapping=mapping,path=path)
                else:
                    plans[face]=dict(origin='upload_npz',source_kind='simulation',mapping=mapping,path=path,
                                     geometry={key:inherited[key] for key in ('space_xy_um','space_z_um')})
        # All frozen inputs are validated before creating any upload copies.
        def upload(path):
            with path.open('rb') as stream:
                result=service.upload(path.name,stream,path.stat().st_size)
            if result['sha256']!=hashes[path]:
                raise ValueError('复制期间冻结输入发生变化，请重新载入')
            return result
        for face,plan in plans.items():
            if plan['origin']=='coordinates':
                paths=plan.pop('paths')
                records={axis:upload(path) for axis,path in paths.items()}
                plan['coordinate_uploads']={axis:r['id'] for axis,r in records.items()}
                plan['coordinate_names']={axis:r['name'] for axis,r in records.items()}
            else:
                record=upload(plan.pop('path'))
                plan.update(upload_id=record['id'],upload_name=record['name'])
                if plan['origin']=='upload_npz':
                    from .apdl_npz import inspect_uploaded_npz
                    info=inspect_uploaded_npz(service,record['id'])
                    geometry=plan.pop('geometry')
                    plan.update(npz_info=info,npz_variable=plan['mapping'].get('npz_variable') or info['default_variable'])
                    variable=next(v for v in info['variables'] if v['name']==plan['npz_variable'])
                    plan['npz_stage']=plan['mapping'].get('npz_stage') or variable['stage_count']
                    plan.update(geometry)
            draft[face]=plan
        return draft

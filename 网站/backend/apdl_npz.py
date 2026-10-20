"""外部 CA 状态 NPZ 的安全检查；不改变元胞到表面的提取算法。"""
from __future__ import annotations

import math
import time
import zipfile
from pathlib import Path

import numpy as np
from numpy.lib import format as npformat

STATE_KEYS = ('perfect_a', 'a_sd')
GEOMETRY_KEYS = ('space_xy_um', 'space_z_um')
MAX_STATE_BYTES = 1024 ** 3


def _positive(value, key):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float, np.number)):
        raise ValueError(key + '元胞尺寸必须是正的有限数值（μm）')
    if not np.isrealobj(value) or not math.isfinite(float(value)) or float(value) <= 0:
        raise ValueError(key + '元胞尺寸必须是正的有限数值（μm）')
    return float(value)


def _headers(path):
    """只读取候选数组头；不解压对象数组，不载入全部历史阶段。"""
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            if len(names) > 4096 or len(names) != len(set(names)):
                raise ValueError('NPZ 成员过多或重复')
            result = {}
            for key in (*STATE_KEYS, *GEOMETRY_KEYS):
                name = key + '.npy'
                if name not in names:
                    continue
                with archive.open(name) as stream:
                    version = npformat.read_magic(stream)
                    if version == (1, 0):
                        shape, order, dtype = npformat.read_array_header_1_0(stream)
                    elif version == (2, 0):
                        shape, order, dtype = npformat.read_array_header_2_0(stream)
                    else:
                        raise ValueError('NPZ 内部 NPY 版本不支持，请另存为标准数值 NPZ')
                result[key] = (shape, dtype, archive.getinfo(name).file_size)
            return result
    except (OSError, EOFError, zipfile.BadZipFile, RuntimeError) as exc:
        raise ValueError('无法读取 NPZ 文件或数组头：' + str(exc)) from exc


def inspect_npz(path):
    started = time.perf_counter()
    if Path(path).suffix.lower() != '.npz':
        raise ValueError('模拟状态上传需为 .npz 文件')
    headers = _headers(path)
    variables, warnings = [], []
    for key in STATE_KEYS:
        if key not in headers:
            continue
        shape, dtype, stored_bytes = headers[key]
        reason = None
        if dtype.hasobject:
            reason = '对象型历史数组（pickle）不直接加载；请使用数值 perfect_a，或在可信离线环境导出所需阶段为数值三维 perfect_a。'
        elif not np.issubdtype(dtype, np.number) or np.issubdtype(dtype, np.complexfloating):
            reason = '状态必须为实数数值数组。'
        elif len(shape) not in ((3,) if key == 'perfect_a' else (3, 4)) or min(shape, default=0) < 1:
            reason = 'perfect_a 必须三维；a_sd 必须三维或 [阶段,X,Y,Z] 四维，且各轴非空。'
        elif math.prod(shape) * dtype.itemsize > MAX_STATE_BYTES or stored_bytes > MAX_STATE_BYTES + 65536:
            reason = '解压后状态数组超过 1GB，请单独导出所需阶段。'
        variables.append(dict(name=key, shape=list(shape), dtype=str(dtype), supported=reason is None,
                              stage_count=shape[0] if len(shape) == 4 else 1,
                              state_shape=list(shape[-3:]), reason=reason))
        if reason:
            warnings.append(key + '：' + reason)
    usable = [v for v in variables if v['supported']]
    if not usable:
        raise ValueError('未找到可读取的三维 CA 状态 perfect_a / a_sd。' + '；'.join(warnings))
    geometry = {}
    with np.load(path, allow_pickle=False) as data:
        for key in GEOMETRY_KEYS:
            if key not in headers:
                continue
            shape, dtype, size = headers[key]
            if math.prod(shape) != 1 or size > 65536 or dtype.hasobject:
                raise ValueError(key + '元胞尺寸必须是单个数值（μm）')
            geometry[key] = _positive(data[key].reshape(-1)[0], key)
    return dict(variables=variables, default_variable=usable[0]['name'], geometry=geometry,
                missing_geometry=[k for k in GEOMETRY_KEYS if k not in geometry], warnings=warnings,
                reading_seconds=time.perf_counter() - started,
                rule='状态=1为金属，沿Z读取第一层金属；无金属沿用最后层索引。原始轴顺序为[X,Y,Z]。')


def resolve_geometry(info, supplied=None):
    if supplied is not None and not isinstance(supplied, dict):
        raise ValueError('cell_geometry必须是元胞尺寸对象')
    geometry = dict(info['geometry'])
    for key in GEOMETRY_KEYS:
        if key in (supplied or {}):
            value = _positive(supplied[key], key)
            if key in geometry and not math.isclose(value, geometry[key], rel_tol=0, abs_tol=1e-12):
                raise ValueError(key + '与文件尺寸不一致，不能覆盖原模拟元胞尺寸')
            geometry[key] = value
        if key not in geometry:
            raise ValueError('NPZ 缺少元胞尺寸 ' + key + '，请按原模拟配置补填（μm）')
    return geometry


def read_npz_state(path, variable=None, stage=None):
    info = inspect_npz(path)
    variable = variable or info['default_variable']
    selected = next((v for v in info['variables'] if v['name'] == variable), None)
    if selected is None:
        raise ValueError('NPZ 中没有指定状态变量 perfect_a / a_sd')
    if not selected['supported']:
        raise ValueError(selected['reason'])
    count = selected['stage_count']
    if stage is None:
        stage = count
    if isinstance(stage, bool) or not isinstance(stage, int) or not 1 <= stage <= count:
        raise ValueError(f'NPZ 阶段必须是 1 至 {count} 的整数（按存储顺序编号）')
    with np.load(path, allow_pickle=False) as data:
        raw = data[variable]
        state = raw[stage - 1] if raw.ndim == 4 else raw
        if not np.isfinite(state).all():
            raise ValueError('所选 CA 状态包含 NaN / Inf，需为有限三维实数数组')
        state = np.array(state, copy=True)
    return state, dict(npz_variable=variable, npz_stage=stage, state_shape=list(state.shape))


def inspect_uploaded_npz(service, upload_id):
    from .system_info import sha256
    record, path = service.get_upload(upload_id)
    if sha256(path) != record['sha256']:
        raise ValueError('来源文件已变化，请重新上传')
    info = inspect_npz(path)
    if sha256(path) != record['sha256']:
        raise ValueError('读取期间来源文件变化，请重新上传')
    return dict(info, sha256=record['sha256'], name=record['name'])

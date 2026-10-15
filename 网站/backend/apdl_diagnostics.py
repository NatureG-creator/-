"""Read-only input diagnostics; no result here certifies a MAPDL solve.

Hexahedron corners follow SOLID185's I,J,K,L,M,N,O,P ordering.  The
scaled Jacobian is the determinant of the three normalized local edge
directions at each corner, with local axes oriented consistently.  This
corner-only measure is a geometric warning, not an ANSYS shape test.
"""
from __future__ import annotations

import math
import numbers

import numpy as np


DEFAULT_FIELD_OUTPUT_TIMES = (.25, .5, .75, 1.)
_CHUNK_SIZE = 20000
_SCALED_JACOBIAN_WARNING = .1
_EDGES = ((0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6),
          (6, 7), (7, 4), (0, 4), (1, 5), (2, 6), (3, 7))
# Each pair points along increasing local xi, eta or zeta at its corner.
_CORNER_AXES = (
    ((0, 1), (0, 1), (3, 2), (3, 2), (4, 5), (4, 5), (7, 6), (7, 6)),
    ((0, 3), (1, 2), (1, 2), (0, 3), (4, 7), (5, 6), (5, 6), (4, 7)),
    ((0, 4), (1, 5), (2, 6), (3, 7), (0, 4), (1, 5), (2, 6), (3, 7)),
)


def _options(value: dict) -> dict:
    if not isinstance(value, dict):
        raise ValueError('APDL options 必须是对象。')
    return value


def _real(value: object, name: str, *, positive: bool = False) -> float:
    if (isinstance(value, (bool, np.bool_)) or not isinstance(value, numbers.Real)
            or not math.isfinite(value) or (positive and value <= 0)):
        raise ValueError(f'{name} 必须是{"正的" if positive else ""}有限实数。')
    return float(value)


def normalise_output_options(options: dict) -> dict:
    """Copy output settings; only selected mode activates the time draft.

    Inactive drafts may be unordered, empty, or outside (0,1], but must
    remain JSON-safe lists of finite real numbers, never command text.
    """
    options = _options(options)
    mode = options.get('result_save_mode', 'all')
    if not isinstance(mode, str) or mode not in {'all', 'last', 'selected'}:
        raise ValueError('result_save_mode 只支持 all、last 或 selected。')
    times = options.get('field_output_times', list(DEFAULT_FIELD_OUTPUT_TIMES))
    if not isinstance(times, list):
        raise ValueError('field_output_times 必须是有限实数列表。')
    cleaned = [_real(value, 'field_output_times') for value in times]
    if mode == 'selected' and (
            not 1 <= len(cleaned) <= 20 or cleaned[-1] != 1.
            or any(not 0 < value <= 1 for value in cleaned)
            or any(b <= a for a, b in zip(cleaned, cleaned[1:]))):
        raise ValueError('selected 模式要求 1 至 20 个严格递增、不重复的加载比例，0<t<=1 且包含 1。')
    return {'result_save_mode': mode, 'field_output_times': cleaned}


def output_policy_summary(options: dict) -> dict:
    """Describe RST output independently of the final nodal CSV option."""
    normalized = normalise_output_options(options)
    mode = normalized['result_save_mode']
    return dict(
        **normalized,
        active_field_output_times=(list(normalized['field_output_times']) if mode == 'selected'
                                   else [1.] if mode == 'last' else []),
        curve_output='all_substeps',
        nldat_output=('all_substeps' if options.get('material_model') == 'multilinear_iso'
                      else 'not_applicable'),
        field_output='all_substeps' if mode == 'all' else mode,
        time_basis='load_fraction',
        export_full_field=options.get('export_full_field', True),
        warnings=[
            'TIME=1 静力加载步中的比例是无量纲加载比例，不是物理秒。',
            '指定比例保存目标时刻或其后的首个收敛子步，不强迫求解器改变时间步。',
            'RST 场保存策略与末步 nodal_results.csv 导出是独立选项；曲线保留全部子步。',
        ],
    )


def material_coverage_hint(options: dict) -> dict:
    """Estimate uniform extension from the last MISO point without editing it."""
    options = _options(options)
    model = options.get('material_model', 'elastic')
    if not isinstance(model, str) or model not in {'elastic', 'bilinear_iso', 'multilinear_iso'}:
        raise ValueError('material_model 无效。')
    hint = dict(
        status='not_applicable', material_model=model, last_plastic_strain=None,
        last_stress_MPa=None, target_engineering_strain=None, target_log_strain=None,
        estimated_last_total_strain=None, estimated_uniform_extension_mm=None,
        exceeds_estimated_coverage=None,
        warnings=['材料覆盖提示仅为均匀应变估算，不能作为积分点验收；腐蚀热点可能超过曲线范围。'],
    )
    if model != 'multilinear_iso':
        hint['warnings'].append('弹性或 BISO 模型没有有限 MISO 表末点覆盖上界，此项不适用。')
        return hint
    curve = options.get('plastic_curve')
    if not isinstance(curve, list) or len(curve) < 2:
        raise ValueError('MISO 覆盖估算需要至少两个原始材料曲线点。')
    for point in curve:
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            raise ValueError('plastic_curve 每点必须是 [塑性应变, 应力MPa]。')
        if _real(point[0], '塑性应变') < 0:
            raise ValueError('塑性应变不能为负。')
        _real(point[1], '应力MPa', positive=True)
    last_plastic, last_stress = map(float, curve[-1])
    length = _real(options.get('length_mm', 100.), 'length_mm', positive=True)
    displacement = _real(options.get('target_displacement_mm', .1),
                         'target_displacement_mm', positive=True)
    modulus = _real(options.get('E_MPa', 206000.), 'E_MPa', positive=True)
    engineering = displacement / length
    last_total = last_plastic + last_stress / modulus
    if not math.isfinite(engineering) or not math.isfinite(last_total):
        raise ValueError('材料覆盖估算数值溢出。')
    logarithmic = math.log1p(engineering)
    try:
        uniform_extension = length * math.expm1(last_total)
    except OverflowError:
        uniform_extension = None
    if uniform_extension is not None and not math.isfinite(uniform_extension):
        uniform_extension = None
    hint.update(
        status='estimate_only', last_plastic_strain=last_plastic,
        last_stress_MPa=last_stress, target_engineering_strain=engineering,
        target_log_strain=logarithmic, estimated_last_total_strain=last_total,
        estimated_uniform_extension_mm=uniform_extension,
        exceeds_estimated_coverage=logarithmic > last_total,
    )
    if uniform_extension is None:
        hint['warnings'].append('对应均匀延伸的估算超出浮点表示范围，未给出该数值。')
    if hint['exceeds_estimated_coverage']:
        hint['warnings'].append('目标加载的均匀对数应变超过 MISO 表末点总应变估算，请审查材料覆盖风险；原曲线保持不变。')
    return hint


def _matrix(value: object, columns: int, name: str) -> np.ndarray:
    array = np.asarray(value)
    if (array.ndim != 2 or array.shape[1] != columns or len(array) == 0
            or array.dtype.kind not in 'fiu' or not np.isfinite(array).all()):
        raise ValueError(f'{name} 必须是非空、{columns} 列的有限实数矩阵。')
    return array


def _ids(value: np.ndarray, name: str) -> np.ndarray:
    # Coordinates share a floating-point table with node IDs; enforce exact
    # representability before conversion and never round references silently.
    if np.any(value <= 0) or np.any(value > 2**53 - 1) or np.any(value != np.floor(value)):
        raise ValueError(f'{name} 必须是可精确表示的正整数编号。')
    return value.astype(np.int64)


def mesh_quality_precheck(nodes: object, elements: object, limit: int = 20) -> dict:
    """Chunked corner Jacobian/edge-ratio warnings; never modifies the mesh.

    worst_elements sorts by increasing corner Jacobian, decreasing edge
    ratio, then element ID. warning_element_count counts Jacobian < 0.1.
    """
    if isinstance(limit, (bool, np.bool_)) or not isinstance(limit, numbers.Integral) or limit < 1:
        raise ValueError('limit 必须是正整数。')
    nodes, elements = _matrix(nodes, 4, 'nodes'), _matrix(elements, 9, 'elements')
    node_ids, element_ids = _ids(nodes[:, 0], '节点'), _ids(elements[:, 0], '单元')
    if len(np.unique(node_ids)) != len(node_ids) or len(np.unique(element_ids)) != len(element_ids):
        raise ValueError('节点或单元编号重复。')
    node_order = np.argsort(node_ids)
    sorted_node_ids = node_ids[node_order]
    minimum, maximum, warning_count, worst = 1., 1., 0, []
    for start in range(0, len(elements), _CHUNK_SIZE):
        block = elements[start:start + _CHUNK_SIZE]
        references = _ids(block[:, 1:], '单元节点引用')
        indices = np.searchsorted(sorted_node_ids, references)
        if np.any(indices >= len(node_ids)):
            raise ValueError('单元引用不存在的节点。')
        if np.any(sorted_node_ids[indices] != references):
            raise ValueError('单元引用不存在的节点。')
        points = np.asarray(nodes[node_order[indices], 1:], dtype=np.float64)
        lengths = np.stack([np.hypot.reduce(points[:, b] - points[:, a], axis=1)
                            for a, b in _EDGES], axis=1)
        if not np.isfinite(lengths).all() or np.any(lengths <= 0):
            raise ValueError('单元边长无效或退化，无法进行几何预检。')
        ratios = lengths.max(axis=1) / lengths.min(axis=1)
        if not np.isfinite(ratios).all():
            raise ValueError('单元边长比数值溢出。')
        axes = []
        for pairs in _CORNER_AXES:
            vectors = np.stack([points[:, b] - points[:, a] for a, b in pairs], axis=1)
            axes.append(vectors / np.hypot.reduce(vectors, axis=2)[:, :, None])
        jacobians = np.einsum('ijk,ijk->ij', axes[0], np.cross(axes[1], axes[2]))
        scores = np.clip(jacobians.min(axis=1), -1., 1.)
        minimum = min(minimum, float(scores.min()))
        maximum = max(maximum, float(ratios.max()))
        warning_count += int(np.count_nonzero(scores < _SCALED_JACOBIAN_WARNING))
        ids = element_ids[start:start + len(block)]
        order = np.lexsort((ids, -ratios, scores))[:limit]
        for index in order:
            worst.append(dict(element_id=int(ids[index]),
                              centroid_mm=(points[index] / 8).sum(axis=0).tolist(),
                              scaled_jacobian=float(scores[index]),
                              edge_length_ratio=float(ratios[index])))
        worst.sort(key=lambda item: (item['scaled_jacobian'], -item['edge_length_ratio'], item['element_id']))
        del worst[limit:]
    warnings = ['Python 角点 scaled Jacobian 和边长比仅为几何预警，不替代 ANSYS 单元质量判据或网格收敛检查。']
    if warning_count:
        warnings.append(f'{warning_count} 个单元的角点 scaled Jacobian 小于 0.1；请检查最差单元位置，未自动修网格或放宽质量限制。')
    if maximum > 20:
        warnings.append(f'最大单元边长比为 {maximum:.3g}，建议检查厚度层数和网格收敛。')
    return dict(status='precheck_only', node_count=len(nodes), element_count=len(elements),
                min_scaled_jacobian=minimum, max_edge_length_ratio=maximum,
                scaled_jacobian_warning_threshold=_SCALED_JACOBIAN_WARNING,
                warning_element_count=warning_count, worst_elements=worst, warnings=warnings)


def diagnostics_for_geometry(geometry: dict) -> dict:
    """Combine only input-derived information; no solver files are created."""
    return dict(material_coverage=material_coverage_hint(geometry['options']),
                mesh_quality=mesh_quality_precheck(geometry['nodes'], geometry['elements']),
                output_policy=output_policy_summary(geometry['options']))

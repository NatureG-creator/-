"""Explicit, audited material table conversion; no sorting or point manufacture."""
import math

from .apdl_geometry import normalise_options
from .fitting_data import load_table
from .system_info import sha256


def uploaded_table(service, payload):
    record, path = service.get_upload(payload.get('upload_id'))
    if sha256(path) != record['sha256']:
        raise ValueError('上传文件已变化，请重新上传')
    table = load_table(path, sheet=payload.get('sheet'), variable=payload.get('variable'))
    return table, dict(name=record['name'], sha256=record['sha256'], upload_id=record['id'],
                       sheet=table.get('sheet'), variable=table.get('variable')), path


def numeric_pair(table, selection, x_key, y_key):
    indices = [selection.get(x_key), selection.get(y_key)]
    if any(type(i) is not int or not 0 <= i < len(table['columns']) for i in indices) or indices[0] == indices[1]:
        raise ValueError('请选择两个不同的有效数据列')
    pairs = []
    for row_number, row in enumerate(table['rows'], 1):
        values = [row[i] for i in indices]
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in values):
            raise ValueError(f'第{row_number}行不是有限数值；不自动剔除')
        pairs.append(values)
    return pairs


def convert_material_table(table, selection):
    pairs = numeric_pair(table, selection, 'strain_column', 'stress_column')
    strain_unit = selection.get('strain_unit')
    stress_unit = selection.get('stress_unit')
    kind = selection.get('strain_type')
    if strain_unit not in {'fraction', 'percent'} or stress_unit not in {'Pa', 'MPa'}:
        raise ValueError('必须明确选择应变和应力单位')
    if kind not in {'true_plastic', 'true_total', 'engineering'}:
        raise ValueError('必须明确选择应变类型')
    modulus = selection.get('E_MPa')
    if type(modulus) not in (int, float) or not math.isfinite(modulus) or modulus <= 0:
        raise ValueError('弹性模量必须为正的MPa值')
    if kind != 'true_plastic' and selection.get('uniform_before_necking') is not True:
        raise ValueError('总应变转换须确认数据为颈缩前均匀拉伸阶段')
    curve = []
    for strain, stress in pairs:
        strain /= 100 if strain_unit == 'percent' else 1
        stress /= 1e6 if stress_unit == 'Pa' else 1
        if kind == 'engineering':
            if strain <= -1:
                raise ValueError('工程应变必须大于-1')
            stress *= 1 + strain
            strain = math.log1p(strain)
        if kind != 'true_plastic':
            strain -= stress / modulus
            # Floating subtraction at yield can leave machine roundoff, not a physical offset.
            if abs(strain) <= 1e-14:
                strain = 0.0
        curve.append([strain, stress])
    options = normalise_options(dict(material_model='multilinear_iso', E_MPa=modulus,
        plastic_curve=curve, allow_negative_slope=selection.get('allow_negative_slope', False)))
    return dict(curve=options['plastic_curve'], points=len(curve), selection=selection,
        note='保持原行顺序，未补屈服点、平滑或降采样；首点必须是塑性应变0的真实屈服点')


def import_material(service, payload):
    table, source, _ = uploaded_table(service, payload)
    return dict(convert_material_table(table, payload.get('selection', {})), source=source)


def prepare_material_source(service, payload, options):
    if not isinstance(payload, dict):
        raise ValueError('材料来源必须是对象')
    table, source, path = uploaded_table(service, payload)
    result = convert_material_table(table, payload.get('selection', {}))
    if (options['material_model'] != 'multilinear_iso'
            or options['plastic_curve'] != result['curve']
            or options['E_MPa'] != result['selection']['E_MPa']):
        raise ValueError('材料参数与导入来源不一致，请重新转换或清除导入来源')
    input_path = 'inputs/material_original' + path.suffix.lower()
    return dict(source=source, selection=result['selection'], input_path=input_path), dict(
        path=path, sha256=source['sha256'], input_path=input_path, label='material')

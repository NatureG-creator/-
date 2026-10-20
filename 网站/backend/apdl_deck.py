"""Write self-contained ASCII MAPDL tension inputs; never fabricate solver data."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import zipfile

import numpy as np

from .apdl_diagnostics import diagnostics_for_geometry
from .apdl_plots import contour_commands
from .apdl_macros import (DIAGNOSTICS_SCHEMA_VERSION, diagnostic_macros,
                          material_coverage_commands, output_commands)


def _number(value: float) -> str:
    return format(float(value), '.17g')


def _ascii(path: Path, text: str) -> None:
    path.write_text(text.rstrip()+'\n', encoding='ascii', newline='\n')


def _boundaries(geometry: dict) -> str:
    o = geometry['options']
    direction = o.get('tensile_direction', 'X')
    if direction not in {'X', 'Y'}:
        raise ValueError('tensile_direction 只支持 X 或 Y。')
    axis, axial_dof = ('X', 'UX') if direction == 'X' else ('Y', 'UY')
    transverse_dof = 'UY' if direction == 'X' else 'UX'
    axial_coords = geometry['x'] if direction == 'X' else geometry['y']
    transverse_coords = geometry['y'] if direction == 'X' else geometry['x']
    axial_spacing = o['dx_mm'] if direction == 'X' else o['dy_mm']

    def corner(transverse_index, axial_index, top=False):
        row, col = ((transverse_index, axial_index) if direction == 'X'
                    else (axial_index, transverse_index))
        z = (o['thickness_mm']-geometry['top_depth'][row, col]
             if top else geometry['bottom_depth'][row, col])
        target = [geometry['x'][col], geometry['y'][row], z]
        matches = np.flatnonzero(np.all(geometry['nodes'][:,1:] == target, axis=1))
        if len(matches) != 1:
            raise ValueError('边界角点坐标不能唯一映射到网格节点。')
        return int(geometry['nodes'][matches[0],0])
    first, last = _number(axial_coords[0]), _number(axial_coords[-1])
    delta = _number(o['target_displacement_mm'])
    axial_span = float(axial_coords[-1]-axial_coords[0])
    if o['boundary_mode'] == 'clamped_grips':
        grip_fixed = float(o.get('grip_length_fixed_mm', 0.))
        grip_loaded = float(o.get('grip_length_loaded_mm', 0.))
        if grip_fixed*2 > axial_span + 1e-9 or grip_loaded*2 > axial_span + 1e-9 or grip_fixed+grip_loaded > axial_span + 1e-9:
            raise ValueError('夹持长度超过轴向跨度或两端重叠；请减小 grip_length_fixed_mm / grip_length_loaded_mm。')
    lines = [
        f'! {direction} tension; all input coordinates and displacements are in mm.',
        'CSYS,0', 'SELTOL,'+_number(geometry['stats'].get('grip_tolerance_mm', axial_spacing*.01)),
        f'NSEL,S,LOC,{axis},{first}',
    ]
    if o['boundary_mode'] == 'clamped_grips' and float(o.get('grip_length_fixed_mm', 0.)) > 0:
        lines.append(f'NSEL,A,LOC,{axis},{first},{_number(float(axial_coords[0])+float(o["grip_length_fixed_mm"]))}')
    lines += ['CM,GRIP_FIXED,NODE', f'D,ALL,{axial_dof},0']
    if o['boundary_mode'] == 'clamped_grips':
        lines += [f'D,ALL,{transverse_dof},0', 'D,ALL,UZ,0']
    grip_loaded_sel = ([f'NSEL,S,LOC,{axis},{_number(float(axial_coords[-1])-float(o["grip_length_loaded_mm"]))},{last}',
                        f'NSEL,A,LOC,{axis},{last}']
                       if o['boundary_mode'] == 'clamped_grips' and float(o.get('grip_length_loaded_mm', 0.)) > 0
                       else [f'NSEL,S,LOC,{axis},{last}'])
    lines += grip_loaded_sel+['CM,GRIP_LOADED,NODE', f'D,ALL,{axial_dof},{delta}']
    if o['boundary_mode'] == 'clamped_grips':
        lines += [f'D,ALL,{transverse_dof},0', 'D,ALL,UZ,0']
    elif o['boundary_mode'] == 'legacy_recommended':
        corner_a, corner_b = corner(-1, 0), corner(-1, 0, top=True)
        lines += ['ALLSEL,ALL', '! Original recommended grips, mapped to bottom-first layers.',
                  f'D,{corner_b},{transverse_dof},0', f'D,{corner_b},UZ,0',
                  f'D,{corner_a},{transverse_dof},0']
    else:
        # One corner removes transverse/Z translation; the second removes only
        # rotation about the loading axis while preserving Poisson contraction.
        corner_a, corner_b = corner(0, 0), corner(-1, 0)
        z_a = float(geometry['bottom_depth'][0, 0])
        z_b = float(geometry['bottom_depth'][-1, 0] if direction == 'X'
                    else geometry['bottom_depth'][0, -1])
        dz = z_b-z_a
        span = float(transverse_coords[-1]-transverse_coords[0])
        lines += ['ALLSEL,ALL', f'D,{corner_a},{transverse_dof},0', f'D,{corner_a},UZ,0']
        if dz == 0:
            lines.append(f'D,{corner_b},UZ,0')
        else:
            lines.append('! Rotation constraint permits isotropic Poisson contraction.')
            if direction == 'X':
                lines.append(f'CE,1,0,{corner_b},UZ,{_number(span)},{corner_b},UY,{_number(-dz)}')
            else:
                lines.append(f'CE,1,0,{corner_b},UX,{_number(-dz)},{corner_b},UZ,{_number(span)}')
    return '\n'.join(lines+['ALLSEL,ALL', 'SELTOL'])


def _post(geometry: dict) -> str:
    o = geometry['options']
    direction = o.get('tensile_direction', 'X')
    if direction not in {'X', 'Y'}:
        raise ValueError('tensile_direction 只支持 X 或 Y。')
    displacement_dof, reaction_dof = ('UX', 'FX') if direction == 'X' else ('UY', 'FY')
    axial_length = o['length_mm'] if direction == 'X' else o['width_mm']
    lines = [
        '/POST1', 'RSYS,0', 'ALLSEL,ALL', 'SET,LAST',
        '*GET,nsets,ACTIVE,0,SET,NSET', '*CFOPEN,force_displacement,csv',
        f'! No header: time,{displacement_dof.lower()},Floaded,Ffixed,engineering_strain,nominal_stress.',
        '! Six E19.11 fields + commas fit the MAPDL 128 character output limit.',
        '*DO,iset,1,nsets', 'SET,,,,,,,iset', '*GET,tm,ACTIVE,0,SET,TIME',
        'CMSEL,S,GRIP_LOADED', '*GET,ncnt,NODE,0,COUNT', 'nid=0', 'fl=0', 'usum=0',
        '*DO,jj,1,ncnt', 'nid=NDNEXT(nid)', f'*GET,rr,NODE,nid,RF,{reaction_dof}',
        f'*GET,uu,NODE,nid,U,{direction}', 'fl=fl+rr', 'usum=usum+uu', '*ENDDO',
        'uax=usum/ncnt', 'CMSEL,S,GRIP_FIXED', '*GET,ncnt,NODE,0,COUNT', 'nid=0', 'ff=0',
        '*DO,jj,1,ncnt', 'nid=NDNEXT(nid)', f'*GET,rr,NODE,nid,RF,{reaction_dof}', 'ff=ff+rr', '*ENDDO',
        'engstrain=uax/'+_number(axial_length),
        'nomstress=fl/'+_number(geometry['stats']['nominal_area_mm2']),
        '*VWRITE,tm,uax,fl,ff,engstrain,nomstress',
        "(E19.11,5(',',E19.11))",
        '*ENDDO', '*CFCLOS', 'ALLSEL,ALL',
    ]
    if o['material_model'] == 'multilinear_iso':
        lines += material_coverage_commands()
    if o['export_full_field']:
        lines += ['SET,LAST']
        if o['material_model'] != 'elastic':
            # Switching S/EPPL at every node repeatedly recomputes nodal averaging.
            lines += [
                '*GET,nn,NODE,0,COUNT', '*DIM,ns_values,ARRAY,nn', '*DIM,np_values,ARRAY,nn',
                'nid=0', '*DO,jj,1,nn', 'nid=NDNEXT(nid)',
                '*GET,seqv,NODE,nid,S,EQV', 'ns_values(jj)=seqv', '*ENDDO',
                'nid=0', '*DO,jj,1,nn', 'nid=NDNEXT(nid)',
                '*GET,eqpl,NODE,nid,EPPL,EQV', 'np_values(jj)=eqpl', '*ENDDO',
            ]
        lines += [
            '*CFOPEN,nodal_results,csv',
            '! Final set; no header: id,x,y,z,ux,uy,uz,seqv,eqpl.',
            '! S/EPPL are averaged nodal results, not integration-point peaks.',
            '! Short field widths keep nine columns within 128 output characters.',
            '*GET,nn,NODE,0,COUNT', 'nid=0', '*DO,jj,1,nn', 'nid=NDNEXT(nid)',
            '*GET,xx,NODE,nid,LOC,X', '*GET,yy,NODE,nid,LOC,Y', '*GET,zz,NODE,nid,LOC,Z',
            '*GET,uu,NODE,nid,U,X', '*GET,vv,NODE,nid,U,Y', '*GET,ww,NODE,nid,U,Z',
        ]
        lines += (['seqv=ns_values(jj)', 'eqpl=np_values(jj)']
                  if o['material_model'] != 'elastic' else ['*GET,seqv,NODE,nid,S,EQV', 'eqpl=0'])
        lines += [
            '*VWRITE,nid,xx,yy,zz,uu,vv,ww,seqv,eqpl',
            "(F12.0,8(',',E13.5))",
            '*ENDDO', '*CFCLOS',
        ]
    return '\n'.join(lines+['ALLSEL,ALL', 'FINISH'])


def _write_preview(path: Path, geometry: dict) -> None:
    import matplotlib
    matplotlib.use('Agg')
    from matplotlib import pyplot as plt

    o = geometry['options']
    extent = [geometry['x'][0], geometry['x'][-1], geometry['y'][0], geometry['y'][-1]]
    fig, axes = plt.subplots(1, 3, figsize=(13, 3.6), constrained_layout=True)
    try:
        for axis, key, title in zip(axes[:2], ('top_depth', 'remaining'), ('Top corrosion depth (mm)', 'Remaining thickness (mm)')):
            image = axis.imshow(geometry[key], extent=extent, origin='lower', aspect='auto')
            axis.set(title=title, xlabel='X (mm)', ylabel='Y (mm)')
            fig.colorbar(image, ax=axis)
        direction = o.get('tensile_direction', 'X')
        if direction == 'X':
            middle = o['ny']//2
            axial_coords = geometry['x']
            top_section = geometry['top_depth'][middle]
            bottom_section = geometry['bottom_depth'][middle]
        else:
            middle = o['nx']//2
            axial_coords = geometry['y']
            top_section = geometry['top_depth'][:, middle]
            bottom_section = geometry['bottom_depth'][:, middle]
        axes[2].plot(axial_coords, o['thickness_mm']-top_section, label='Top')
        axes[2].plot(axial_coords, bottom_section, label='Bottom')
        axes[2].set(title=f'Midline section along {direction} (undeformed)',
                    xlabel=f'{direction} (mm)', ylabel='Z (mm)')
        axes[2].legend()
        fig.savefig(path, dpi=150)
    finally:
        plt.close(fig)


def create_tension_bundle(geometry: dict, output_dir: Path, provenance: dict) -> dict:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    o = geometry['options']
    files = []
    for name, key in (('top_depth.csv', 'top_depth'), ('bottom_depth.csv', 'bottom_depth'),
                      ('remaining_thickness.csv', 'remaining')):
        np.savetxt(output_dir/name, geometry[key], delimiter=',', fmt='%.16g')
        files.append(name)
    np.savez_compressed(output_dir/'surface_inputs.npz',
                        top_depth=geometry['top_depth'], bottom_depth=geometry['bottom_depth'],
                        remaining=geometry['remaining'], x=geometry['x'], y=geometry['y'])
    files.append('surface_inputs.npz')
    if provenance.get('surface_mapping'):
        (output_dir/'surface_mapping.json').write_text(
            json.dumps(provenance['surface_mapping'], ensure_ascii=False, indent=2), encoding='utf-8')
        files.append('surface_mapping.json')
    with (output_dir/'nodes.dat').open('w', encoding='ascii', newline='\n') as stream:
        for node in geometry['nodes']:
            stream.write(f'N,{int(node[0])},'+','.join(_number(v) for v in node[1:])+'\n')
    with (output_dir/'elements.dat').open('w', encoding='ascii', newline='\n') as stream:
        for element in geometry['elements']:
            stream.write('EN,'+','.join(str(int(v)) for v in element[:9])+'\n')
            if len(element) > 9:
                stream.write('EMORE,'+','.join(str(int(v)) for v in element[9:])+'\n')
    files += ['nodes.dat', 'elements.dat']
    materials = f"MP,EX,1,{_number(o['E_MPa'])}\nMP,PRXY,1,{_number(o['poisson_ratio'])}"
    if o['material_model'] == 'bilinear_iso':
        materials += f"\nTB,BISO,1\nTBDATA,1,{_number(o['yield_MPa'])},{_number(o['tangent_MPa'])}"
    elif o['material_model'] == 'multilinear_iso':
        curve = o['plastic_curve']
        materials += f'\nTB,PLASTIC,1,0,{len(curve)},MISO'
        if o['allow_negative_slope'] and any(b[1] < a[1] for a,b in zip(curve, curve[1:])):
            materials += '\nTBEO,NEGSLOPE,1'
        materials += ''.join(f'\nTBPT,,{_number(strain)},{_number(stress)}' for strain,stress in curve)
    _ascii(output_dir/'materials.mac', materials)
    _ascii(output_dir/'boundary.mac', _boundaries(geometry))
    solve = [
        '/SOLU', 'ANTYPE,STATIC,NEW', 'SOLCONTROL,ON', 'LNSRCH,1',
        'NLGEOM,'+('ON' if o['large_deflection'] else 'OFF'),
        'TIME,1', f"NSUBST,{o['substeps']},{o['max_substeps']},{o['min_substeps']}",
        'AUTOTS,ON', 'KBC,0',
    ]
    solve += output_commands(o)
    if o['restart_frequency']:
        solve += [f"RESCONTROL,DEFINE,ALL,{o['restart_frequency']}"]
    else:
        solve += ['RESCONTROL,DEFINE,NONE']
    solve += ['SOLVE', 'FINISH', 'SAVE']
    _ascii(output_dir/'solve.mac', '\n'.join(solve))
    _ascii(output_dir/'post.mac', _post(geometry))
    _ascii(output_dir/'plots.mac', contour_commands(o['material_model']))
    files.append('plots.mac')
    for name, text in diagnostic_macros(geometry).items():
        _ascii(output_dir/name, text)
        files.append(name)
    element_type = {'solid185_hex': 'SOLID185', 'solid187_tetra': 'SOLID187',
                    'solid285_tetra': 'SOLID285'}[o['mesh_type']]
    _ascii(output_dir/'main.inp', '\n'.join([
        '! Generated geometry: N-mm-MPa. Inspect settings before research use.',
        '/CLEAR,START', '/FILNAME,corrosion', '/PREP7', f'ET,1,{element_type}',
        '/INPUT,materials,mac', 'TYPE,1', 'MAT,1', 'SHPP,ON',
        *(['SHPP,SILENT,ON'] if o['mesh_type'] != 'solid185_hex' else []),
        '/INPUT,nodes,dat', '/INPUT,elements,dat', 'ALLSEL,ALL',
        '/INPUT,mesh_quality,mac', '/INPUT,mesh_self_check,mac',
        '/INPUT,boundary,mac', '/INPUT,boundary_self_check,mac', 'FINISH', 'SAVE',
        '/INPUT,solve,mac', '/INPUT,post,mac', '/EXIT,NOSAVE',
    ]))
    _ascii(output_dir/'run_apdl.cmd', '\n'.join([
        '@echo off', 'setlocal', 'if "%~1"=="" (',
        '  echo Usage: run_apdl.cmd "C:\\path\\to\\ansysXXX.exe"', '  exit /b 2', ')',
        'if not exist "%~1" (', '  echo MAPDL executable not found.', '  exit /b 2', ')',
        'pushd "%~dp0"',
        f'"%~1" -b -np {o["cores"]} -j corrosion -i main.inp -o mapdl.out',
        'set "MAPDL_CODE=%ERRORLEVEL%"', 'popd', 'exit /b %MAPDL_CODE%',
    ]))
    files += ['main.inp', 'materials.mac', 'boundary.mac', 'solve.mac', 'post.mac', 'run_apdl.cmd']
    diagnostics = diagnostics_for_geometry(geometry)
    (output_dir/'diagnostics_precheck.json').write_text(
        json.dumps(diagnostics, ensure_ascii=False, indent=2), encoding='utf-8')
    files.append('diagnostics_precheck.json')
    warnings = list(geometry['warnings'])
    try:
        _write_preview(output_dir/'geometry_preview.png', geometry)
        files.append('geometry_preview.png')
    except Exception as exc:
        warnings.append(f'几何预览绘制失败，但数值和APDL输入已保留：{type(exc).__name__}: {exc}')
    readme = '''# 单轴拉伸 APDL 输入包

本包是三维 SOLID185、SOLID187 或 SOLID285 输入，单位统一为 N、mm、MPa。腐蚀深度正值向板内，数据为 depth[row_y, col_x]。
正面 Z=t0-top_depth，反面 Z=bottom_depth；剩余厚度=t0-top_depth-bottom_depth。
网格生成阶段不再插值、裁剪或修补形貌；来源阶段的显式裁剪、参考面与坐标变换见manifest.json。

检查 manifest.json 中的参数、来源和 SHA256，然后运行：
`run_apdl.cmd "C:\\Program Files\\ANSYS Inc\\vXXX\\ansys\\bin\\winx64\\ANSYSXXX.exe"`
也可在 MAPDL 中读取 main.inp。需要本机合法可用的 MAPDL 和对应许可证。

拉伸方向由 options.tensile_direction 选择 X 或 Y（默认 X）。相应两端选择全局 X/Y 端面并施加 UX/UY；位移、反力、标距和名义截面积随方向同步变化。
poisson_free 模板：两端仅约束所选轴向位移，固定端角点去除横向/Z平移，第二角点用几何约束方程去除绕拉伸轴转动，保持泊松收缩可行。
clamped_grips 模板：两端横向/Z位移为0，模拟夹持。模型不自动增加未腐蚀夹持段。
legacy_recommended 模板保留原GitHub主宏的角点约束，并按所选拉伸轴映射到对应固定端。
双线性等向硬化参数为屈服应力与屈服后切线模量；多线性等向硬化输入[塑性应变,应力MPa]，不包含断裂或材料失效。
多线性曲线要求首应变0、应变严格递增；负斜率需要明确允许并输出TBEO,NEGSLOPE,1，不擅自平滑原曲线。
初始节点/单元、材料、边界、求解和后处理分文件，均可独立审阅。SOLID187/SOLID285使用全局一致六分四面体，公共面一致、厚度层正确连接，不自动加密；SOLID187增加共享边中节点，以EN前8节点加EMORE后2节点导入。两种阶次不能假定结果相同，需网格收敛验证。
四面体表面采用固定00-11对角线三角化，保留全部原始采样坐标与深度；实际体积与双线性参考体积及二者之差见stats。原始点距不是允许放大的显示比例。

diagnostics_precheck.json 仅包含输入推导的材料覆盖估算、Python网格几何预警和保存策略。
diagnostics_schema_version=2；三个诊断宏及预检报告的SHA256记录于manifest.json。
导入前SHPP,ON启用默认单元形状阈值。六面体保留CHECK；四面体用SHPP,SILENT,ON汇总大量重复警告，并以SHPP,SUMMARY记录数量、ESCHECK,ESEL,ERR筛选形状错误，非零则退出。没有提高/NERR上限或放宽几何阈值。无形状错误也不代表质量优秀，长宽比警告仍需收敛验证。
mesh_self_check.mac验证实际节点/单元数量和连续编号范围，boundary_self_check.mac验证两端组件数量、端面位置及互不重叠。
失败输出APDL_SELF_CHECK_FAILED并退出，不继续SOLVE；两阶段原始记录不等于科研结果验收。

RST保存模式result_save_mode：all（默认）保留原OUTRES,ALL,ALL；last仅末子步保存完整元素场；selected目前兼容回退完整保存。
last/selected仍逐子步保存NSOL/RSOL以保留完整曲线，MISO的NLDAT也逐子步保存供材料筛查。
TIME=1中的field_output_times是无量纲加载比例，不是物理秒；selected比例只记录请求，不减少RST体积。MAPDL不允许关键时刻数组与逐子步频率混用，因此优先保留完整曲线，不改变时间步。
RST保存策略与export_full_field末步节点CSV导出独立；稀疏元素场不代表所有RST数据均只保存指定步。

真实求解后才生成以下CSV（无表头）：
force_displacement.csv：6列 time, displacement_mm, loaded_reaction_N, fixed_reaction_N, engineering_strain, nominal_stress_MPa。
名义应力分母为拉伸轴横向尺寸*thickness，反力按约束节点求和保留符号；平衡检查看两端反力之和。
nodal_results.csv（可选）：9列 id,x_mm,y_mm,z_mm,ux_mm,uy_mm,uz_mm,seqv_MPa,eqpl。
SEQV/EPPL为平均节点值，不代表积分点峰值；弹性模型eqpl固定为0。
apdl_self_check.csv：6列stage,node_count,element_count,fixed_count,loaded_count,passed；阶段1为网格，固定/加载数量均为-1；阶段2为边界实际数量。
material_coverage_history.csv（仅MISO）：6列time,max_element_nodal_epeq,element_id,centroid_x,centroid_y,centroid_z。
筛查逐结果集用ETABLE的NL,EPEQ,MAX元素节点代理；不是已核验积分点极值，未提示超表不能证明全部积分点覆盖。
mesh_quality_report.txt是实际运行产生的MAPDL原始报告；文件存在不自动表示质量通过。生成输入包时不制造这些运行文件。
MAPDL *VWRITE输出行上限128字符；曲线采用E19.11，节点编号F12.0及其余E13.5，避免9列被截断。
完整原始输入保存在surface_inputs.npz和CSV，节点命令使用17位有效数字以保留双精度坐标。

几何体积/边长比仅为预检，不替代MAPDL网格检查及网格收敛研究。SOLID185使用默认积分设置。
flat解析EA/L与EAδ/L只是小变形、弹性、自由泊松伸缩参考；非线性或夹持工况不保证满足此参考。
SAVE模型及RESCONTROL重启动文件不代表任意断电点可自动恢复；重启需保留MAPDL完整文件集并人工核对。
输入包生成成功不代表求解已经成功，任何CSV、RST结果均必须由真实MAPDL生成。
plots.mac 为独立原生云图宏：已有求解结果时，先 RESUME,corrosion,db，再 /POST1、FILE,corrosion,rst、SET,LAST 后 /INPUT,plots,mac。
网站标准参数求解成功后自动在 contour_plots 子目录恢复已有 DB/RST 出图，不重新求解。独立运行 main.inp 后，可手动执行上述后处理。
输出末步总位移(mm)、节点平均等效应力(MPa)，弹塑性工况另输出节点平均等效塑性应变(无量纲)；真实变形比例1倍，FULL平均，不能当作积分点峰值。
云图导出失败与物理解算状态分别记录，不修改材料曲线、几何、边界或加载。
'''
    (output_dir/'README_zh.md').write_text(readme, encoding='utf-8')
    files.append('README_zh.md')
    summary = dict(analysis='tension', build_state='built', options=o,
                   stats=geometry['stats'], provenance=provenance, warnings=warnings,
                   diagnostics_schema_version=DIAGNOSTICS_SCHEMA_VERSION,
                   diagnostics=diagnostics, output_policy=diagnostics['output_policy'],
                   files=files+['manifest.json', 'apdl_tension_input_bundle.zip'])
    manifest = dict(schema_version=1, **summary)
    manifest['files'] = {name: hashlib.sha256((output_dir/name).read_bytes()).hexdigest() for name in files}
    (output_dir/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    with zipfile.ZipFile(output_dir/'apdl_tension_input_bundle.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for name in files+['manifest.json']:
            archive.write(output_dir/name, name)
    return summary

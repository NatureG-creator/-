"""Cross-check native LS-DYNA binaries; never synthesize a post-peak curve."""
from pathlib import Path
import re

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components


def load_path_exists(connectivity, alive, fixed, loaded, node_count):
    live = connectivity[np.asarray(alive, dtype=bool)]
    if not len(live):
        return False
    first = np.repeat(live[:, 0], 7)
    rest = live[:, 1:].ravel()
    graph = coo_matrix((np.ones(2*len(first), dtype=np.int8),
                        (np.r_[first, rest], np.r_[rest, first])), shape=(node_count, node_count)).tocsr()
    _, labels = connected_components(graph, directed=False)
    return bool(np.intersect1d(labels[fixed], labels[loaded]).size)


def section_areas(coordinates, nx, ny, layers, axis):
    grid = coordinates.reshape(layers+1, ny, nx, 3)
    # A section is a quadrilateral grid in thickness and transverse directions.
    sections = np.moveaxis(grid, 2 if axis == 0 else 1, 0)
    a, b = sections[:, :-1, :-1], sections[:, 1:, :-1]
    c, d = sections[:, 1:, 1:], sections[:, :-1, 1:]
    return (np.linalg.norm(np.cross(b-a, c-a), axis=-1)
            + np.linalg.norm(np.cross(c-a, d-a), axis=-1)).sum(axis=(1, 2))/2


def read_fracture_results(output, stats, options):
    from lasso.dyna import D3plot, Binout
    from .runner import _atomic_json
    output = Path(output)
    with np.load(output/'fracture_geometry.npz', allow_pickle=False) as saved:
        nodes, elements = saved['nodes'], saved['elements']
        fixed, loaded = saved['fixed'], saved['loaded']
    axis = 0 if options['tensile_direction'] == 'X' else 1
    d3 = D3plot(str(output/'d3plot'))
    a = d3.arrays
    if (not np.array_equal(a['node_ids'], nodes[:, 0])
            or not np.array_equal(a['element_solid_ids'], elements[:, 0])
            or not np.array_equal(a['element_solid_node_indexes'], elements[:, 1:]-1)
            or not np.allclose(a['node_coordinates'], nodes[:, 1:], rtol=1e-8, atol=1e-8)):
        raise ValueError('d3plot 的节点、连接关系或原始坐标与冻结输入不一致。')
    times = a['timesteps']
    if not np.isfinite(times).all() or len(times) < 3 or np.any(np.diff(times) <= 0):
        raise ValueError('原生结果时间必须为严格递增的有限值。')
    duration = options['loading_time_s']
    if not .9999 <= times[-1]/duration <= 1.001:
        raise ValueError('LS-DYNA 未计算到目标物理时间，不能认定完整加载。')
    # lasso 2.0.3 exposes native deformed coordinates under node_displacement.
    if not np.allclose(a['node_displacement'][0], nodes[:, 1:], rtol=1e-8, atol=1e-8):
        raise ValueError('初始状态坐标与输入不一致；请核对 d3plot 读取库版本。')
    displacement = a['node_displacement']-nodes[None, :, 1:]
    a['node_displacement'] = displacement
    if not np.isfinite(displacement).all():
        raise ValueError('原生位移包含非有限值。')
    applied = displacement[:, loaded, axis].mean(axis=1)-displacement[:, fixed, axis].mean(axis=1)
    if abs(applied[-1]-options['target_displacement_mm']) > max(1e-7, options['target_displacement_mm']*1e-4):
        raise ValueError('原生末步位移未达到设定目标。')
    if np.any(np.diff(applied) < -1e-7):
        raise ValueError('单调拉伸位移出现回退。')
    raw_alive = a['element_solid_is_alive']
    if not np.isin(raw_alive, [0, 1]).all() or np.any(np.diff(raw_alive.astype(int), axis=0) > 0):
        raise ValueError('原生单元存活标记无效或出现未定义的单元复活。')
    alive = raw_alive.astype(bool)
    deleted = (~alive).sum(axis=1)
    text = (output/'d3hsp').read_text(encoding='utf-8', errors='replace')
    match = re.search(r'PID\s+1\s*:\s*first damage history variable ND\s*=\s*(\d+)', text, re.I)
    if not match:
        raise ValueError('未找到原生 GISSMO 损伤历史变量位置，拒绝猜测损伤列。')
    index = int(match[1])-1
    history = a['element_solid_history_variables']
    if history.shape[-1] <= index+2 or not np.isfinite(history).all():
        raise ValueError('GISSMO 历史变量缺失或非有限。')
    damage = history[..., index].max(axis=2)
    coupled = history[..., index+2].max(axis=2)
    if np.any(damage < -1e-8) or np.any(damage > 1+1e-6):
        raise ValueError('GISSMO 损伤超出 [0,1]；请核查二进制读取与模型。')
    binout = Binout(str(output/'binout*'))
    bt = binout.read('bndout', 'velocity', 'nodes', 'time')
    bids = binout.read('bndout', 'velocity', 'nodes', 'ids')
    loaded_mask = np.isin(bids, nodes[loaded, 0])
    if np.count_nonzero(loaded_mask) != len(loaded):
        raise ValueError('反力输出不包含全部加载端节点。')
    force_name = ('x', 'y')[axis]+'_force'
    raw_force = binout.read('bndout', 'velocity', 'nodes', force_name)[:, loaded_mask].sum(axis=1)
    ft = binout.read('spcforc', 'time')
    fids = binout.read('spcforc', 'force_ids')
    fixed_mask = np.isin(fids, nodes[fixed, 0])
    if np.count_nonzero(fixed_mask) != len(fixed):
        raise ValueError('反力输出不包含全部固定端节点。')
    raw_fixed = binout.read('spcforc', force_name)[:, fixed_mask].sum(axis=1)
    if (not np.isfinite(raw_force).all() or not np.isfinite(raw_fixed).all()
            or np.any(np.diff(bt) <= 0) or np.any(np.diff(ft) <= 0)
            or bt[0] > times[1] or bt[-1] < times[-1]-duration*1e-4):
        raise ValueError('原生反力时间历史不完整或无效。')
    # Native databases differ by at most one explicit step; align, without smoothing.
    force = np.interp(times, bt, raw_force, left=0.)
    fixed_force = np.interp(times, ft, raw_fixed, left=0.)
    length = stats['length_mm'] if axis == 0 else stats['width_mm']
    curve = np.column_stack((times/duration, applied, force, fixed_force,
                             applied/length, force/stats['nominal_area_mm2']))
    peak = int(np.argmax(force))
    if force[peak] <= 1e-4:
        raise ValueError('未检测到有效的拉伸承载响应。')
    first_deleted = int(np.flatnonzero(deleted)[0]) if np.any(deleted) else None
    before = max(0, first_deleted-1) if first_deleted is not None else len(times)-1
    areas0 = section_areas(nodes[:, 1:], stats['nx'], stats['ny'], options['layers'], axis)
    areas = section_areas(nodes[:, 1:]+displacement[before], stats['nx'], stats['ny'], options['layers'], axis)
    interior = np.arange(len(areas))[1:-1]
    ratios = areas[interior]/areas0[interior]
    local_index = int(np.argmin(ratios))
    localization = float(ratios[local_index]/np.median(ratios))
    separation = not load_path_exists(a['element_solid_node_indexes'], alive[-1], fixed, loaded, len(nodes))
    residual = float(abs(force[-1])/force[peak])
    gt = binout.read('glstat', 'time')
    ie, ke = binout.read('glstat', 'internal_energy'), binout.read('glstat', 'kinetic_energy')
    de = binout.read('glstat', 'system_damping_energy')
    if not np.isfinite(ie).all() or not np.isfinite(ke).all() or not np.isfinite(de).all():
        raise ValueError('能量历史包含非有限值。')
    pre = (gt <= times[before]) & (ie > max(ie.max()*.01, 1e-15))
    energy_ratio = float(np.max(ke[pre]/ie[pre])) if np.any(pre) else None
    damping_ratio = float(np.max(np.abs(de[pre])/ie[pre])) if np.any(pre) else None
    balance_mask = (times <= times[before]) & (force > force[peak]*.1)
    balance = float(np.max(np.abs(force[balance_mask]+fixed_force[balance_mask]))/force[peak]) if np.any(balance_mask) else None
    calibrated = options['damage_parameter_basis'] == 'calibrated'
    fracture = dict(model='MAT_024 + GISSMO', parameter_basis=options['damage_parameter_basis'],
                    necking_observed=localization < .9, section_localization_ratio=localization,
                    minimum_section_area_ratio=float(ratios[local_index]),
                    section_index=int(interior[local_index]), section_time_s=float(times[before]),
                    damage_observed=bool(np.max(damage) > .01), coupling_observed=bool(np.max(coupled) > .5),
                    max_damage_observed=float(damage.max()), damage_history_variable=index+1,
                    deleted_elements=int(deleted[-1]), load_path_separated=separation,
                    fracture_confirmed=bool(separation and deleted[-1] and residual < .05),
                    first_deletion_time_s=float(times[first_deleted]) if first_deleted is not None else None,
                    peak_force_n=float(force[peak]), peak_engineering_strain=float(curve[peak, 4]),
                    final_force_ratio=residual, prefracture_max_kinetic_internal_ratio=energy_ratio,
                    damping_per_s=options['damage_damping_per_s'], prefracture_max_damping_internal_ratio=damping_ratio,
                    prefracture_max_force_imbalance_ratio=balance,
                    quasistatic_screen_passed=bool(energy_ratio is not None and energy_ratio < .05 and balance is not None and balance < .05 and damping_ratio is not None and damping_ratio < .05),
                    calibration_verified=False,
                    note='断裂检查要求单元失效、两端无存活网格连接、末步拉力低于峰值5%。截面非均匀收缩比<0.9仅为颈缩筛查。准静态还需加载时间敏感性验证；试验标定声明未在此独立验证。')
    warnings = ['显式模型按能量及反力进行准静态筛查，不套用静力分析的逐步1%反力平衡判据。',
                '原生反力按 d3plot 时间线性对齐，未平滑或修改下降段；原始 binout 保留。',
                '当前导出应变为加载端相对位移/模型端面跨度；与试验引伸计标距可能不同。']
    warnings.append('断裂后可能存在卸载波与反力正负振荡；原始曲线保留，不取绝对值或人为平滑。数值阻尼影响需单独复核。')
    if not calibrated:
        warnings.append('当前为示例材料和损伤参数，结果仅验证流程，不能作为钢材定量断裂预测。')
    if not fracture['quasistatic_screen_passed']:
        warnings.append('断裂前能量或两端反力筛查未通过，请减慢加载并复算。')
    if not fracture['fracture_confirmed']:
        warnings.append('目标加载已完成，但未通过完整断裂检查；不得把此曲线称为完整拉断曲线。')
    np.savetxt(output/'force_displacement.csv', curve, delimiter=',', fmt='%.16g')
    # Reload the exported values so existing cross-plot provenance checks are exact.
    curve = np.loadtxt(output/'force_displacement.csv', delimiter=',', ndmin=2)
    np.savetxt(output/'damage_history.csv', np.column_stack((times, damage.max(axis=1), deleted,
               a['element_solid_effective_plastic_strain'].max(axis=(1, 2)))), delimiter=',',
               header='time_s,max_native_damage,deleted_elements,max_effective_plastic_strain', comments='')
    np.savetxt(output/'energy_history.csv', np.column_stack((gt, ie, ke, de)), delimiter=',',
               header='time_s,internal_energy_Nmm,kinetic_energy_Nmm,numerical_damping_energy_Nmm', comments='')
    _atomic_json(output/'fracture_report.json', fracture)
    plots = render_fracture_plots(output, nodes, a, curve, damage, alive, peak, before, calibrated)
    files = ['force_displacement.csv', 'damage_history.csv', 'energy_history.csv', 'fracture_report.json',
             'd3hsp', 'lsdyna.log', 'mapdl_execution.json']+plots
    return dict(solve_state='solved', curve=curve.tolist(), point_count=len(curve), solver_type='ls-dyna',
                final_displacement_mm=float(applied[-1]), final_load_n=float(force[-1]),
                engineering_strain=float(curve[-1, 4]), nominal_stress_mpa=float(curve[-1, 5]),
                validation_state='native_binary_cross_checked', warnings=warnings,
                checks=dict(target_time=True, target_displacement=True, native_geometry=True),
                fracture=fracture, curve_plot=dict(state='completed', file='load_displacement.png'),
                stress_strain_plot=dict(state='completed', file='engineering_stress_strain.png'),
                contour_plots=dict(state='completed', plots=[dict(file='fracture_snapshots.png', title='颈缩与断裂 · 原生网格变形')], files=plots),
                files=files)


def render_fracture_plots(output, nodes, arrays, curve, damage, alive, peak, before, calibrated):
    import matplotlib
    matplotlib.use('Agg')
    from matplotlib import pyplot as plt
    from matplotlib.ticker import MaxNLocator
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    label = 'User-supplied parameters' if calibrated else 'EXAMPLE parameters - not calibrated'
    for filename, x, y, xlabel, ylabel in (
            ('load_displacement.png', curve[:, 1], curve[:, 2], 'Applied displacement (mm)', 'Tensile force (N)'),
            ('engineering_stress_strain.png', curve[:, 4]*100, curve[:, 5], 'Engineering strain (%)', 'Nominal stress (MPa)')):
        fig, ax = plt.subplots(figsize=(8, 4.5), constrained_layout=True)
        ax.plot(x, y, color='#9b382d', lw=1.8)
        ax.scatter([x[peak]], [y[peak]], color='#263c54', zorder=3)
        ax.set(xlabel=xlabel, ylabel=ylabel, title='LS-DYNA / MAT024 + GISSMO\n'+label)
        ax.grid(alpha=.2)
        fig.savefig(output/filename, dpi=160)
        plt.close(fig)
    conn = arrays['element_solid_node_indexes']
    faces = np.array([[0,1,2,3],[4,5,6,7],[0,1,5,4],[1,2,6,5],[2,3,7,6],[3,0,4,7]])
    fig = plt.figure(figsize=(13, 8), constrained_layout=True)
    for panel, (step, title) in enumerate([(0,'Initial'), (peak,'Peak load'), (before,'Before first deletion'), (len(curve)-1,'Final')], 1):
        ax = fig.add_subplot(2, 2, panel, projection='3d')
        live = np.flatnonzero(alive[step])
        all_faces = conn[live][:, faces].reshape(-1, 4)
        _, unique, counts = np.unique(np.sort(all_faces, axis=1), axis=0, return_index=True, return_counts=True)
        outside = unique[counts == 1]
        # Plot sampling changes only the preview, never the model or binary results.
        outside = outside[::max(1, len(outside)//12000)]
        coords = nodes[:, 1:]+arrays['node_displacement'][step]
        poly = Poly3DCollection(coords[all_faces[outside]], linewidth=.12, edgecolors='#555555')
        color = damage[step, live][outside//6]
        poly.set_facecolor(plt.cm.magma(np.clip(color, 0, 1)))
        ax.add_collection3d(poly)
        ax.auto_scale_xyz(coords[:, 0], coords[:, 1], coords[:, 2])
        ax.set_box_aspect(np.maximum(np.ptp(coords, axis=0), .01))
        ax.set(xlabel='X (mm)', ylabel='Y (mm)', zlabel='Z (mm)', title=f'{title} | t={arrays["timesteps"][step]:.5g} s')
        for direction in (ax.xaxis, ax.yaxis, ax.zaxis):
            direction.set_major_locator(MaxNLocator(3))
        ax.tick_params(labelsize=8, pad=0)
        ax.view_init(elev=24, azim=-65)
    fig.suptitle('True deformation scale / native GISSMO damage (0 to 1)\n'+label)
    fig.savefig(output/'fracture_snapshots.png', dpi=150)
    plt.close(fig)
    return ['load_displacement.png', 'engineering_stress_strain.png', 'fracture_snapshots.png']

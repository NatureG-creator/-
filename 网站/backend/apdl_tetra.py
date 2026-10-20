"""Conforming six-tetra split of each sampled height-field cell.

One global body diagonal gives matching triangles on every shared face.
The resulting piecewise planar boundary retains every source coordinate.
SOLID187 midside order is IJ, JK, KI, IL, JL, KL.
"""
from __future__ import annotations

import time

import numpy as np


def build_tetra_mesh(nodes, nx, ny, layers, dx, dy, *, quadratic,
                     max_nodes, max_elements):
    started = time.perf_counter()
    plane = nx*ny
    base = np.arange(plane).reshape(ny,nx)[:-1,:-1].ravel()
    lower = np.column_stack((base,base+1,base+nx+1,base+nx))
    split = np.array(((0,1,2,6),(0,2,3,6),(0,3,7,6),
                      (0,7,4,6),(0,4,5,6),(0,5,1,6)))
    if len(base)*layers*6 > max_elements:
        raise ValueError(f'四面体单元 {len(base)*layers*6} 超过上限 {max_elements}；未降采样或降阶。')
    blocks = []
    for layer in range(layers):
        corners = np.column_stack((lower+layer*plane,lower+(layer+1)*plane))
        blocks.append(corners[:,split].reshape(-1,4))
    tets = np.concatenate(blocks)
    xyz = nodes[:,1:]
    volumes = np.empty(len(tets))
    for start in range(0,len(tets),20000):
        p = xyz[tets[start:start+20000]]
        volumes[start:start+len(p)] = np.linalg.det(p[:,1:]-p[:,:1])/6
    if not np.all(np.isfinite(volumes)) or np.any(volumes <= 0):
        raise ValueError('四面体含非正体积，拒绝单独翻转节点掩盖错误。')
    remaining = (xyz[-plane:,2]-xyz[:plane,2]).reshape(ny,nx)
    expected = dx*dy/6*np.sum(2*remaining[:-1,:-1]+remaining[:-1,1:]
                             +2*remaining[1:,1:]+remaining[1:,:-1])
    volume = float(volumes.sum())
    mismatch = abs(volume-expected)/expected
    if mismatch > 1e-10:
        raise ValueError('四面体体积与封闭三角形表面不守恒。')
    if quadratic:
        order = ((0,1),(1,2),(2,0),(0,3),(1,3),(2,3))
        edges = np.sort(np.stack([tets[:,ids] for ids in order],axis=1),axis=2)
        unique_edges,inverse = np.unique(edges.reshape(-1,2),axis=0,return_inverse=True)
        if len(xyz)+len(unique_edges) > max_nodes:
            raise ValueError(f'SOLID187 共 {len(xyz)+len(unique_edges)} 节点，超过上限 {max_nodes}；未自动降阶。')
        mids = xyz[unique_edges].mean(axis=1)
        connectivity = np.column_stack((tets,inverse.reshape(-1,6)+len(xyz)))+1
        xyz = np.concatenate((xyz,mids))
    else:
        connectivity = tets+1
    if len(xyz) > max_nodes:
        raise ValueError(f'四面体节点 {len(xyz)} 超过上限 {max_nodes}。')
    rows = np.column_stack((np.arange(1,len(xyz)+1),xyz))
    elements = np.column_stack((np.arange(1,len(tets)+1),connectivity))
    return rows,elements,dict(positive_tetra_count=len(tets),negative_tetra_count=0,
        min_tetra_volume_mm3=float(volumes.min()),actual_mesh_volume_mm3=volume,
        tetra_volume_mismatch_fraction=mismatch,source_boundary_node_count=2*plane,
        meshing_seconds=time.perf_counter()-started,
        mesh_algorithm='conforming six-tetra split; global (00,11) diagonal',
        surface_discretization='fixed diagonal (00,11); piecewise planar triangles')

import time

import numpy as np

from corrosion_sim import Block, block_process, init_taichi, jixiantiqu_3d, moving_avg_3d, split_uniform_blocks


# 对应 CA_single4.m。请把 perfect_parameter 改成你的最优参数数组。
F = 5000
w = 800
l = 1120
n = 100
space = 25
stage_number = 1

use_parallel = False
use_taichi = True
load_external_data = False

if use_taichi:
    init_taichi("gpu")

perfect_parameter = np.array([0.1, 0.5, 0.001, 20, 10, 0.02, 10, 0.1, 0.1, 5], dtype=float)
XY = perfect_parameter

data_x = 456
data = np.array([456, 100, 1.86, 5.74, 0.63, 0.27], dtype=float)

if load_external_data:
    raise NotImplementedError("请在这里载入外部 a / d / CL_concentration，例如 np.load 或 scipy.io.loadmat。")
else:
    print("使用默认初始化")
    a = np.zeros((w, l, n + 1), dtype=np.int8)
    a[:, :, 1:] = 1
    d = np.ones((w, l, n + 1), dtype=np.int8) * 3
    CL_concentration = np.zeros((w, l), dtype=float)
    rng = np.random.default_rng()
    s_p = rng.integers(0, w * l * n, size=int(round(w * l * n * XY[5])))
    full_d = np.ones((w, l, n), dtype=np.int8) * 3
    full_d[np.unravel_index(s_p, full_d.shape)] = 1
    d[:, :, 1:] = full_d

block_coords = split_uniform_blocks(w, l, num_blocks=5)
blocks = []
for x1, x2, y1, y2 in block_coords:
    blocks.append(Block(a=a[x1:x2, y1:y2, :].copy(), d=d[x1:x2, y1:y2, :].copy(), cl=CL_concentration[x1:x2, y1:y2].copy()))

del a, d, CL_concentration

p_uniform_base, p_passive_base, p_break, CL_threshold = XY[:4]
alpha_corrosion = XY[4]
alpha_passive = 0.8
alpha_p_break = XY[6]
p_h, p_v, p_o = XY[7], XY[8], XY[9]
K0 = 0
beta = 1

print("=========================================")
print("           腐蚀模拟开始迭代")
print("=========================================")
start = time.time()
rng = np.random.default_rng()

Average_depth = 0.0
for k in range(1, F + 1):
    for b in range(len(blocks)):
        blocks[b] = block_process(
            blocks[b],
            k,
            n,
            p_uniform_base,
            p_passive_base,
            p_break,
            CL_threshold,
            alpha_corrosion,
            alpha_passive,
            alpha_p_break,
            p_h,
            p_v,
            p_o,
            K0,
            beta,
            stage_number,
            rng,
            use_taichi=use_taichi,
        )

    total_metal = sum(np.sum(block.a == 1) for block in blocks)
    quality_loss = (w * l * n - total_metal) / (w * l * n)
    Average_depth = quality_loss * n * space
    elapsed = time.time() - start
    est = elapsed / k * (F - k) if k > 1 else 0
    print(f"迭代: {k:4d}/{F:4d} | 进度: {k / F * 100:5.1f}% | 已用: {elapsed:6.1f}s | 剩余预估: {est:6.1f}s | 平均腐蚀深度: {Average_depth:.2f}")
    if data_x - Average_depth <= 0:
        print("已达到目标深度，提前终止。")
        break

full_a = np.zeros((w, l, n + 1), dtype=np.int8)
full_d = np.zeros((w, l, n + 1), dtype=np.int8)
full_CL = np.zeros((w, l), dtype=float)
for block, (x1, x2, y1, y2) in zip(blocks, block_coords):
    full_a[x1:x2, y1:y2, :] = block.a
    full_d[x1:x2, y1:y2, :] = block.d
    full_CL[x1:x2, y1:y2] = block.cl

baseline, _, _, depth_map = moving_avg_3d(full_a, 11, w, l, n)
jicha = baseline.max() - baseline.min()
bj_depth = np.mean(depth_map - depth_map.min()) * space
if jicha < 3:
    yuzhi, scale = 0.3, 15
elif jicha < 5:
    yuzhi, scale = 0.4, 20
else:
    yuzhi, scale = 0.5, 25

params = {"MinProminence": 0.05, "MinDistance": 15, "Neighborhood": [scale, scale]}
shengdu, sjb, *_ = jixiantiqu_3d(baseline, n, params, yuzhi)
shengdu = np.log(np.maximum(shengdu * space, np.finfo(float).eps))
sjb = sjb / 10
jsb = np.log(1 / np.maximum(sjb, np.finfo(float).eps))
sigma1 = np.std(jsb, ddof=1) if jsb.size > 1 else 0.0
sigma2 = np.std(shengdu, ddof=1) if shengdu.size > 1 else 0.0
CS = (np.array([Average_depth, bj_depth, np.mean(jsb), np.mean(shengdu), sigma1, sigma2]) - data) / data

np.savez_compressed("ca_single4_result.npz", a=full_a, d=full_d, CL_concentration=full_CL, baseline=baseline, depth_map=depth_map, CS=CS)
print(f"迭代完成，总耗时：{time.time() - start:.2f} 秒")
print("CS =", CS)

import numpy as np

from corrosion_sim import Block, block_process, init_taichi


def main():
    ok = init_taichi("cpu")
    w, l, n = 8, 8, 5
    a = np.zeros((w, l, n + 1), dtype=np.int8)
    a[:, :, 1:] = 1
    d = np.ones_like(a, dtype=np.int8) * 3
    cl = np.zeros((w, l), dtype=float)
    block = Block(a=a, d=d, cl=cl)
    out = block_process(
        block,
        1,
        n,
        0.8,
        0.1,
        0.01,
        10,
        2,
        0.8,
        2,
        0.1,
        0.1,
        2,
        0,
        1,
        1,
        np.random.default_rng(1),
        use_taichi=True,
    )
    print("taichi_enabled =", ok)
    print("a_shape =", out.a.shape)
    print("zero_count =", int((out.a == 0).sum()))


if __name__ == "__main__":
    main()

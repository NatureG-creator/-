import numpy as np

try:
    import taichi as ti
except Exception:  # pragma: no cover
    ti = None


_INITIALIZED = False
_KERNEL = None


def _build_kernel():
    @ti.kernel
    def boundary_update_kernel(
        boundary: ti.types.ndarray(dtype=ti.i32, ndim=2),
        rand_uniform: ti.types.ndarray(dtype=ti.f32, ndim=1),
        rand_break: ti.types.ndarray(dtype=ti.f32, ndim=1),
        a: ti.types.ndarray(dtype=ti.i32, ndim=3),
        d: ti.types.ndarray(dtype=ti.i32, ndim=3),
        cl: ti.types.ndarray(dtype=ti.f32, ndim=2),
        break_points: ti.types.ndarray(dtype=ti.i32, ndim=2),
        break_count: ti.types.ndarray(dtype=ti.i32, ndim=1),
        p_uniform_base: ti.f32,
        p_passive_base: ti.f32,
        p_break: ti.f32,
        cl_threshold: ti.f32,
        alpha_corrosion: ti.f32,
        alpha_passive: ti.f32,
        alpha_p_break: ti.f32,
        stage_number: ti.i32,
        decay_factor: ti.f32,
        n_boundary: ti.i32,
    ):
        for i in range(n_boundary):
            x = boundary[i, 0]
            y = boundary[i, 1]
            z = boundary[i, 2]
            av = a[x, y, z]
            if av != 0:
                dv = d[x, y, z]
                cl_factor = cl[x, y] / cl_threshold
                if av == 1:
                    p_uniform = p_uniform_base * (1.0 + alpha_corrosion * cl_factor) * decay_factor
                    p_passive = p_passive_base * (1.0 - alpha_passive * cl_factor)
                    if rand_uniform[i] < p_uniform:
                        if dv > 1:
                            d[x, y, z] = dv - 1
                        else:
                            a[x, y, z] = 0
                    elif rand_uniform[i] < p_passive:
                        a[x, y, z] = 2
                elif av == 2 and dv == 1:
                    pbr = p_break * (1.0 + alpha_p_break * cl_factor)
                    if stage_number == 1:
                        pbr = pbr * (1.0 + alpha_p_break * cl_factor)
                    if rand_break[i] < pbr:
                        a[x, y, z] = 0
                        nv = cl[x, y] + 1.0
                        if nv > cl_threshold:
                            nv = cl_threshold
                        cl[x, y] = nv
                        pos = ti.atomic_add(break_count[0], 1)
                        break_points[pos, 0] = x
                        break_points[pos, 1] = y
                        break_points[pos, 2] = z

    return boundary_update_kernel


def init_taichi_accel(arch: str = "gpu") -> bool:
    global _INITIALIZED, _KERNEL
    if ti is None:
        return False
    if _INITIALIZED:
        return True
    try:
        backend = ti.gpu if arch.lower() == "gpu" else ti.cpu
        ti.init(arch=backend, default_fp=ti.f32, default_ip=ti.i32)
    except Exception:
        try:
            ti.init(arch=ti.cpu, default_fp=ti.f32, default_ip=ti.i32)
        except Exception:
            return False
    _KERNEL = _build_kernel()
    _INITIALIZED = True
    return True


def boundary_update_taichi(
    boundary: np.ndarray,
    a: np.ndarray,
    d: np.ndarray,
    cl: np.ndarray,
    p_uniform_base: float,
    p_passive_base: float,
    p_break: float,
    cl_threshold: float,
    alpha_corrosion: float,
    alpha_passive: float,
    alpha_p_break: float,
    stage_number: int,
    decay_factor: float,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    if ti is None or not _INITIALIZED or _KERNEL is None or boundary.size == 0:
        return a, d, cl, np.empty((0, 3), dtype=np.int32)

    boundary_i32 = np.ascontiguousarray(boundary.astype(np.int32, copy=False))
    a_i32 = np.ascontiguousarray(a.astype(np.int32, copy=False))
    d_i32 = np.ascontiguousarray(d.astype(np.int32, copy=False))
    cl_f32 = np.ascontiguousarray(cl.astype(np.float32, copy=False))
    n_boundary = boundary_i32.shape[0]
    rand_uniform = rng.random(n_boundary).astype(np.float32)
    rand_break = rng.random(n_boundary).astype(np.float32)
    break_points = np.zeros((n_boundary, 3), dtype=np.int32)
    break_count = np.zeros(1, dtype=np.int32)

    _KERNEL(
        boundary_i32,
        rand_uniform,
        rand_break,
        a_i32,
        d_i32,
        cl_f32,
        break_points,
        break_count,
        float(p_uniform_base),
        float(p_passive_base),
        float(p_break),
        float(cl_threshold),
        float(alpha_corrosion),
        float(alpha_passive),
        float(alpha_p_break),
        int(stage_number),
        float(decay_factor),
        int(n_boundary),
    )

    a[...] = a_i32.astype(a.dtype, copy=False)
    d[...] = d_i32.astype(d.dtype, copy=False)
    cl[...] = cl_f32.astype(cl.dtype, copy=False)
    return a, d, cl, break_points[: int(break_count[0])]

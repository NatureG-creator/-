"""Optional Taichi acceleration for boundary detection and boundary-cell updates.

The accelerated path mirrors `python_converted/taichi_accel.py`. It only
handles the vectorized boundary update; chloride-driven spread and all
post-processing remain in NumPy/SciPy for MATLAB compatibility.
"""

import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np


def _try_add_bundled_taichi_path() -> bool:
    """Add the bundled Codex Python dependency path when local env lacks Taichi."""
    candidates: list[Path] = []
    env_path = os.environ.get("CODEX_PYTHON_DEPS")
    if env_path:
        candidates.append(Path(env_path))
    candidates.append(
        Path(r"C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python")
    )
    for candidate in candidates:
        if candidate.exists() and str(candidate) not in sys.path:
            sys.path.insert(0, str(candidate))
            return True
    return False


try:  # pragma: no cover - availability depends on the local environment.
    import taichi as ti
except Exception:  # pragma: no cover
    if _try_add_bundled_taichi_path():
        try:
            import taichi as ti
        except Exception:
            ti = None
    else:
        ti = None


_INITIALIZED = False
_BOUNDARY_UPDATE_KERNEL = None
_BOUNDARY_MASK_KERNEL = None
_LAST_INIT_ERROR: str | None = None


@dataclass
class TaichiCAState:
    """CA 内复用整型状态；氯离子保留 float64，不降低扩散计算精度。"""

    a: np.ndarray
    d: np.ndarray
    cl: np.ndarray

    @classmethod
    def from_arrays(cls, a, d, cl):
        # d 允许用户输入非整数。只有整数值且在 int32 范围内才持久转为整型。
        limit = np.iinfo(np.int32)
        compatible = all(np.all(np.isfinite(value)) and
                         np.all(value == np.trunc(value)) and
                         np.all((value >= limit.min) & (value <= limit.max))
                         for value in (a, d))
        if not compatible:
            return cls(a, d, cl)
        return cls(np.ascontiguousarray(a, dtype=np.int32),
                   np.ascontiguousarray(d, dtype=np.int32), cl)


def _build_kernels():
    @ti.kernel
    def boundary_update_kernel(
        boundary: ti.types.ndarray(dtype=ti.i32, ndim=2),
        convex_flags: ti.types.ndarray(dtype=ti.i32, ndim=1),
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
        convex_multiplier: ti.f32,
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
                    if convex_flags[i] != 0:
                        pbr = pbr * convex_multiplier
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

    @ti.kernel
    def boundary_mask_kernel(
        a: ti.types.ndarray(dtype=ti.i32, ndim=3),
        boundary_mask: ti.types.ndarray(dtype=ti.i32, ndim=3),
        w: ti.i32,
        l: ti.i32,
        d: ti.i32,
    ):
        for x, y, z in ti.ndrange(w, l, d):
            boundary_mask[x, y, z] = 0
            if a[x, y, z] != 0:
                hit = 0
                if z > 0 and a[x, y, z - 1] == 0:
                    hit = 1
                elif z + 1 < d and a[x, y, z + 1] == 0:
                    hit = 1
                elif y > 0 and a[x, y - 1, z] == 0:
                    hit = 1
                elif y + 1 < l and a[x, y + 1, z] == 0:
                    hit = 1
                elif x > 0 and a[x - 1, y, z] == 0:
                    hit = 1
                elif x + 1 < w and a[x + 1, y, z] == 0:
                    hit = 1
                boundary_mask[x, y, z] = hit

    return boundary_update_kernel, boundary_mask_kernel


def init_taichi(arch: str = "cpu") -> bool:
    """Enable Taichi acceleration; return `False` when unavailable.

    Taichi仅使用CPU架构。
    """
    global _INITIALIZED, _BOUNDARY_UPDATE_KERNEL, _BOUNDARY_MASK_KERNEL, _LAST_INIT_ERROR
    if arch.lower() != "cpu":
        _LAST_INIT_ERROR = "当前仅允许 Taichi CPU 架构"
        return False
    if ti is None:
        _LAST_INIT_ERROR = "taichi package is not importable in the current interpreter"
        return False
    if _INITIALIZED:
        return True
    cache_dir = Path(tempfile.gettempdir()) / f"corrosion_taichi_cache_{os.getpid()}"
    cache_dir.mkdir(parents=True, exist_ok=True)
    try:  # pragma: no cover - hardware/backend dependent.
        ti.init(
            arch=ti.cpu,
            default_fp=ti.f32,
            default_ip=ti.i32,
            offline_cache=False,
            offline_cache_file_path=str(cache_dir),
        )
    except Exception as exc:
        _LAST_INIT_ERROR = f"taichi.init() failed for requested backend: {exc!r}"
        return False
    try:
        _BOUNDARY_UPDATE_KERNEL, _BOUNDARY_MASK_KERNEL = _build_kernels()
    except Exception as exc:
        _LAST_INIT_ERROR = f"building Taichi kernels failed: {exc!r}"
        _BOUNDARY_UPDATE_KERNEL = None
        _BOUNDARY_MASK_KERNEL = None
        _INITIALIZED = False
        return False
    _INITIALIZED = True
    _LAST_INIT_ERROR = None
    return True


def taichi_available() -> bool:
    """Return whether Taichi is imported and initialized for acceleration."""
    return (
        ti is not None
        and _INITIALIZED
        and _BOUNDARY_UPDATE_KERNEL is not None
        and _BOUNDARY_MASK_KERNEL is not None
    )


def taichi_last_error() -> str | None:
    """Return the last Taichi initialization failure reason, if any."""
    return _LAST_INIT_ERROR


def detect_boundary_taichi(a: np.ndarray, n: int) -> np.ndarray:
    """Taichi-accelerated boundary detection returning MATLAB 1-based coords."""
    if not taichi_available():
        return np.empty((0, 3), dtype=np.int64)
    a = np.asarray(a)
    if a.ndim != 3:
        raise ValueError("输入 a 必须是三维数组")
    if n < 1:
        raise ValueError("n 必须是正数")
    if not np.any(a == 0):
        return np.empty((0, 3), dtype=np.int64)

    zero_mask = a == 0
    z_has_zero = np.any(zero_mask, axis=(0, 1))
    z_nonzero = np.flatnonzero(z_has_zero)
    if z_nonzero.size == 0:
        return np.empty((0, 3), dtype=np.int64)
    jizhun_z_0based = min(int(z_nonzero[-1]) + 1, n)
    process_depth = min(jizhun_z_0based + 1, a.shape[2])

    a_process = np.ascontiguousarray(a[:, :, :process_depth].astype(np.int32, copy=False))
    boundary_mask = np.zeros_like(a_process, dtype=np.int32)
    w, l, d = a_process.shape
    _BOUNDARY_MASK_KERNEL(a_process, boundary_mask, int(w), int(l), int(d))
    coords_0based = np.argwhere(boundary_mask != 0)
    return coords_0based.astype(np.int64) + 1


def boundary_update_taichi(
    boundary_zero_based: np.ndarray,
    convex_flags: np.ndarray,
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
    convex_multiplier: float,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Run the Taichi boundary update.

    可调项：`boundary_zero_based`、`a`、`d`、`cl`、`p_uniform_base`、
    `p_passive_base`、`p_break`、`cl_threshold`、`alpha_corrosion`、
    `alpha_passive`、`alpha_p_break`、`stage_number`、`decay_factor`、`rng`。

    `boundary_zero_based` must be Python 0-based coordinates, unlike the public
    CA helpers that expose MATLAB 1-based coordinates.
    """
    if not taichi_available() or boundary_zero_based.size == 0:
        return a, d, cl, np.empty((0, 3), dtype=np.int32)
    boundary_i32 = np.ascontiguousarray(boundary_zero_based.astype(np.int32, copy=False))
    convex_i32 = np.ascontiguousarray(convex_flags.astype(np.int32, copy=False))
    a_i32 = np.ascontiguousarray(a.astype(np.int32, copy=False))
    d_i32 = np.ascontiguousarray(d.astype(np.int32, copy=False))
    cl_f32 = np.ascontiguousarray(cl.astype(np.float32, copy=False))
    n_boundary = boundary_i32.shape[0]
    rand_uniform = rng.random(n_boundary).astype(np.float32)
    rand_break = rng.random(n_boundary).astype(np.float32)
    break_points = np.zeros((n_boundary, 3), dtype=np.int32)
    break_count = np.zeros(1, dtype=np.int32)

    _BOUNDARY_UPDATE_KERNEL(
        boundary_i32,
        convex_i32,
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
        float(convex_multiplier),
        int(n_boundary),
    )

    # CA 已持有兼容缓冲区时 kernel 直接写入；避免每次将整块状态复制回自身。
    if not np.shares_memory(a, a_i32):
        a[...] = a_i32
    if not np.shares_memory(d, d_i32):
        d[...] = d_i32
    cl[...] = cl_f32.astype(cl.dtype, copy=False)
    return a, d, cl, break_points[: int(break_count[0])]

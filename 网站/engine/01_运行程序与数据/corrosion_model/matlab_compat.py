"""MATLAB compatibility helpers used by the converted corrosion model."""

from __future__ import annotations

import numpy as np


def matlab_round(values):
    """Round like MATLAB `round`, where halves are rounded away from zero."""
    arr = np.asarray(values)
    rounded = np.where(arr >= 0, np.floor(arr + 0.5), np.ceil(arr - 0.5))
    if np.isscalar(values):
        return rounded.item()
    return rounded.astype(np.int64)


def sub2ind_matlab(shape: tuple[int, ...], subs_1based: np.ndarray) -> np.ndarray:
    """Convert MATLAB 1-based subscripts to MATLAB 1-based linear indices.

    MATLAB stores arrays in column-major order and starts indexing at 1.
    Python/NumPy normally uses 0-based indices; this helper keeps the MATLAB
    convention at the function boundary so every conversion is explicit.
    """
    subs = np.asarray(subs_1based, dtype=np.int64)
    if subs.ndim == 1:
        subs = subs.reshape(1, -1)
    if subs.shape[1] != len(shape):
        raise ValueError("subscript column count must match array dimensions")
    zero_based = subs - 1  # 索引改动：MATLAB 1-based -> Python 0-based。
    multipliers = np.array([1, *np.cumprod(shape[:-1])], dtype=np.int64)
    return zero_based @ multipliers + 1  # 返回 MATLAB 风格 1-based 线性索引。


def ind2sub_matlab(shape: tuple[int, ...], linear_1based: np.ndarray) -> np.ndarray:
    """Convert MATLAB 1-based linear indices to MATLAB 1-based subscripts."""
    idx = np.asarray(linear_1based, dtype=np.int64) - 1  # 1-based -> 0-based。
    flat = idx.reshape(-1)
    cols = []
    for dim in shape:
        cols.append((flat % dim) + 1)  # 转回 MATLAB 1-based 子脚标。
        flat = flat // dim
    result = np.stack(cols, axis=-1)
    return result.reshape(idx.shape + (len(shape),))


def take_matlab_linear(array: np.ndarray, linear_1based: np.ndarray) -> np.ndarray:
    """Read `array(linear_index)` using MATLAB column-major linear indexing."""
    zero_based = np.asarray(linear_1based, dtype=np.int64) - 1
    subs = np.unravel_index(zero_based, array.shape, order="F")
    return array[subs]


def put_matlab_linear(array: np.ndarray, linear_1based: np.ndarray, values) -> None:
    """Assign `array(linear_index)=values` using MATLAB column-major indexing."""
    zero_based = np.asarray(linear_1based, dtype=np.int64) - 1
    subs = np.unravel_index(zero_based, array.shape, order="F")
    array[subs] = values


def matlab_slice(start_1based: int, stop_1based_inclusive: int) -> slice:
    """Return a Python slice equivalent to MATLAB `start:stop`."""
    return slice(start_1based - 1, stop_1based_inclusive)

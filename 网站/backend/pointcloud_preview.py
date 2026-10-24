"""Grid-preserving previews for processed point-cloud surfaces."""

from __future__ import annotations

import math

import numpy as np


def grid_preview(x: np.ndarray, y: np.ndarray, height: np.ndarray,
                 depth: np.ndarray | None = None, max_points: int = 2500) -> tuple[np.ndarray, np.ndarray | None]:
    """Sample a height grid by rows and columns, preserving its 2-D layout."""
    rows, columns = height.shape
    target = max(1, min(int(max_points), rows * columns))
    aspect = rows / columns
    preview_rows = max(1, min(rows, round(math.sqrt(target * aspect))))
    preview_columns = max(1, min(columns, target // preview_rows))
    row_indices = np.unique(np.linspace(0, rows - 1, preview_rows, dtype=int))
    column_indices = np.unique(np.linspace(0, columns - 1, preview_columns, dtype=int))
    sampled_height = height[np.ix_(row_indices, column_indices)]
    xx, yy = np.meshgrid(x[column_indices], y[row_indices])
    xyz = np.column_stack((xx.ravel(), yy.ravel(), sampled_height.ravel()))
    sampled_depth = None if depth is None else depth[np.ix_(row_indices, column_indices)].ravel()
    return xyz, sampled_depth

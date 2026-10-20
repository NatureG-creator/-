"""Executor lifetime and input helpers; scientific code stays untouched."""
from contextlib import nullcontext
import multiprocessing
import numpy as np

class ExecutorScope:
    def __init__(self, executor, policy):
        if policy not in ('persistent', 'recreate'):
            raise ValueError('pool_policy 必须是 persistent 或 recreate')
        self.executor, self.policy, self.pool = executor, policy, None

    def __call__(self, **kwargs):
        kwargs['mp_context'] = multiprocessing.get_context('spawn')
        if self.policy == 'recreate':
            return self.executor(**kwargs)
        if self.pool is None:
            self.pool = self.executor(**kwargs)
        return nullcontext(self.pool)

    def close(self):
        if self.pool is not None:
            self.pool.shutdown(wait=True, cancel_futures=True)
            self.pool = None

def load_initial_state(path, w, l, n):
    if path is None:
        return None, None, None
    with np.load(path, allow_pickle=False) as data:
        states = tuple(np.array(data[key], copy=True) for key in ('perfect_a','perfect_d','perfect_cl'))
    for value, shape in zip(states, ((w,l,n+1),(w,l,n+1),(w,l))):
        if value.shape != shape:
            raise ValueError(f'初始快照 shape 错误：期望 {shape}，实际 {value.shape}')
        if not np.all(np.isfinite(value)):
            raise ValueError('初始快照包含非有限数值')
    return states

def sample_statistics(samples):
    values = np.asarray(samples, dtype=float)
    if not values.size:
        raise ValueError('至少需要一个测速样本')
    q1, median, q3 = np.percentile(values, [25,50,75])
    return dict(median_seconds=float(median), min_seconds=float(values.min()),
                max_seconds=float(values.max()), q1_seconds=float(q1), q3_seconds=float(q3),
                iqr_seconds=float(q3-q1), variation_ratio=float((q3-q1)/median) if median else 0.,
                sample_count=len(values), low_sample_warning=len(values)<5)

def compare_snapshot(reference, arrays):
    """Load one reference array at a time, limiting extra resident population states."""
    rows = {}
    with np.load(reference, allow_pickle=False) as stored:
        for key in arrays:
            a, b = stored[key], arrays[key]
            shape = a.shape == b.shape
            finite = bool(np.isfinite(a).all() and np.isfinite(b).all())
            exact = bool(shape and finite and np.array_equal(a,b))
            close = bool(shape and finite and np.allclose(a,b,rtol=1e-7,atol=1e-9))
            delta = a.astype(float)-b.astype(float) if shape and finite else None
            rows[key] = dict(exact=exact,within_tolerance=close,shape_match=shape,
                mismatch_count=int(np.count_nonzero(a != b)) if shape else None,
                max_abs_diff=None if delta is None else float(np.max(np.abs(delta))),
                rmse=None if delta is None else float(np.sqrt(np.mean(delta*delta))))
    return dict(exact=all(row['exact'] for row in rows.values()),
                within_tolerance=all(row['within_tolerance'] for row in rows.values()),
                rtol=1e-7,atol=1e-9,arrays=rows)

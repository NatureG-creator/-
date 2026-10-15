import tempfile
import unittest
from pathlib import Path
import numpy as np

from backend.benchmark_pool import ExecutorScope, load_initial_state, sample_statistics

class ExecutionTests(unittest.TestCase):
    def test_statistics(self):
        result = sample_statistics([1., 2., 3., 4.])
        self.assertEqual(result['q1_seconds'], 1.75)
        self.assertEqual(result['iqr_seconds'], 1.5)
        self.assertEqual(result['sample_count'], 4)

    def test_snapshot_shapes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'state.npz'
            np.savez(path, perfect_a=np.zeros((5,6,5)), perfect_d=np.zeros((5,6,5)), perfect_cl=np.zeros((5,6)))
            self.assertEqual(load_initial_state(path,5,6,4)[0].shape,(5,6,5))
            with self.assertRaises(ValueError):
                load_initial_state(path,4,6,4)

    def test_pool_reused_and_closed_after_exception(self):
        made = []
        class Fake:
            def __init__(self, **kwargs): made.append(self); self.closed=False
            def shutdown(self, wait=True, cancel_futures=False): self.closed=True
        scope = ExecutorScope(Fake, 'persistent')
        try:
            with scope(max_workers=2) as first:
                pass
            with scope(max_workers=2) as second:
                self.assertIs(first, second)
                raise RuntimeError('test')
        except RuntimeError:
            pass
        finally:
            scope.close()
        self.assertEqual(len(made),1)
        self.assertTrue(made[0].closed)

class RealTinyExecutionTests(unittest.TestCase):
    def test_numpy_workloads(self):
        from backend.config import default_simulation_config
        from backend.benchmark import prepare_benchmark
        from backend.benchmark_trial import run_trial
        value = dict(config=default_simulation_config(),targets=[[100,20,2,4,.6,.3]],options=dict(
            grid_w=5,grid_l=6,grid_n=4,steps=3,population=2,workers=2,repeats=1,seed=8,
            timeout_seconds=120,target_index=0,modes=['numpy_serial']))
        spec = prepare_benchmark(value)
        for workload in ('population','short_ga'):
            spec['options'].update(workload=workload,generations=1,selected_count=1,pool_policy='persistent',cpu_budget=2)
            with tempfile.TemporaryDirectory() as directory:
                report = run_trial(spec,'numpy_serial',Path(directory))
                self.assertEqual(report['state'],'completed')
                self.assertTrue(report['repeat_exact'])
                self.assertEqual(report['sample_count'],1)
                with np.load(Path(directory)/'arrays.npz') as data:
                    self.assertEqual(data['objv'].shape,(2,6) if workload=='population' else (4,))




    def test_parallel_pool_policies_and_snapshot(self):
        from backend.config import default_simulation_config
        from backend.benchmark import prepare_benchmark
        from backend.benchmark_trial import run_trial
        value = dict(config=default_simulation_config(),targets=[[100,20,2,4,.6,.3]],options=dict(
            grid_w=5,grid_l=6,grid_n=4,steps=3,population=2,workers=2,repeats=1,seed=8,
            timeout_seconds=120,target_index=0,modes=['numpy_serial','numpy_parallel']))
        spec = prepare_benchmark(value)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_trial(spec,'numpy_serial',root/'source')
            with np.load(root/'source'/'arrays.npz') as data:
                np.savez(root/'snapshot.npz',perfect_a=data['a'][0],perfect_d=data['d'][0],perfect_cl=data['cl'][0])
            spec.update(initial_state_path=str(root/'snapshot.npz'),stage_number=2)
            for workload in ('population','short_ga'):
                reports=[]
                for policy in ('recreate','persistent'):
                    spec['options'].update(workload=workload,generations=3,selected_count=1,pool_policy=policy,cpu_budget=2)
                    result=run_trial(spec,'numpy_parallel',root/(workload+policy))
                    self.assertTrue(result['repeat_exact'])
                    reports.append(result)
                with np.load(root/(workload+'recreate')/'arrays.npz') as left, np.load(root/(workload+'persistent')/'arrays.npz') as right:
                    for key in ('objv','a','d','cl'):
                        np.testing.assert_array_equal(left[key],right[key])

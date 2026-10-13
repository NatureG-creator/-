"""优化副本与原始 Python 底层的对照测试，不执行默认大规模仿真。"""
from __future__ import annotations

import unittest
import contextlib
import importlib.util
import io
from tempfile import TemporaryDirectory
from pathlib import Path
import numpy as np

from corrosion_model import analysis, analysis_优化版 as fast_analysis
from corrosion_model import ca, ca_优化版 as fast_ca
from corrosion_model import fitness, fitness_优化版 as fast_fitness
from corrosion_model import ga, ga_优化版 as fast_ga
from corrosion_model import stage_moni, stage_moni_优化版 as fast_stage
from corrosion_model import taichi_accel, taichi_accel_优化版 as fast_taichi

PARAMETERS = np.array([.25,.3,.1,5.,2.,.01,3.,.3,.25,2.])
TARGET = np.array([50.,20.,2.,4.,.6,.3])


class OptimizedBackendTests(unittest.TestCase):
    def test_highspeed_entry_save_and_reader_time(self):
        root = Path(__file__).resolve().parent
        spec = importlib.util.spec_from_file_location('highspeed_entry',root/'02_运行多阶段stage_moni_高速版.py')
        entry = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(entry)
        entry.STAGE_GA_CONFIG = dict(F=3,nind=4,selected_count=2,maxgen=3,parallel_workers=1)
        entry.geometry_values = lambda: (5,6,4,25.)
        entry.stage_data_copy = lambda: TARGET.reshape(1,-1).copy()
        reader_spec = importlib.util.spec_from_file_location('optimized_reader',root/'10_read_step2_result.py')
        reader = importlib.util.module_from_spec(reader_spec)
        reader_spec.loader.exec_module(reader)
        with TemporaryDirectory() as temporary:
            entry.__file__ = str(Path(temporary)/'02_运行多阶段stage_moni_高速版.py')
            with contextlib.redirect_stdout(io.StringIO()) as output:
                entry.main()
            self.assertIn('Gen',output.getvalue())
            result_path = Path(temporary)/'step2_stage_moni_highspeed_result.npz'
            saved = reader.load_result(result_path)
            self.assertGreater(float(saved['elapsed_seconds']),0.)
            self.assertFalse(bool(saved['use_taichi']))
            summary = reader.build_summary(result_path,saved)
            self.assertAlmostEqual(summary['elapsed_hours'],summary['elapsed_seconds']/3600.)

    def test_persistent_integer_state_and_float64_chloride(self):
        a = np.ones((4,5,6)); d = np.full_like(a,3.)
        cl = np.full((4,5), .123456789012345)
        state = fast_taichi.TaichiCAState.from_arrays(a,d,cl)
        self.assertEqual(state.a.dtype,np.int32)
        self.assertEqual(state.d.dtype,np.int32)
        self.assertIs(state.cl,cl)
        self.assertEqual(state.cl.dtype,np.float64)
        d[0,0,0] = 1.5
        fallback = fast_taichi.TaichiCAState.from_arrays(a,d,cl)
        self.assertIs(fallback.d,d)

    def test_taichi_cpu_controlled_ca(self):
        if taichi_accel.ti is None:
            self.skipTest('当前解释器未安装 Taichi')
        parameters = PARAMETERS.copy()
        parameters[2] = 0. # 不发生破膜，避开原内核原子更新的既有非确定性。
        kwargs = dict(xy=parameters,F=6,a=None,data=TARGET,data_x=1000.,n=4,w=5,l=6,
                      space=25.,d=None,stage_number=1,cl_concentration=None,use_taichi=True)
        self.assertTrue(taichi_accel.init_taichi('cpu'),taichi_accel.taichi_last_error())
        expected = ca.run_ca(**kwargs,rng=np.random.default_rng(12))
        self.assertTrue(fast_taichi.init_taichi('cpu'),fast_taichi.taichi_last_error())
        actual = fast_ca.run_ca(**kwargs,rng=np.random.default_rng(12))
        for attr in ('a','d','cl_concentration','cs'):
            np.testing.assert_array_equal(getattr(expected,attr),getattr(actual,attr))
        self.assertEqual(actual.a.dtype,np.float64)
        self.assertEqual(actual.d.dtype,np.float64)

    def test_extrema_clipped_edges_even_windows_and_ties(self):
        rng = np.random.default_rng(123)
        surfaces = [rng.normal(size=(19, 23)), np.ones((9, 8)),
                    rng.integers(0, 5, (18, 20)).astype(float),
                    np.array([[0., 3., 1.], [4., 1., 2.]])]
        for surface in surfaces:
            for neighborhood in ((1,1), (4,6), (35,35)):
                for distance in (0,3):
                    for prominence in (0., .05, 1.):
                        expected = analysis.find_local_extrema(surface, prominence, distance, neighborhood)
                        actual = fast_analysis.find_local_extrema(surface, prominence, distance, neighborhood)
                        for first, second in zip(expected, actual):
                            np.testing.assert_array_equal(first, second)

    def test_ga_encoding_decoding_and_rng_state(self):
        for bits in (3,11):
            rng1, rng2 = np.random.default_rng(42), np.random.default_rng(42)
            expected = ga.latin_begin(13,10,bits,rng1)
            actual = fast_ga.latin_begin(13,10,bits,rng2)
            np.testing.assert_array_equal(expected, actual)
            self.assertEqual(rng1.bit_generator.state, rng2.bit_generator.state)
            lb, ub = np.arange(10.) / 7., np.arange(10.) + 5.
            np.testing.assert_array_equal(ga.decode_binary_population(expected,lb,ub,bits),
                                          fast_ga.decode_binary_population(actual,lb,ub,bits))

    def test_spread_and_full_ca_exact_numpy(self):
        for point in ((1,1,1),(3,3,3),(5,6,4)):
            a = np.ones((5,6,5)); cl = np.zeros((5,6))
            r1, r2 = np.random.default_rng(88), np.random.default_rng(88)
            expected = ca.spread_corrosion2(*point,a,.3,.2,4,cl,5.,r1)
            actual = fast_ca.spread_corrosion2(*point,a,.3,.2,4,cl,5.,r2)
            for first, second in zip(expected,actual):
                np.testing.assert_array_equal(first,second)
            np.testing.assert_array_equal(a, np.ones_like(a))
            self.assertEqual(r1.bit_generator.state,r2.bit_generator.state)
        for stage in (1,2):
            a,d,cl = ca.initialise_stage(6,7,5,.01,np.random.default_rng(1))
            a[2:4,2:4,1] = 2.; d[2:4,2:4,1] = 1.
            kwargs = dict(xy=PARAMETERS,F=10,a=a,data=TARGET,data_x=1000.,n=5,w=6,l=7,
                          space=25.,d=d,stage_number=stage,cl_concentration=cl)
            first = ca.run_ca(**kwargs,rng=np.random.default_rng(45))
            second = fast_ca.run_ca(**kwargs,rng=np.random.default_rng(45))
            for attr in ('a','d','cl_concentration','cs'):
                np.testing.assert_array_equal(getattr(first,attr),getattr(second,attr))
            self.assertEqual(first.iterations,second.iterations)

    def test_score_only_replay_and_processes(self):
        kwargs = dict(xy=np.vstack([PARAMETERS,PARAMETERS*.99,PARAMETERS*1.01]),
                      data=TARGET,data_x=1000.,F=4,n=4,w=5,l=6,space=25.,
                      stage_number=1,seed=99,use_taichi=False)
        expected = fitness.evaluate_population(**kwargs,parallel_workers=1)
        for workers in (1,2):
            actual = fast_fitness.evaluate_population(**kwargs,parallel_workers=workers,
                                                      retain_states=False)
            np.testing.assert_array_equal(expected.objv,actual.objv)
            self.assertTrue(all(item.size == 0 for item in actual.a_states))
            state = fast_fitness.recover_individual_state(1, actual, **kwargs)
            np.testing.assert_array_equal(expected.a_states[1],state.a)
            np.testing.assert_array_equal(expected.d_states[1],state.d)
            np.testing.assert_array_equal(expected.cl_states[1],state.cl_concentration)

    def test_two_stage_chain(self):
        kwargs = dict(w=5,l=6,n=4,space=25.,F=3,nind=4,selected_count=2,maxgen=3,
                      seed=19,parallel_workers=1,use_taichi=False)
        data = np.vstack([TARGET, TARGET*1.1])
        first = stage_moni.run_stage_moni(data[:,0],data,stage_moni.StageConfig(**kwargs))
        second = fast_stage.run_stage_moni(data[:,0],data,fast_stage.StageConfig(**kwargs))
        for attr in ('perfect_result_sd','perfect_parameter_sd','stage_numbers'):
            np.testing.assert_array_equal(getattr(first,attr),getattr(second,attr))
        for attr in ('a_sd','d_sd','cl_sd'):
            for left,right in zip(getattr(first,attr),getattr(second,attr)):
                np.testing.assert_array_equal(left,right)


if __name__ == '__main__':
    unittest.main(verbosity=2)

"""有界测速：对比原 Python 底层和优化副本，不更改统一参数或正式结果。"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
import numpy as np
from corrosion_model import analysis, analysis_优化版 as fast_analysis
from corrosion_model import ca, ca_优化版 as fast_ca
from corrosion_model import fitness, fitness_优化版 as fast_fitness
from corrosion_model.ga import combine_objectives


def measure(function, repeats):
    times = []
    for _ in range(repeats):
        start = time.perf_counter()
        result = function()
        times.append(time.perf_counter() - start)
    return float(np.median(times)), result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--grid',type=int,default=40)
    parser.add_argument('--depth',type=int,default=16)
    parser.add_argument('--steps',type=int,default=8)
    parser.add_argument('--population',type=int,default=6)
    parser.add_argument('--repeats',type=int,default=3)
    parser.add_argument('--workers',type=int,default=2)
    args = parser.parse_args()
    if min(args.grid,args.depth,args.steps,args.population,args.repeats,args.workers) < 1:
        parser.error('所有参数必须为正整数')
    reports = {}

    def compare(name, original, optimized, equal):
        original() # 两边均预热；并行评估的进程创建时间仍包含在每次测速中。
        optimized()
        old_time, old = measure(original,args.repeats)
        new_time, new = measure(optimized,args.repeats)
        equal(old,new)
        reports[name] = {'original_seconds':old_time,'optimized_seconds':new_time,
                         'speedup':old_time/new_time,'equal':True}
        print(f'{name}: 原版 {old_time:.6f}s，优化版 {new_time:.6f}s，原版/优化版 {old_time/new_time:.3f}x，一致=True')

    surface = np.random.default_rng(5).normal(size=(100,100))
    compare('局部极值100x100',lambda: analysis.find_local_extrema(surface),
            lambda: fast_analysis.find_local_extrema(surface),
            lambda a,b: [np.testing.assert_array_equal(x,y) for x,y in zip(a,b)])

    parameters = np.array([.25,.3,.1,5.,2.,.01,3.,.3,.25,2.])
    target = np.array([1000.,20.,2.,4.,.6,.3])
    ca_kwargs = dict(xy=parameters,F=args.steps,a=None,data=target,data_x=1000.,
                     n=args.depth,w=args.grid,l=args.grid,space=25.,d=None,
                     stage_number=1,cl_concentration=None)

    def assert_ca(a,b):
        for attribute in ('a','d','cl_concentration','cs'):
            np.testing.assert_array_equal(getattr(a,attribute),getattr(b,attribute))

    compare('完整NumPy_CA',lambda: ca.run_ca(**ca_kwargs,rng=np.random.default_rng(8)),
            lambda: fast_ca.run_ca(**ca_kwargs,rng=np.random.default_rng(8)),assert_ca)

    kwargs = dict(xy=np.tile(parameters,(args.population,1)),data=target,data_x=1000.,
                  F=args.steps,n=args.depth,w=args.grid,l=args.grid,space=25.,
                  stage_number=1,seed=8,parallel_workers=args.workers)

    def original_population():
        result = fitness.evaluate_population(**kwargs)
        _, weighted = combine_objectives(result.objv)
        index = int(np.argmin(weighted))
        return result.objv, result.a_states[index], result.d_states[index],result.cl_states[index]

    def optimized_population():
        result = fast_fitness.evaluate_population(**kwargs,retain_states=False)
        _, weighted = combine_objectives(result.objv)
        index = int(np.argmin(weighted))
        best = fast_fitness.recover_individual_state(index,result,**kwargs)
        return result.objv,best.a,best.d,best.cl_concentration

    compare('种群评估含最优重跑',original_population,optimized_population,
            lambda a,b: [np.testing.assert_array_equal(x,y) for x,y in zip(a,b)])
    path = Path(__file__).with_name('outputs') / 'optimization_benchmark.json'
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps({'settings':vars(args),'results':reports},ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'测速结果保存到: {path}')


if __name__ == '__main__':
    main()

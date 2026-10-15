"""One backend per fresh process, explicit initialization and timed warm samples."""
from __future__ import annotations
import functools
import json
import os
import sys
import time
from pathlib import Path
import numpy as np
from .benchmark import MODES, verify_arch
from .benchmark_pool import ExecutorScope, load_initial_state, sample_statistics, compare_snapshot
from .strict_ga import _apply_scientific_settings, scientific_settings
from corrosion_model.fitness_优化版 import _fitness_worker_init as _base_worker_init

class BackendUnavailable(RuntimeError):
    pass

def initialize_backend(arch, threads=1):
    try:
        import taichi as ti
        from corrosion_model.taichi_accel_优化版 import init_taichi, taichi_last_error
        runtime = ti.lang.impl.get_runtime()
        if runtime.prog is not None:
            cfg = ti.lang.impl.current_cfg()
            verify_arch(arch, str(cfg.arch))
            if int(cfg.cpu_max_num_threads) != int(threads):
                raise BackendUnavailable('已初始化 Taichi 的 CPU 线程配置不匹配')
        # The original initializer builds the original kernels. Inject only runtime configuration.
        original_init = ti.init
        def configured_init(*args, **kwargs):
            kwargs.update(cpu_max_num_threads=int(threads), default_fp=ti.f32,
                          default_ip=ti.i32, offline_cache=False)
            return original_init(*args, **kwargs)
        ti.init = configured_init
        try:
            if not init_taichi(arch):
                raise BackendUnavailable('Taichi初始化不可用：' + str(taichi_last_error()))
        finally:
            ti.init = original_init
        cfg = ti.lang.impl.current_cfg()
        actual = str(cfg.arch)
        verify_arch(arch, actual)
        if int(cfg.cpu_max_num_threads) != int(threads):
            raise BackendUnavailable('Taichi CPU 线程配置未生效')
        return actual
    except BackendUnavailable:
        raise
    except Exception as exc:
        raise BackendUnavailable('Taichi依赖或设备不可用：' + str(exc)) from exc

def configured_initializer(config, threads, *args):
    _apply_scientific_settings(config)
    if args[11]:
        initialize_backend(args[12], threads)
    _base_worker_init(*args)

def run_trial(spec: dict, mode: str, folder: Path) -> dict:
    import corrosion_model.fitness_优化版 as fitness
    total_started = time.perf_counter()
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    options, config = spec['options'], spec['config']
    threads = int(options.get('threads_per_worker', 1))
    workers = min(int(options['workers']), int(options['population'])) if mode.endswith('parallel') else 1
    if threads < 1 or workers * threads > int(options.get('cpu_budget', os.cpu_count() or 1)):
        raise ValueError('workers × threads_per_worker 超过 cpu_budget 或线程数无效')
    workload = options.get('workload', 'population')
    if workload not in ('population', 'short_ga'):
        raise ValueError('未知 workload')
    read_started = time.perf_counter()
    w, l, n = (int(options[key]) for key in ('grid_w','grid_l','grid_n'))
    initial_path = spec.get('initial_state_path')
    if initial_path and not Path(initial_path).is_absolute():
        raise ValueError('initial_state_path 必须是绝对路径')
    a, d, cl = load_initial_state(initial_path, w, l, n)
    stage_number = int(spec.get('stage_number', 1))
    if initial_path and stage_number < 2:
        raise ValueError('有初始快照时 stage_number 必须 >= 2')
    read_seconds = time.perf_counter() - read_started
    use_taichi = mode.startswith('taichi')
    arch = 'gpu' if 'gpu' in mode else 'cpu'
    started = time.perf_counter()
    actual = initialize_backend(arch, threads) if use_taichi else 'cpu'
    initialization_seconds = time.perf_counter() - started
    kwargs = dict(xy=np.asarray(spec['population']), data=np.asarray(spec['target']),
                  data_x=float(spec['target'][0]), F=options['steps'], n=n, w=w, l=l,
                  space=float(config['GEOMETRY_CONFIG']['space_z_um']), stage_number=stage_number,
                  a_jisuan=a, d_jisuan=d, cl_concentration_jisuan=cl,
                  seed=options['seed'], use_taichi=use_taichi, parallel_workers=workers,
                  allow_taichi_parallel=True, taichi_arch=arch, retain_states=True)
    effective_selected_count = int(options.get('selected_count', min(int(options['population'])-1,int(config['STAGE_GA_CONFIG']['selected_count']))))
    if workload == 'short_ga' and not 1 <= effective_selected_count < int(options['population']):
        raise ValueError('short_ga selected_count 必须满足 1 <= selected_count < population')
    def execute():
        if workload == 'population':
            result = fitness.evaluate_population(**kwargs)
            return dict(objv=result.objv, a=np.stack(result.a_states), d=np.stack(result.d_states),
                        cl=np.stack(result.cl_states)), list(result.child_seeds)
        from corrosion_model.ga_优化版 import GAConfig, run_ga
        settings = config['GA_CONFIG']
        ga_config = GAConfig(nind=int(options['population']),
            selected_count=effective_selected_count,
            maxgen=int(options.get('generations',3))+1, parallel_workers=workers,
            **{key: settings[key] for key in ('bits_per_param','base_px','base_pm','decay_rate','sigma_share')})
        result = run_ga(w,l,n,kwargs['data_x'],kwargs['data'],a,int(options['steps']),stage_number,
            kwargs['space'],d,cl,seed=int(options['seed']),config=ga_config,
            lb=np.asarray(config['GA_PARAMETER_LOWER_BOUNDS']),ub=np.asarray(config['GA_PARAMETER_UPPER_BOUNDS']),
            use_taichi=use_taichi,parallel_workers=workers,allow_taichi_parallel=True,taichi_arch=arch)
        return dict(objv=result.perfect_result,a=result.perfect_a,d=result.perfect_d,cl=result.perfect_cl,
                    perfect_parameter=result.perfect_parameter,actual_generations=np.asarray(result.generations)), []
    previous_initializer, previous_executor = fitness._fitness_worker_init, fitness.ProcessPoolExecutor
    scope = ExecutorScope(previous_executor, options.get('pool_policy','recreate'))
    fitness._fitness_worker_init = functools.partial(configured_initializer, config, threads)
    fitness.ProcessPoolExecutor = scope
    samples, repeat_comparisons = [], []
    export_seconds = comparison_seconds = 0.
    child_seeds = []
    try:
        with scientific_settings(config):
            for index in range(int(options['repeats'])+1):
                tick = time.perf_counter()
                arrays, child_seeds = execute()
                if use_taichi:
                    import taichi as ti
                    ti.sync()
                seconds = time.perf_counter()-tick
                if index == 0:
                    first_seconds = seconds
                else:
                    samples.append(seconds)
                tick = time.perf_counter()
                destination = folder / ('first_arrays.npz' if index == 0 else 'arrays.npz')
                if index == 0 or index == int(options['repeats']):
                    np.savez(destination, **arrays)
                export_seconds += time.perf_counter()-tick
                if index:
                    tick = time.perf_counter()
                    repeat_comparisons.append(compare_snapshot(folder/'first_arrays.npz',arrays))
                    comparison_seconds += time.perf_counter()-tick
                del arrays
    finally:
        fitness._fitness_worker_init, fitness.ProcessPoolExecutor = previous_initializer, previous_executor
        scope.close()
    result = dict(mode=mode,label=MODES[mode],state='completed',actual_arch=actual,
        workers=workers,actual_threads=threads,threads_per_worker=threads,
        cpu_budget=int(options.get('cpu_budget',os.cpu_count() or 1)),workload=workload,
        stage_number=stage_number,initial_state_path=initial_path,retain_detail=bool(options.get('retain_detail',True)),
        pool_policy=scope.policy,population_source=('original_ga_seed' if workload=='short_ga' else 'frozen_population'),sample_timing_label=('包含进程池创建' if scope.policy=='recreate' else '复用常驻进程池'),
        initialization_seconds=initialization_seconds,read_seconds=read_seconds,
        first_seconds=first_seconds,samples_seconds=samples,
        export_seconds=export_seconds,comparison_seconds=comparison_seconds,
        total_trial_seconds=time.perf_counter()-total_started,
        repeat_exact=all(x['exact'] for x in repeat_comparisons),repeat_comparisons=repeat_comparisons,
        child_seeds=child_seeds,**sample_statistics(samples))
    if workload == 'short_ga':
        with np.load(folder/'arrays.npz') as data:
            result['actual_generations'] = int(data['actual_generations'])
        result['selected_count'] = effective_selected_count
        result['effective_selected_count'] = effective_selected_count
    return result

def main():
    spec_path, mode, destination = sys.argv[1:]
    folder = Path(destination)
    folder.mkdir(parents=True, exist_ok=True)
    try:
        result = run_trial(json.loads(Path(spec_path).read_text(encoding='utf-8')), mode, folder)
    except BackendUnavailable as exc:
        result = dict(mode=mode,label=MODES[mode],state='unavailable',reason=str(exc))
    except Exception as exc:
        import traceback
        traceback.print_exc()
        result = dict(mode=mode,label=MODES[mode],state='failed',reason=str(exc))
    from .runner import _atomic_json
    _atomic_json(folder/'trial.json',result)

if __name__ == '__main__':
    main()

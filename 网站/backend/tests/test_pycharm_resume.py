import tempfile
import json
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from backend import config
from backend.checkpoint import CheckpointStore, precheck_checkpoint
from corrosion_model.ga_优化版 import GAConfig, run_ga


class PyCharmResumeTests(unittest.TestCase):
    def run_case(self, checkpoint=None, verbose=False):
        return run_ga(5,6,4,10,np.array([10,2,1,3,.2,.3]),None,2,1,25,None,None,
                      seed=17,config=GAConfig(nind=8,selected_count=1,maxgen=4),
                      parallel_workers=2,checkpoint=checkpoint,verbose=verbose)

    def assert_same(self, left, right):
        for name in ('perfect_result','perfect_parameter','perfect_a','perfect_d','perfect_cl'):
            np.testing.assert_array_equal(getattr(left,name),getattr(right,name))
        self.assertEqual(left.generations,right.generations)

    def test_partial_generation_reuses_nonprefix_scores_and_matches_uninterrupted(self):
        baseline=self.run_case()
        with tempfile.TemporaryDirectory() as folder:
            store=CheckpointStore(Path(folder),'case',engine_fingerprint='test')
            def stop(message):
                if '已完成 5/8 个体' in message:raise InterruptedError('power loss')
            # Resolve genuine worker futures in reverse index order.
            with patch('corrosion_model.fitness_优化版.as_completed',side_effect=lambda futures:reversed(futures)):
                with self.assertRaises(InterruptedError):self.run_case(store,stop)
            state=store.load()
            self.assertEqual(set(state['scores']),{'3','4','5','6','7'})
            self.assertEqual(precheck_checkpoint(Path(folder),'case',engine_fingerprint='test')['completed_individuals'],5)
            from concurrent.futures import ProcessPoolExecutor
            submitted=[]
            original_submit=ProcessPoolExecutor.submit
            def submit(pool, worker, task):
                submitted.append(task[0])
                return original_submit(pool,worker,task)
            with patch.object(ProcessPoolExecutor,'submit',submit):
                resumed=self.run_case(store)
            self.assertEqual(submitted[:3],[0,1,2])
            self.assertEqual(len(submitted),19)  # 3 unfinished; the remaining run converges after 2 generations.
            self.assert_same(baseline,resumed)
            self.assertTrue(store.load()['completed'])
            # A completed checkpoint returns the saved result, without reevaluation.
            with patch('corrosion_model.ga_优化版.evaluate_population',side_effect=AssertionError('reevaluated')):
                self.assert_same(resumed,self.run_case(store))

    def test_corrupt_current_falls_back_and_rng_matches(self):
        baseline=self.run_case()
        with tempfile.TemporaryDirectory() as folder:
            store=CheckpointStore(Path(folder),'case',engine_fingerprint='test')
            def stop(message):
                if '已完成第 1 代' in message:raise InterruptedError('boundary')
            with self.assertRaises(InterruptedError):self.run_case(store,stop)
            store.path.write_text('{broken',encoding='utf-8')
            resumed=self.run_case(store)
            self.assert_same(baseline,resumed)

    def test_website_runner_prechecks_and_resumes_identical_npz(self):
        from backend.runner import run_simulation,precheck_resume
        cfg=config.default_simulation_config()
        cfg['mode']='pycharm'
        cfg['TAICHI_CONFIG']['use_taichi']=False
        cfg['GEOMETRY_CONFIG'].update(grid_w=5,grid_l=6,grid_n=4)
        cfg['STAGE_GA_CONFIG'].update(F=2,nind=8,selected_count=1,maxgen=3,parallel_workers=2)
        spec=dict(kind='simulation',run_mode='staged',config=cfg,targets=[[10,2,1,3,.2,.3],[12,3,1,4,.2,.3]])
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            with patch('backend.runner._plot_stage'):
                run_simulation(spec,root/'full')
                def stop(event):
                    if event.get('stage')==2 and '已完成 5/8 个体' in event.get('label',''):
                        raise InterruptedError('interrupt second stage')
                with self.assertRaises(InterruptedError):
                    run_simulation(spec,root/'resume',progress=stop)
                checked=precheck_resume(spec,root/'resume')
                self.assertTrue(checked['available'])
                self.assertTrue(checked['stages'][0]['stage_exported'])
                self.assertEqual(checked['stages'][1]['completed_individuals'],5)
                run_simulation(spec,root/'resume')
            with np.load(root/'full/outputs/simulation.npz',allow_pickle=False) as full:
                with np.load(root/'resume/outputs/simulation.npz',allow_pickle=False) as resumed:
                    for key in full.files:np.testing.assert_array_equal(full[key],resumed[key])

    def test_persistent_pool_matches_recreated_pool(self):
        from backend.runner import run_simulation
        from backend.config import default_simulation_config
        configs=[]
        for reuse in (False, True):
            cfg=default_simulation_config()
            cfg['mode']='pycharm'
            cfg['TAICHI_CONFIG']['use_taichi']=False
            cfg['GEOMETRY_CONFIG'].update(grid_w=5,grid_l=6,grid_n=4)
            cfg['SINGLE_STAGE_GA_CONFIG'].update(F=3,nind=6,selected_count=1,maxgen=4,
                                                 parallel_workers=2,reuse_process_pool=reuse)
            configs.append(cfg)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            outputs=[]
            with patch('backend.runner._plot_stage'):
                for index,cfg in enumerate(configs):
                    spec=dict(kind='simulation',run_mode='single',config=cfg,
                              targets=[[10,2,1,3,.2,.3]])
                    run_simulation(spec,root/str(index))
                    with np.load(root/str(index)/'outputs/simulation.npz',allow_pickle=False) as data:
                        outputs.append({key:np.array(data[key],copy=True) for key in data.files})
            self.assertEqual(outputs[0].keys(),outputs[1].keys())
            for key in outputs[0]:
                np.testing.assert_array_equal(outputs[0][key],outputs[1][key])

    def test_real_worker_stop_and_service_resume_matches_full_run(self):
        from backend.server import make_server
        from backend.runner import run_simulation
        cfg=config.default_simulation_config()
        cfg['mode']='pycharm'
        cfg['TAICHI_CONFIG']['use_taichi']=False
        cfg['GEOMETRY_CONFIG'].update(grid_w=12,grid_l=13,grid_n=6)
        cfg['SINGLE_STAGE_GA_CONFIG'].update(F=3,nind=12,selected_count=1,maxgen=4,
                                             parallel_workers=2,reuse_process_pool=True)
        with tempfile.TemporaryDirectory() as folder:
            server=make_server(port=0,runtime=Path(folder)/'runtime')
            job=None
            try:
                job=server.create_job(dict(kind='simulation',run_mode='single',config=cfg,
                                           seed_mode='fixed',targets=[[10,2,1,3,.2,.3]]))
                root=server.runtime/'jobs'/job['id']
                deadline=time.monotonic()+60
                while time.monotonic()<deadline:
                    try:
                        saved=json.loads((root/'checkpoints/stage_001/progress.json').read_text())['state']
                    except (OSError,ValueError):saved={}
                    if saved.get('next_individual',0)>0 and not saved.get('completed'):break
                    if server.get_job(job['id'])['state']=='failed':
                        self.fail((root/'worker.log').read_text(encoding='utf-8'))
                    time.sleep(.01)
                else:self.fail('no partial checkpoint')
                server.stop(job['id'])
                stopped=server.get_job(job['id'])
                self.assertTrue(stopped['checkpoint']['available'])
                self.assertEqual(stopped['checkpoint']['backend'],'pycharm')
                self.assertGreater(stopped['checkpoint']['saved']['completed_individuals'],0)
                server.resume(job['id'])
                deadline=time.monotonic()+90
                while time.monotonic()<deadline:
                    status=server.get_job(job['id'])
                    if status['state'] in ('failed','completed'):break
                    time.sleep(.05)
                self.assertEqual(status['state'],'completed',(root/'worker.log').read_text(encoding='utf-8'))
                spec=json.loads((root/'spec.json').read_text(encoding='utf-8'))
                with patch('backend.runner._plot_stage'):run_simulation(spec,Path(folder)/'full')
                with np.load(Path(folder)/'full/outputs/simulation.npz',allow_pickle=False) as full:
                    with np.load(root/'outputs/simulation.npz',allow_pickle=False) as resumed:
                        for key in full.files:np.testing.assert_array_equal(full[key],resumed[key])
            finally:
                if job is not None:
                    state=server.get_job(job['id'])
                    if state['state'] in ('running','queued','stop_failed'):server.stop(job['id'])
                server.server_close()


if __name__=='__main__':unittest.main()

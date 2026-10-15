"""Service integration contracts for frozen stage inputs, retries and diagnostics."""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from backend.config import default_simulation_config
from backend.job_service import JobService
from backend.runner import _atomic_json


def benchmark_request():
    return {'kind':'benchmark','config':default_simulation_config(),
            'targets':[[100,20,2,4,.6,.3]],'options':{'grid_w':5,'grid_l':6,'grid_n':4,
            'steps':3,'population':2,'workers':2,'repeats':2,'seed':8,'timeout_seconds':120,
            'target_index':0,'modes':['numpy_serial','numpy_parallel']}}


class BenchmarkIntegrationV2Tests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.runtime=Path(self.temporary.name)
        self.service=JobService()
        self.service.initialize(self.runtime)
        self.source_id='a'*16
        self.source_dir=self.runtime/'jobs'/self.source_id
        (self.source_dir/'outputs').mkdir(parents=True)
        _atomic_json(self.source_dir/'status.json',{'id':self.source_id,'kind':'simulation','state':'completed','pid':None})
        self.source=self.source_dir/'outputs'/'stage_002.npz'
        np.savez(self.source,perfect_a=np.arange(150,dtype=float).reshape(5,6,5),
                 perfect_d=np.zeros((5,6,5)),perfect_cl=np.zeros((5,6)))
        self.payload=benchmark_request()
        source_config=copy.deepcopy(self.payload['config'])
        source_config['GEOMETRY_CONFIG'].update(grid_w=5,grid_l=6,grid_n=4)
        _atomic_json(self.source_dir/'spec.json',{'config':source_config})
        self.payload.update(source_job_id=self.source_id,source_stage=2)

    def test_source_stage_is_byte_frozen_and_sha_matches(self):
        before=copy.deepcopy(self.payload)
        state=self.service.create_job(self.payload,launch=False)
        spec=self.service.get_job(state['id'])['spec']
        frozen=self.runtime/'jobs'/state['id']/spec['initial_state_path']
        self.assertEqual(frozen.read_bytes(),self.source.read_bytes())
        info=spec['initial_state_info']
        self.assertEqual(info['source_job_id'],self.source_id)
        self.assertEqual(info['source_stage'],2)
        self.assertEqual(info['sha256'],hashlib.sha256(frozen.read_bytes()).hexdigest())
        self.assertEqual(info['geometry']['space_z_um'],self.payload['config']['GEOMETRY_CONFIG']['space_z_um'])
        self.assertEqual(spec['stage_number'],3)
        self.assertEqual(self.payload,before)
        original=frozen.read_bytes()
        self.source.write_bytes(b'original source changed after freeze')
        self.assertEqual(frozen.read_bytes(),original)

    def test_dimension_mismatch_rejected_before_job_creation_or_launch(self):
        before=set((self.runtime/'jobs').iterdir())
        original=self.source.read_bytes()
        self.payload['options']['grid_w']=6
        with patch.object(self.service,'launch') as launch:
            with self.assertRaisesRegex(ValueError,'不进行隐式重采样'):
                self.service.create_job(self.payload)
            launch.assert_not_called()
        self.assertEqual(set((self.runtime/'jobs').iterdir()),before)
        self.assertEqual(self.source.read_bytes(),original)

    def test_same_shape_different_physical_spacing_is_rejected(self):
        self.payload['config']['GEOMETRY_CONFIG']['space_z_um'] *= 2
        before=set((self.runtime/'jobs').iterdir())
        with patch.object(self.service,'launch') as launch:
            with self.assertRaisesRegex(ValueError,'物理间距'):
                self.service.create_job(self.payload)
            launch.assert_not_called()
        self.assertEqual(set((self.runtime/'jobs').iterdir()),before)

    def test_retry_creates_new_baseline_and_preserves_frozen_source(self):
        previous=self.service.create_job(self.payload,launch=False)
        old_dir=self.runtime/'jobs'/previous['id']
        old_spec=self.service.get_job(previous['id'])['spec']
        old_frozen=(old_dir/old_spec['initial_state_path']).read_bytes()
        _atomic_json(old_dir/'status.json',dict(previous,state='completed'))
        (old_dir/'outputs').mkdir()
        old_summary={'rows':[{'mode':'numpy_serial','state':'completed','median_seconds':999},
                             {'mode':'numpy_parallel','state':'timeout'}]}
        _atomic_json(old_dir/'outputs'/'summary.json',old_summary)
        # A retry must depend on its own frozen snapshot, even if the original disappears.
        self.source.unlink()
        with patch.object(self.service,'launch') as launch:
            retry=self.service.retry_benchmark(previous['id'],{})
            launch.assert_called_once_with(retry['id'])
        self.assertNotEqual(retry['id'],previous['id'])
        new_state=self.service.get_job(retry['id'])
        spec=new_state['spec']
        self.assertEqual(spec['options']['modes'],['numpy_serial','numpy_parallel'])
        self.assertEqual(spec['retry_of'],previous['id'])
        self.assertEqual(spec['initial_state_info'],old_spec['initial_state_info'])
        self.assertEqual(spec['stage_number'],3)
        new_dir=self.runtime/'jobs'/retry['id']
        self.assertEqual((new_dir/spec['initial_state_path']).read_bytes(),old_frozen)
        self.assertIsNone(new_state['summary'])
        self.assertFalse((new_dir/'outputs'/'summary.json').exists())
        self.assertEqual(json.loads((old_dir/'outputs'/'summary.json').read_text()),old_summary)

    def test_diagnostics_service_creates_isolated_queued_job(self):
        with patch.object(self.service,'launch') as launch:
            state=self.service.create_job({'kind':'diagnostics','timeout_seconds':7})
            launch.assert_called_once_with(state['id'])
        saved=self.service.get_job(state['id'])
        self.assertEqual(saved['kind'],'diagnostics')
        self.assertEqual(saved['state'],'queued')
        self.assertEqual(saved['spec'],{'kind':'diagnostics','timeout_seconds':7})
        with patch.object(self.service,'launch') as launch:
            for invalid in (0,31,True,1.5):
                with self.subTest(invalid=invalid):
                    with self.assertRaises(ValueError):
                        self.service.create_job({'kind':'diagnostics','timeout_seconds':invalid})
            launch.assert_not_called()

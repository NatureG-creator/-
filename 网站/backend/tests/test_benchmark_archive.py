"""On-demand benchmark archive snapshots are cached and immutable."""
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from backend.benchmark_archive import ensure_benchmark_bundle

class BenchmarkArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.output=self.root/'outputs'
        self.output.mkdir()
        (self.output/'benchmark_inputs.json').write_text('{"input_hash":"frozen"}',encoding='utf-8')
        self.report=dict(rows=[dict(variant_id='numpy_serial__s8',mode='numpy_serial',state='completed',median_seconds=1.)],revision=1)
        self.folder=self.output/'trials'/'numpy_serial__s8'
        self.folder.mkdir(parents=True)
        (self.folder/'trial.log').write_text('first log',encoding='utf-8')
        self.save_report()
    def tearDown(self): self.temp.cleanup()
    def save_report(self):
        (self.output/'summary.json').write_text(json.dumps(self.report),encoding='utf-8')
    def test_same_snapshot_uses_cached_archive(self):
        first=ensure_benchmark_bundle(self.root)
        original=first.read_bytes()
        with patch('backend.benchmark_archive.zipfile.ZipFile',side_effect=AssertionError('must use cache')):
            second=ensure_benchmark_bundle(self.root)
        self.assertEqual(first,second)
        self.assertEqual(first.read_bytes(),original)
        self.assertEqual(first.parent,self.root/'archives')
        self.assertFalse(list(first.parent.glob('*.tmp')))
    def test_report_change_creates_new_immutable_snapshot(self):
        first=ensure_benchmark_bundle(self.root)
        old=first.read_bytes()
        self.report['revision']=2
        self.report['rows'][0]['median_seconds']=3.
        self.save_report()
        second=ensure_benchmark_bundle(self.root)
        self.assertNotEqual(first,second)
        self.assertEqual(first.read_bytes(),old)
        with zipfile.ZipFile(first) as archive:
            self.assertEqual(json.loads(archive.read('summary.json'))['revision'],1)
        with zipfile.ZipFile(second) as archive:
            self.assertEqual(json.loads(archive.read('summary.json'))['revision'],2)
            self.assertIn('benchmark_results.csv',archive.namelist())
            self.assertIn('benchmark_inputs.json',archive.namelist())
            self.assertIn('trials/numpy_serial__s8/trial.log',archive.namelist())
        info=json.loads((self.output/'bundle_info.json').read_text(encoding='utf-8'))
        self.assertGreaterEqual(info['packing_seconds'],0)
        self.assertEqual(info['bytes'],second.stat().st_size)
    def test_trial_file_change_invalidates_cache_without_mutating_old_zip(self):
        first=ensure_benchmark_bundle(self.root)
        old=first.read_bytes()
        (self.folder/'trial.log').write_text('a longer replacement log',encoding='utf-8')
        second=ensure_benchmark_bundle(self.root)
        self.assertNotEqual(first,second)
        self.assertEqual(first.read_bytes(),old)
        with zipfile.ZipFile(first) as archive:
            self.assertEqual(archive.read('trials/numpy_serial__s8/trial.log'),b'first log')
        with zipfile.ZipFile(second) as archive:
            self.assertEqual(archive.read('trials/numpy_serial__s8/trial.log'),b'a longer replacement log')

    def add_source(self):
        inputs=self.root/'inputs'
        inputs.mkdir()
        source=inputs/'initial_state.npz'
        source.write_bytes(b'frozen source npz bytes')
        metadata={'sha256':'original-source-sha','source_job_id':'source123','source_stage':1}
        spec={'initial_state_path':'inputs/initial_state.npz','initial_state_info':metadata,'config':{'unchanged':True}}
        (self.output/'benchmark_inputs.json').write_text(json.dumps(spec),encoding='utf-8')
        trial=dict(spec,initial_state_path=str(source.resolve()))
        (self.folder/'trial_request.json').write_text(json.dumps(trial),encoding='utf-8')
        self.report['initial_state_info']=metadata
        self.save_report()
        return source,spec,trial
    def test_source_snapshot_and_portable_requests_preserve_metadata(self):
        source,spec,trial=self.add_source()
        summary=(self.output/'summary.json').read_bytes()
        bundle=ensure_benchmark_bundle(self.root)
        with zipfile.ZipFile(bundle) as archive:
            self.assertEqual(archive.read('inputs/initial_state.npz'),source.read_bytes())
            self.assertEqual(archive.read('summary.json'),summary)
            for name in ('benchmark_inputs.json','trials/numpy_serial__s8/trial_request.json'):
                value=json.loads(archive.read(name))
                self.assertEqual(value['initial_state_path'],'inputs/initial_state.npz')
                self.assertEqual(value['initial_state_info'],spec['initial_state_info'])
                self.assertEqual(value['config'],spec['config'])
            readme=archive.read('README.md').decode('utf-8')
            self.assertIn('解压目录',readme)
            self.assertIn('同版本',readme)
        self.assertEqual(json.loads((self.folder/'trial_request.json').read_text(encoding='utf-8')),trial)
    def test_source_snapshot_stat_invalidates_cache(self):
        source,_,_=self.add_source()
        first=ensure_benchmark_bundle(self.root)
        old=first.read_bytes()
        source.write_bytes(b'new longer frozen source bytes')
        second=ensure_benchmark_bundle(self.root)
        self.assertNotEqual(first,second)
        self.assertEqual(first.read_bytes(),old)
    def test_rejects_arbitrary_source_path_in_inputs_and_trial(self):
        source,spec,trial=self.add_source()
        outside=self.root/'other.npz'
        outside.write_bytes(b'private data')
        for name,value in ((self.output/'benchmark_inputs.json',spec),(self.folder/'trial_request.json',trial)):
            original=name.read_bytes()
            changed=dict(value,initial_state_path=str(outside))
            name.write_text(json.dumps(changed),encoding='utf-8')
            with self.assertRaises(ValueError):
                ensure_benchmark_bundle(self.root)
            name.write_bytes(original)

    def test_native_lock_coordinates_handles_and_releases_on_exception(self):
        from backend.benchmark_archive import benchmark_artifact_lock
        with benchmark_artifact_lock(self.root):
            with self.assertRaises(TimeoutError):
                with benchmark_artifact_lock(self.root,timeout=.1):
                    self.fail('another handle must not enter')
        with self.assertRaisesRegex(RuntimeError,'test release'):
            with benchmark_artifact_lock(self.root,timeout=.1):
                raise RuntimeError('test release')
        with benchmark_artifact_lock(self.root,timeout=.1):
            pass
    def test_archive_enumeration_waits_for_artifact_lock(self):
        from backend.benchmark_archive import benchmark_artifact_lock
        with benchmark_artifact_lock(self.root):
            from functools import partial
            with patch('backend.benchmark_archive.benchmark_artifact_lock',side_effect=partial(benchmark_artifact_lock,timeout=.1)):
                with self.assertRaises(TimeoutError):
                    ensure_benchmark_bundle(self.root)
        self.assertFalse((self.root/'archives').exists())
        self.assertTrue(ensure_benchmark_bundle(self.root).is_file())

    def test_native_lock_blocks_an_independent_process(self):
        import os
        import subprocess
        import sys
        from backend.benchmark_archive import benchmark_artifact_lock
        script="from backend.benchmark_archive import benchmark_artifact_lock; from pathlib import Path; import sys;\nwith benchmark_artifact_lock(Path(sys.argv[1]),timeout=.1):\n print('unexpected entry')"
        flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
        with benchmark_artifact_lock(self.root):
            child=subprocess.run([sys.executable,'-c',script,str(self.root)],capture_output=True,text=True,encoding='utf-8',timeout=15,creationflags=flags)
        self.assertNotEqual(child.returncode,0)
        self.assertIn('TimeoutError',child.stderr)
        self.assertNotIn('unexpected entry',child.stdout)

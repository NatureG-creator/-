import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import psutil
from backend import apdl_process as controlled


def wait_file(path):
    deadline = time.monotonic() + 10
    while not path.exists() and time.monotonic() < deadline:
        time.sleep(.03)
    if not path.exists():
        raise AssertionError(f'missing owned-process marker: {path}')
    return int(path.read_text())


class OwnedProcessTests(unittest.TestCase):
    def test_stop_without_execution_is_not_started(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(controlled.stop_owned_execution(Path(temp))['state'], 'not_started')

    def test_group_cleans_descendant_after_command_parent_exits(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            marker = output/'child.pid'
            code = "import subprocess,sys;from pathlib import Path;p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']);Path(sys.argv[1]).write_text(str(p.pid))"
            with (output/'launcher.log').open('wb') as stream:
                owner = controlled.launch_owned([sys.executable, '-c', code, str(marker)], output, stream)
                try:
                    child = wait_file(marker)
                    self.assertEqual(owner.wait(timeout=10), 0)
                    self.assertTrue(psutil.pid_exists(child))
                    result = owner.close()
                    self.assertEqual(result['state'], 'stopped')
                    self.assertTrue(result['verified_empty'])
                    self.assertFalse(psutil.pid_exists(child))
                finally:
                    owner.close()

    def test_normal_completion_persists_identity_before_real_command(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            code = "import json;from pathlib import Path;r=json.loads(Path('mapdl_process.json').read_text(encoding='utf-8'));assert r['state']=='grouped';assert r['launcher_create_time'];Path('checked').write_text('ok')"
            with (output/'launcher.log').open('wb') as stream:
                owner = controlled.launch_owned([sys.executable, '-c', code], output, stream)
                try:
                    self.assertEqual(owner.wait(timeout=10), 0)
                    self.assertTrue((output/'checked').exists())
                    self.assertTrue(owner.close()['verified_empty'])
                finally:
                    owner.close()

    def test_child_receives_explicit_environment(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            marker = output/'env.txt'
            code = "import os;from pathlib import Path;Path('env.txt').write_text(os.environ['APDL_TEST_ENV'])"
            with (output/'launcher.log').open('wb') as stream:
                owner = controlled.launch_owned([sys.executable, '-c', code], output, stream,
                                                env={**os.environ, 'APDL_TEST_ENV': 'injected'})
                try:
                    self.assertEqual(owner.wait(timeout=10), 0)
                    self.assertEqual(marker.read_text(), 'injected')
                finally:
                    owner.close()

    def test_external_stop_rejects_pid_reuse_and_persists_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            with (output/'launcher.log').open('wb') as stream:
                owner = controlled.launch_owned([sys.executable, '-c', 'import time;time.sleep(60)'], output, stream)
                try:
                    record_path = output/'mapdl_process.json'
                    record = json.loads(record_path.read_text(encoding='utf-8'))
                    record['launcher_create_time'] -= 100
                    record_path.write_text(json.dumps(record))
                    result = controlled.stop_owned_execution(output)
                    self.assertEqual(result['state'], 'failed')
                    self.assertIn('身份', result['error'])
                    self.assertIsNone(owner.poll())
                    self.assertEqual(json.loads(record_path.read_text(encoding='utf-8'))['cleanup']['state'], 'failed')
                finally:
                    owner.close()

    def test_permission_failure_is_not_reported_stopped(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            with (output/'launcher.log').open('wb') as stream:
                owner = controlled.launch_owned([sys.executable, '-c', 'import time;time.sleep(60)'], output, stream)
                try:
                    with patch.object(controlled, '_open_group', side_effect=PermissionError('denied')):
                        result = controlled.stop_owned_execution(output)
                    self.assertEqual(result['state'], 'failed')
                    self.assertFalse(result['verified_empty'])
                finally:
                    owner.close()

    def test_external_stop_after_launcher_exit_and_job_destruction_is_verified(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            with (output/'launcher.log').open('wb') as stream:
                owner = controlled.launch_owned([sys.executable, '-c', 'pass'], output, stream)
                try:
                    owner.wait(timeout=10)
                    self.assertTrue(controlled.stop_owned_execution(output)['verified_empty'])
                    owner.close()
                    self.assertTrue(controlled.stop_owned_execution(output)['verified_empty'])
                finally:
                    owner.close()

    def test_timeout_requires_explicit_cleanup_and_empties_group(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            marker = output/'solver.pid'
            with (output/'launcher.log').open('wb') as stream:
                owner = controlled.launch_owned([sys.executable, '-c', "import os,time;from pathlib import Path;Path('solver.pid').write_text(str(os.getpid()));time.sleep(60)"], output, stream)
                try:
                    solver = wait_file(marker)
                    with self.assertRaises(subprocess.TimeoutExpired):
                        owner.wait(timeout=.03)
                    self.assertTrue(owner.close()['verified_empty'])
                    self.assertFalse(psutil.pid_exists(solver))
                finally:
                    owner.close()

    def test_assignment_failure_never_starts_real_command(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            group_type = controlled._WindowsGroup if os.name == 'nt' else controlled._PosixGroup
            with (output/'launcher.log').open('wb') as stream, patch.object(group_type, 'assign', side_effect=PermissionError('assign denied')):
                with self.assertRaises(PermissionError):
                    controlled.launch_owned([sys.executable, '-c', "from pathlib import Path;Path('unsafe').write_text('ran')"], output, stream)
            self.assertFalse((output/'unsafe').exists())

    def test_failed_owner_cleanup_can_retry_against_the_real_group(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            marker = output/'solver.pid'
            with (output/'launcher.log').open('wb') as stream:
                owner = controlled.launch_owned([sys.executable, '-c', "import os,time;from pathlib import Path;Path('solver.pid').write_text(str(os.getpid()));time.sleep(60)"], output, stream)
                try:
                    solver = wait_file(marker)
                    with patch.object(owner.group, 'terminate', side_effect=PermissionError('denied')):
                        self.assertEqual(owner.close()['state'], 'failed')
                    self.assertTrue(owner.close()['verified_empty'])
                    self.assertFalse(psutil.pid_exists(solver))
                finally:
                    owner.close()

    def test_stop_record_write_failure_returns_explicit_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            with (output/'launcher.log').open('wb') as stream:
                owner = controlled.launch_owned([sys.executable, '-c', 'pass'], output, stream)
                try:
                    owner.wait(timeout=10)
                    with patch.object(controlled, '_persist', side_effect=PermissionError('read only')):
                        result = controlled.stop_owned_execution(output)
                    self.assertEqual(result['state'], 'failed')
                    self.assertIn('persistence_error', result)
                finally:
                    owner.close()

    def test_startup_cleanup_failure_does_not_hide_persistence_error(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            group_type = controlled._WindowsGroup if os.name == 'nt' else controlled._PosixGroup
            with (output/'launcher.log').open('wb') as stream, patch.object(controlled, '_persist', side_effect=RuntimeError('persist denied')), patch.object(group_type, 'terminate', side_effect=PermissionError('cleanup denied')):
                with self.assertRaisesRegex(RuntimeError, 'persist denied'):
                    controlled.launch_owned([sys.executable, '-c', "from pathlib import Path;Path('unsafe').write_text('ran')"], output, stream)
            self.assertFalse((output/'unsafe').exists())

    @unittest.skipUnless(os.name == 'nt', 'Windows kill-on-close guarantee')
    def test_worker_unexpected_exit_kills_all_owned_descendants(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            marker = output/'solver.pid'
            code = "import os,sys,time;from pathlib import Path;sys.path.insert(0,sys.argv[2]);from backend.apdl_process import launch_owned;f=open(Path(sys.argv[1])/'launcher.log','wb');o=launch_owned([sys.executable,'-c',\"import os,time;from pathlib import Path;Path('solver.pid').write_text(str(os.getpid()));time.sleep(60)\"],Path(sys.argv[1]),f);time.sleep(60)"
            worker = subprocess.Popen([sys.executable, '-c', code, str(output), str(Path(__file__).resolve().parents[2])])
            solver_pid = None
            try:
                solver_pid = wait_file(marker)
                worker.kill()
                worker.wait(timeout=10)
                deadline = time.monotonic()+10
                while psutil.pid_exists(solver_pid) and time.monotonic() < deadline:
                    time.sleep(.03)
                self.assertFalse(psutil.pid_exists(solver_pid))
            finally:
                if worker.poll() is None:
                    worker.kill()
                    worker.wait(timeout=10)
                controlled.stop_owned_execution(output)
                if solver_pid and psutil.pid_exists(solver_pid):
                    psutil.Process(solver_pid).kill()

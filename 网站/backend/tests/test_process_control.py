import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
import psutil

class ProcessControlTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root=Path(self.directory.name).resolve()
        self.job=self.root/'jobs'/'job1'
        self.job.mkdir(parents=True)
        (self.job/'worker.lock').write_text('123',encoding='ascii')
        self.state={'pid':123,'process_created_at':42.0}
        self.proc=MagicMock()
        self.proc.create_time.return_value=42.0
        self.proc.cmdline.return_value=['python','-u','-m','backend.worker','job1']
        self.proc.cwd.return_value=str(self.root)
        self.proc.environ.return_value={'CORROSION_RUNTIME_DIR':str(self.root/'runtime')}

    def verify(self):
        from backend.process_control import verify_worker_process
        with patch('backend.process_control.psutil.Process',return_value=self.proc):
            return verify_worker_process('job1',self.state,self.job,self.root/'runtime',self.root)

    def test_correct_identity(self):
        self.assertIs(self.verify(),self.proc)
        self.proc.kill.assert_not_called()

    def test_rejects_wrong_identities_without_killing(self):
        for key,value in [('pid',True),('pid',124),('process_created_at',41.0),('process_created_at',None)]:
            with self.subTest(key=key,value=value):
                old=self.state[key]; self.state[key]=value
                with self.assertRaises(ValueError): self.verify()
                self.state[key]=old
        self.proc.kill.assert_not_called()

    def test_rejects_command_directory_and_environment(self):
        for method,value in [('cmdline',['python','-m','backend.worker','another']),('cmdline',['python','-m','backend.worker-other','job1']),('cwd',str(self.root/'other')),('environ',{})]:
            with self.subTest(method=method):
                old=getattr(self.proc,method).return_value
                getattr(self.proc,method).return_value=value
                with self.assertRaises(ValueError): self.verify()
                getattr(self.proc,method).return_value=old
        self.proc.kill.assert_not_called()

    def test_access_denied_is_rejection(self):
        self.proc.environ.side_effect=psutil.AccessDenied(123)
        with self.assertRaisesRegex(ValueError,'核验'): self.verify()
        self.proc.kill.assert_not_called()

    def test_stop_kills_children_and_parent_and_waits(self):
        from backend.process_control import stop_verified_process
        child=MagicMock()
        self.proc.children.return_value=[child]
        with patch('backend.process_control.psutil.wait_procs',return_value=([],[])) as wait:
            stop_verified_process(self.proc)
        child.kill.assert_called_once()
        self.proc.kill.assert_called_once()
        wait.assert_called_once()

    def test_stop_does_not_swallow_permission_errors(self):
        from backend.process_control import stop_verified_process
        self.proc.children.side_effect=psutil.AccessDenied(123)
        with self.assertRaises(psutil.AccessDenied): stop_verified_process(self.proc)

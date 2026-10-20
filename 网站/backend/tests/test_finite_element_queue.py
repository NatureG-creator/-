import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from backend.job_service import JobService
from backend.runner import _atomic_json


class FiniteElementQueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.service = JobService()
        self.service.initialize(Path(self.temp.name))

    def add_job(self, job_id, kind, created_at, state="queued"):
        folder = self.service.runtime / "jobs" / job_id
        folder.mkdir()
        _atomic_json(folder / "status.json", {
            "id": job_id, "kind": kind, "state": state,
            "created_at": created_at, "updated_at": created_at, "pid": None,
        })
        return folder / "status.json"

    def wait_until(self, predicate, timeout=2):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return True
            time.sleep(.01)
        return False

    def test_finite_element_and_apdl_tasks_run_in_creation_order(self):
        first_id, second_id = "1" * 16, "2" * 16
        first_status = self.add_job(first_id, "finite_element", 1)
        second_status = self.add_job(second_id, "apdl_tension", 2)
        first_started = threading.Event()
        release_first = threading.Event()
        second_started = threading.Event()
        started = []

        class Process:
            def __init__(self, finish):
                self.finish = finish

            def wait(self):
                self.finish()

        def start(job_id):
            started.append(job_id)
            status_path = self.service.runtime / "jobs" / job_id / "status.json"
            status = json.loads(status_path.read_text(encoding="utf-8"))
            status.update(state="running", pid=None)
            _atomic_json(status_path, status)
            if job_id == first_id:
                first_started.set()

                def finish_first():
                    release_first.wait(2)
                    status = json.loads(first_status.read_text(encoding="utf-8"))
                    status.update(state="completed")
                    _atomic_json(first_status, status)

                return Process(finish_first)

            second_started.set()
            status = json.loads(second_status.read_text(encoding="utf-8"))
            status.update(state="completed")
            _atomic_json(second_status, status)
            return Process(lambda: None)

        with patch.object(self.service, "_start_process", side_effect=start):
            self.service.launch(first_id)
            self.assertTrue(first_started.wait(1), "first FE task did not start")
            self.service.launch(second_id)
            self.assertTrue(self.wait_until(lambda: json.loads(second_status.read_text(
                encoding="utf-8")).get("queue_position") == 2), "second task did not show queue position")
            self.assertEqual(started, [first_id])
            release_first.set()
            self.assertTrue(second_started.wait(1), "APDL task did not start after the first task completed")
            self.assertTrue(self.wait_until(lambda: self.service._launching_jobs == {}))

        self.assertEqual(started, [first_id, second_id])
        self.assertEqual(json.loads(second_status.read_text(encoding="utf-8"))["state"], "completed")

    def test_queue_sort_tolerates_missing_or_invalid_creation_time(self):
        first, second = "1" * 16, "2" * 16
        self.add_job(first, "finite_element", "invalid")
        self.add_job(second, "apdl_tension", None)
        self.service._launching_jobs.update({first: "token-1", second: "token-2"})
        queue = self.service._finite_element_queue()
        self.assertEqual([item[1] for item in queue], ["1" * 16, "2" * 16])

    def test_unlaunched_queued_task_does_not_block_submitted_task(self):
        unlaunched = "1" * 16
        submitted = "2" * 16
        self.add_job(unlaunched, "finite_element", 1)
        self.add_job(submitted, "apdl_tension", 2)
        self.service._launching_jobs[submitted] = "token"
        self.assertEqual([item[1] for item in self.service._finite_element_queue()], [submitted])

    def test_next_task_starts_after_previous_task_fails(self):
        first_id, second_id = "1" * 16, "2" * 16
        first_status = self.add_job(first_id, "finite_element", 1)
        second_status = self.add_job(second_id, "apdl_tension", 2)
        first_started = threading.Event()
        release_first = threading.Event()
        second_started = threading.Event()
        started = []

        class Process:
            def __init__(self, finish):
                self.finish = finish

            def wait(self):
                self.finish()

        def start(job_id):
            started.append(job_id)
            if job_id == first_id:
                first_started.set()

                def fail_first():
                    release_first.wait(2)
                    status = json.loads(first_status.read_text(encoding="utf-8"))
                    status.update(state="failed", error="expected test failure")
                    _atomic_json(first_status, status)

                return Process(fail_first)

            second_started.set()
            status = json.loads(second_status.read_text(encoding="utf-8"))
            status.update(state="completed")
            _atomic_json(second_status, status)
            return Process(lambda: None)

        with patch.object(self.service, "_start_process", side_effect=start):
            self.service.launch(first_id)
            self.assertTrue(first_started.wait(1), "first FE task did not start")
            self.service.launch(second_id)
            release_first.set()
            self.assertTrue(second_started.wait(1), "next FE task did not start after previous failure")
            self.assertTrue(self.wait_until(lambda: self.service._launching_jobs == {}))

        self.assertEqual(started, [first_id, second_id])
        self.assertEqual(json.loads(second_status.read_text(encoding="utf-8"))["state"], "completed")


if __name__ == "__main__":
    unittest.main()

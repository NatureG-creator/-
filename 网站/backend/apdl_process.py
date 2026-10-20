"""Owned solver groups. Windows jobs kill every member on the worker's handle close.

The launcher blocks on stdin until assignment and durable identity recording finish.
POSIX groups support explicit cleanup only; worker-crash cleanup is not guaranteed.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
import uuid

import psutil

RECORD_NAME = 'mapdl_process.json'
LAUNCHER = Path(__file__).with_name('apdl_launcher.py').resolve()


def _persist(output, record):
    # Unique temp name also allows an external stop and worker cleanup to overlap.
    temporary = output/(RECORD_NAME+'.'+uuid.uuid4().hex+'.tmp')
    temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(output/RECORD_NAME)


if os.name == 'nt':
    _kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    class _BasicLimits(ctypes.Structure):
        _fields_ = [('PerProcessUserTimeLimit', ctypes.c_longlong), ('PerJobUserTimeLimit', ctypes.c_longlong),
                    ('LimitFlags', wintypes.DWORD), ('MinimumWorkingSetSize', ctypes.c_size_t),
                    ('MaximumWorkingSetSize', ctypes.c_size_t), ('ActiveProcessLimit', wintypes.DWORD),
                    ('Affinity', ctypes.c_size_t), ('PriorityClass', wintypes.DWORD), ('SchedulingClass', wintypes.DWORD)]
    class _IOCounters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_ulonglong) for name in ('ReadOperationCount', 'WriteOperationCount',
                    'OtherOperationCount', 'ReadTransferCount', 'WriteTransferCount', 'OtherTransferCount')]
    class _ExtendedLimits(ctypes.Structure):
        _fields_ = [('BasicLimitInformation', _BasicLimits), ('IoInfo', _IOCounters),
                    ('ProcessMemoryLimit', ctypes.c_size_t), ('JobMemoryLimit', ctypes.c_size_t),
                    ('PeakProcessMemoryUsed', ctypes.c_size_t), ('PeakJobMemoryUsed', ctypes.c_size_t)]
    class _Accounting(ctypes.Structure):
        _fields_ = [('TotalUserTime', ctypes.c_longlong), ('TotalKernelTime', ctypes.c_longlong),
                    ('ThisPeriodTotalUserTime', ctypes.c_longlong), ('ThisPeriodTotalKernelTime', ctypes.c_longlong),
                    ('TotalPageFaultCount', wintypes.DWORD), ('TotalProcesses', wintypes.DWORD),
                    ('ActiveProcesses', wintypes.DWORD), ('TotalTerminatedProcesses', wintypes.DWORD)]
    for name, args, result in (
        ('CreateJobObjectW', [ctypes.c_void_p, wintypes.LPCWSTR], wintypes.HANDLE),
        ('OpenJobObjectW', [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR], wintypes.HANDLE),
        ('SetInformationJobObject', [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD], wintypes.BOOL),
        ('QueryInformationJobObject', [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p], wintypes.BOOL),
        ('AssignProcessToJobObject', [wintypes.HANDLE, wintypes.HANDLE], wintypes.BOOL),
        ('TerminateJobObject', [wintypes.HANDLE, wintypes.UINT], wintypes.BOOL),
        ('CloseHandle', [wintypes.HANDLE], wintypes.BOOL),
    ):
        function = getattr(_kernel, name)
        function.argtypes, function.restype = args, result

    def _check(value):
        if not value:
            raise ctypes.WinError(ctypes.get_last_error())
        return value


class _WindowsGroup:
    def __init__(self, name, create=False):
        self.handle = None
        if create:
            handle = _check(_kernel.CreateJobObjectW(None, name))
            if ctypes.get_last_error() == 183:
                _kernel.CloseHandle(handle)
                raise RuntimeError('监管组随机名称已存在，拒绝复用。')
            self.handle = handle
            try:
                limits = _ExtendedLimits()
                limits.BasicLimitInformation.LimitFlags = 0x2000  # KILL_ON_JOB_CLOSE, no breakaway
                _check(_kernel.SetInformationJobObject(handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)))
            except BaseException:
                self.close()
                raise
        else:
            handle = _kernel.OpenJobObjectW(0x0008 | 0x0004, False, name)  # QUERY | TERMINATE
            if not handle:
                if ctypes.get_last_error() == 2:
                    return  # Named object has disappeared: no surviving job members.
                raise ctypes.WinError(ctypes.get_last_error())
            self.handle = handle

    def assign(self, process):
        _check(_kernel.AssignProcessToJobObject(self.handle, wintypes.HANDLE(int(process._handle))))

    def active(self):
        if not self.handle:
            return 0
        info = _Accounting()
        _check(_kernel.QueryInformationJobObject(self.handle, 1, ctypes.byref(info), ctypes.sizeof(info), None))
        return info.ActiveProcesses

    def terminate(self):
        if self.handle:
            _check(_kernel.TerminateJobObject(self.handle, 1))

    def close(self):
        if self.handle:
            _check(_kernel.CloseHandle(self.handle))
            self.handle = None


class _PosixGroup:
    def __init__(self, pid=None):
        self.pid = pid

    def assign(self, process):
        self.pid = process.pid

    def active(self):
        if not self.pid:
            return 0
        count = 0
        for item in psutil.process_iter(['pid', 'status']):
            try:
                if os.getpgid(item.pid) == self.pid and item.status() != psutil.STATUS_ZOMBIE:
                    count += 1
            except ProcessLookupError:
                pass
        return count

    def terminate(self):
        if self.pid:
            try:
                os.killpg(self.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    def close(self):
        pass


def _open_group(record):
    if os.name == 'nt':
        return _WindowsGroup(record['group_name'])
    return _PosixGroup(record['launcher_pid'])


def _cleanup(group):
    group.terminate()  # Always terminate/query the group, even if launcher already exited.
    deadline = time.monotonic()+5
    while group.active():
        if time.monotonic() >= deadline:
            raise RuntimeError('监管组仍有活动进程，清理未完成。')
        time.sleep(.02)
    return {'state': 'stopped', 'verified_empty': True}


def _validate_record(output, record):
    token = record.get('execution_id', '')
    if (record.get('version') != 1 or not re.fullmatch(r'[0-9a-f]{32}', token)
            or record.get('output_dir') != str(output)
            or record.get('group_name') != 'Local\\CorrosionMAPDL_'+token
            or record.get('platform') != os.name
            or record.get('launcher_path') != str(LAUNCHER)):
        raise RuntimeError('监管记录身份或任务路径不匹配，拒绝停止。')
    pid = record.get('launcher_pid')
    if not isinstance(pid, int) or pid <= 0 or not isinstance(record.get('launcher_create_time'), (float, int)):
        raise RuntimeError('监管进程身份记录不完整，拒绝停止。')
    try:
        process = psutil.Process(pid)
        if abs(process.create_time()-record['launcher_create_time']) > .001:
            raise RuntimeError('监管进程身份不匹配（可能PID复用），拒绝停止。')
        args = process.cmdline()
        expected = [str(LAUNCHER), '--output', str(output), '--execution-id', token]
        if args[-len(expected):] != expected:
            raise RuntimeError('监管进程命令身份不匹配，拒绝停止。')
    except psutil.NoSuchProcess:
        pass  # A dead launcher does not imply its grandchildren have exited.


def stop_owned_execution(output: Path) -> dict:
    output = Path(output).resolve()
    path = output/RECORD_NAME
    if not path.exists():
        return {'state': 'not_started', 'verified_empty': True}
    record = None
    group = None
    try:
        record = json.loads(path.read_text(encoding='utf-8'))
        _validate_record(output, record)
        group = _open_group(record)
        result = _cleanup(group)
    except Exception as exc:
        result = {'state': 'failed', 'verified_empty': False, 'error': f'{type(exc).__name__}: {exc}'}
    finally:
        if group:
            try:
                group.close()
            except Exception as exc:
                result = {'state': 'failed', 'verified_empty': False, 'error': f'{type(exc).__name__}: {exc}'}
    if isinstance(record, dict):
        record['cleanup'] = result
        try:
            _persist(output, record)
        except Exception as exc:
            result = {**result, 'state': 'failed', 'persistence_error': f'{type(exc).__name__}: {exc}'}
    return result


class OwnedExecution:
    def __init__(self, process, group, output, record):
        self.process, self.group, self.output, self.record = process, group, output, record
        self.pid = process.pid
        self.cleanup = None
        self.group_closed = False

    def poll(self):
        return self.process.poll()

    def wait(self, timeout=None):
        return self.process.wait(timeout=timeout)

    def close(self):
        if self.cleanup and self.cleanup['verified_empty']:
            return self.cleanup
        try:
            if self.group_closed:
                self.group = _open_group(self.record)
                self.group_closed = False
            result = _cleanup(self.group)
            self.process.wait(timeout=5)
        except Exception as exc:
            result = {'state': 'failed', 'verified_empty': False, 'error': f'{type(exc).__name__}: {exc}'}
        try:
            self.group.close()
            self.group_closed = True
        except Exception as exc:
            result = {'state': 'failed', 'verified_empty': False, 'error': f'{type(exc).__name__}: {exc}'}
        self.cleanup = result
        self.record['cleanup'] = result
        _persist(self.output, self.record)
        return result

    kill = close
    terminate = close


def launch_owned(command, output: Path, stream, env=None) -> OwnedExecution:
    output = Path(output).resolve()
    if (output/RECORD_NAME).exists():
        raise ValueError('已有监管执行记录，拒绝复用输出目录。')
    token = uuid.uuid4().hex
    name = 'Local\\CorrosionMAPDL_'+token
    group = _WindowsGroup(name, create=True) if os.name == 'nt' else _PosixGroup()
    process = None
    record = None
    try:
        process = subprocess.Popen([sys.executable, '-u', str(LAUNCHER), '--output', str(output),
                                    '--execution-id', token], cwd=str(output), stdin=subprocess.PIPE,
                                   stdout=stream, stderr=subprocess.STDOUT, close_fds=True,
                                   start_new_session=os.name != 'nt', shell=False, env=env)
        group.assign(process)
        record = {'version': 1, 'state': 'grouped', 'platform': os.name, 'execution_id': token,
                  'group_name': name, 'output_dir': str(output), 'launcher_path': str(LAUNCHER),
                  'launcher_pid': process.pid, 'launcher_create_time': psutil.Process(process.pid).create_time(),
                  'crash_cleanup': 'kill_on_job_close' if os.name == 'nt' else 'not_guaranteed',
                  'command': list(command)}
        _persist(output, record)
        owner = OwnedExecution(process, group, output, record)
        request = {'go': token, 'command': list(command)}
        if env is not None:
            request['env'] = dict(env)
        process.stdin.write((json.dumps(request)+'\n').encode('utf-8'))
        process.stdin.flush()
        process.stdin.close()
        return owner
    except BaseException as primary:
        # Try every release even when an earlier cleanup step fails. Preserve the
        # startup exception; the real command cannot run before the persisted GO.
        errors = []
        actions = [group.terminate]
        if process is not None:
            if process.stdin and not process.stdin.closed:
                actions.append(process.stdin.close)
            actions.extend([lambda: process.kill() if process.poll() is None else None,
                            lambda: process.wait(timeout=5)])
        actions.append(group.close)
        for action in actions:
            try:
                action()
            except BaseException as exc:
                errors.append(f'{type(exc).__name__}: {exc}')
        if errors:
            primary.add_note('启动失败后的监管清理异常：'+'; '.join(errors))
        raise

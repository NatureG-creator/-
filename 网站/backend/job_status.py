"""跨进程串行更新任务状态，保留尚未完成的APDL停止请求。"""
from contextlib import contextmanager
import json
import os
from pathlib import Path

from .runner import _atomic_json


@contextmanager
def _status_lock(path):
    with path.with_name('status.guard').open('a+b') as stream:
        stream.seek(0,2)
        if stream.tell()==0:
            stream.write(b'\0')
            stream.flush()
        stream.seek(0)
        if os.name=='nt':
            import msvcrt
            msvcrt.locking(stream.fileno(),msvcrt.LK_LOCK,1)
        else:
            import fcntl
            fcntl.flock(stream,fcntl.LOCK_EX)
        try:
            yield
        finally:
            stream.seek(0)
            if os.name=='nt': msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
            else: fcntl.flock(stream,fcntl.LOCK_UN)


def update_job_status(path,changes,*,preserve_stop=True):
    path=Path(path)
    with _status_lock(path):
        current=json.loads(path.read_text(encoding='utf-8'))
        changes=dict(changes)
        if preserve_stop and current.get('kind')=='apdl_tension' and current.get('state')=='stop_failed':
            for key in ('state','error','stop_error','stop_persistence_error'):
                changes.pop(key,None)
        current.update(changes)
        _atomic_json(path,current)
        return current

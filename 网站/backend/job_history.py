"""运行记录显示与删除；不更改计算输入、成果或检查点内容。"""
from contextlib import contextmanager, nullcontext
from functools import wraps
import json
import shutil
import time

from .job_status import _status_lock
from .runner import _atomic_json
from .system_info import json_record, process_alive

ENDED = {'completed', 'failed', 'interrupted', 'cancelled', 'canceled', 'stopped'}


@contextmanager
def history_guard(service):
    # Keep the guard outside a task directory so Windows can remove that task.
    with service._job_lock, _status_lock(service.runtime / 'history.json'):
        yield


def history_guarded(method):
    @wraps(method)
    def guarded(service, *args, **kwargs):
        with history_guard(service):
            return method(service, *args, **kwargs)
    return guarded


def hidden(folder):
    return json_record(folder / 'history.json', {}).get('hidden') is True


def list_jobs(service, *, include_hidden=True, limit=100):
    folders = [p for p in (service.runtime / 'jobs').iterdir()
               if p.is_dir() and len(p.name) == 16 and
               all(c in '0123456789abcdef' for c in p.name) and
               (p / 'status.json').is_file() and (include_hidden or not hidden(p))]
    folders.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    result = []
    for folder in folders:
        try:
            result.append(service.get_job(folder.name))
        except FileNotFoundError:
            continue  # A concurrent confirmed deletion is absent from history.
        if len(result) >= limit:
            break
    return result


def _editable_folder(service, job_id):
    service.validate_id(job_id)
    root = (service.runtime / 'jobs').resolve()
    folder = root / job_id
    if folder.resolve() != folder or folder.is_symlink():
        raise ValueError('任务目录是链接，不能管理或删除，请先检查目录')
    raw = json_record(folder / 'status.json')
    if raw is None:
        raise FileNotFoundError('任务不存在')
    # Do not turn an active-looking orphan into an ended job as a deletion side effect.
    if raw.get('state') not in ENDED:
        raise ValueError('请先停止任务并刷新，确认任务已结束后再管理记录')
    state = service.get_job(job_id)
    process = service.processes.get(job_id)
    try:
        locked_pid = int((folder / 'worker.lock').read_text(encoding='ascii'))
    except FileNotFoundError:
        locked_pid = None
    except (OSError, ValueError) as exc:
        raise ValueError('工作进程锁无法确认，请先检查任务') from exc
    if (state.get('state') not in ENDED or raw.get('export_pending') or state.get('export_pending') or
            process_alive(raw.get('pid')) or process_alive(locked_pid) or
            process is not None and process.poll() is None or
            job_id in service.pending_jobs or job_id in service._launching_jobs):
        raise ValueError('任务仍在运行、排队、清理或导出中，暂不能管理记录')
    if raw.get('kind') == 'apdl_tension':
        for name in ('mapdl_process.json', 'mapdl_execution.json'):
            record = json_record(folder / 'outputs' / name, {})
            cleanup = record.get('cleanup') or {}
            if (process_alive(record.get('pid')) or record.get('state') in {'running', 'starting'} and
                    cleanup.get('verified_empty') is not True):
                raise ValueError('APDL 求解进程尚未确认结束，请先停止并确认清理完成')
    return folder


def set_hidden(service, job_id, value):
    with history_guard(service):
        folder = _editable_folder(service, job_id)
        _atomic_json(folder / 'history.json', {'hidden': bool(value), 'updated_at': time.time()})
        return {'id': job_id, 'history_hidden': bool(value)}


def _references(value, job_id):
    if isinstance(value, dict):
        return any(_references(item, job_id) for item in value.values())
    if isinstance(value, list):
        return any(_references(item, job_id) for item in value)
    if isinstance(value, str):
        normalized = value.replace('\\', '/').casefold().rstrip('/')
        return value == job_id or f'/jobs/{job_id}/' in normalized + '/'
    return False


def delete_jobs(service, job_ids, confirmation):
    if (not isinstance(job_ids,list) or not job_ids or
            any(not isinstance(item,str) for item in job_ids) or
            len(set(job_ids)) != len(job_ids) or confirmation != job_ids):
        raise ValueError('批量删除需要确认所选完整任务编号')
    with history_guard(service):
        for job_id in job_ids:
            delete_job(service, job_id, job_id, preflight=True, guarded=True)
        deleted=[]
        for job_id in job_ids:
            try:
                delete_job(service, job_id, job_id, guarded=True)
                deleted.append(job_id)
            except OSError as exc:
                return {'deleted_ids':deleted,'error':str(exc)}
        return {'deleted_ids':deleted}


def delete_job(service, job_id, confirmation, *, preflight=False, guarded=False):
    service.validate_id(job_id)
    if confirmation != job_id:
        raise ValueError('永久删除需要确认完整任务编号')
    with nullcontext() if guarded else history_guard(service):
        folder = _editable_folder(service, job_id)
        for category, label in (('jobs', '任务'), ('batches', '批次')):
            for other in (service.runtime / category).iterdir():
                if not other.is_dir() or other.resolve() == folder:
                    continue
                records = list(other.glob('*.json'))
                if category == 'jobs' and (other / 'outputs' / 'summary.json').is_file():
                    records.append(other / 'outputs' / 'summary.json')
                for path in records:
                    try:
                        record = json.loads(path.read_text(encoding='utf-8-sig'))
                    except (OSError, ValueError) as exc:
                        raise ValueError(f'{label} {other.name} 的记录无法读取，不能确认引用关系，暂不删除') from exc
                    if _references(record, job_id):
                        raise ValueError(f'被{label} {other.name} 引用，不能永久删除；可以隐藏记录')
        if preflight:
            return {'id':job_id, 'deletable':True}
        shutil.rmtree(folder)
        service.processes.pop(job_id, None)
        return {'id': job_id, 'deleted': True}

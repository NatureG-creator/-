"""任务显示名称与成果副本；不修改冻结的科学参数或检查点。"""

import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

from .job_status import _status_lock
from .runner import _atomic_json
from .system_info import json_record


def validate_task_io(payload, runtime):
    name = payload.get('name', payload.get('case_name', ''))
    directory = payload.get('export_directory', '')
    if not isinstance(name, str) or len(name) > 100 or any(ord(c) < 32 for c in name):
        raise ValueError('任务名称必须是100字以内的单行文字')
    if not isinstance(directory, str) or '\0' in directory:
        raise ValueError('导出目录必须是本机绝对路径')
    directory = directory.strip()
    if directory:
        target = Path(directory).expanduser()
        if not target.is_absolute():
            raise ValueError('导出目录必须是本机绝对路径')
        if target.resolve().is_relative_to(Path(runtime).resolve()):
            raise ValueError('导出位置不能位于网站内部任务目录中')
        directory = str(target.resolve())
    return {'name': name.strip(), 'export_directory': directory}


def job_io(folder, spec):
    settings = json_record(folder / 'task_io.json', {})
    return dict(settings, name=settings.get('name') or spec.get('case_name', ''))


def configure_job(service, job_id, payload):
    state = service.get_job(job_id)
    folder = service.runtime / 'jobs' / job_id
    with _status_lock(folder / 'status.json'):
        current = job_io(folder, state['spec'])
        fields = {key: payload[key] for key in ('name', 'export_directory') if key in payload}
        current.update(validate_task_io(dict(current, **fields), service.runtime))
        _atomic_json(folder / 'task_io.json', current)
    return service.get_job(job_id)


def export_outputs(folder, runtime):
    """Copy finished outputs to a new folder. A copy failure never invalidates a solve."""
    settings = job_io(folder, json_record(folder / 'spec.json', {}))
    if not settings.get('export_directory'):
        return None
    destination = None
    started = time.perf_counter()
    try:
        settings.update(validate_task_io(settings, runtime))
        parent = Path(settings['export_directory'])
        parent.mkdir(parents=True, exist_ok=True)
        name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', settings['name']).strip(' .') or '成果'
        # Prefix keeps Windows reserved names such as CON valid; IDs retain provenance.
        destination = parent / f"成果_{name[:70]}_{folder.name}_{uuid.uuid4().hex[:8]}"
        destination.mkdir()
        outputs = folder / 'outputs'
        count = 0
        if outputs.is_symlink():
            raise ValueError('成果目录不能是符号链接')
        for source in sorted(outputs.rglob('*')):
            if source.is_symlink() or not source.resolve().is_relative_to(outputs.resolve()):
                raise ValueError('成果中包含指向外部的链接，已停止复制')
            if not source.is_file() or source.suffix == '.tmp':
                continue
            target = destination / 'outputs' / source.relative_to(outputs)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            count += 1
        for relative in ('spec.json', 'status.json', 'worker.log'):
            source = folder / relative
            if source.is_file():
                shutil.copy2(source, destination / relative)
        record = {'state': 'completed', 'path': str(destination), 'file_count': count,
                  'exported_at': time.time(), 'elapsed_seconds': round(time.perf_counter() - started, 3)}
        _atomic_json(destination / 'task_io.json', dict(settings, last_export=record))
    except Exception as exc:
        record = {'state': 'failed', 'error': str(exc),
                  'partial_path': str(destination) if destination else None}
    record.update(exported_at=time.time(), elapsed_seconds=round(time.perf_counter() - started, 3))
    with _status_lock(folder / 'status.json'):
        current = json_record(folder / 'task_io.json', settings)
        current['last_export'] = record
        _atomic_json(folder / 'task_io.json', current)
    return record


def export_job(service, job_id):
    state = service.get_job(job_id)
    if state['state'] not in {'completed', 'failed', 'interrupted', 'cancelled', 'stopped'}:
        raise ValueError('请等待任务结束后导出，避免复制仍在写入的文件')
    if state.get('export_pending'):
        raise ValueError('正在自动导出，请等待本次复制结束')
    if not state['task_io'].get('export_directory'):
        raise ValueError('请先填写或选择导出目录')
    folder = service.runtime / 'jobs' / job_id
    result = export_outputs(folder, service.runtime)
    from .job_status import update_job_status
    update_job_status(folder / 'status.json', {'export_pending': False})
    return result


def choose_directory():
    script = """import json
import tkinter as tk
from tkinter.filedialog import askdirectory
root = tk.Tk()
root.withdraw()
root.attributes('-topmost', True)
try:
    value = askdirectory(parent=root, title='选择成果导出目录', mustexist=False)
    print(json.dumps({'path': value, 'cancelled': not bool(value)}, ensure_ascii=True))
finally:
    root.destroy()
"""
    result = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True,
                            timeout=180, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    if result.returncode:
        raise ValueError('本机目录选择器不可用，请直接在输入框填写完整目录路径')
    import json
    return json.loads(result.stdout)

"""Project folders for saved copies of workbench task outputs."""
from __future__ import annotations

import shutil
from pathlib import Path

from .runner import _atomic_json


def _root(service):
    path = service.runtime / 'project_library'
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def _directory(service, relative=''):
    root = _root(service)
    if not isinstance(relative, str) or '\0' in relative:
        raise ValueError('项目文件夹路径无效')
    target = (root / relative).resolve()
    if not target.is_relative_to(root):
        raise ValueError('项目文件夹路径无效')
    return root, target


def _unused_path(folder, name, suffix=''):
    candidate = folder / name
    stem, extension = candidate.stem, candidate.suffix
    index = 2
    while candidate.exists() or candidate.with_name(candidate.name + suffix).exists():
        candidate = folder / f'{stem}_{index}{extension}'
        index += 1
    return candidate


def library_list(service, relative=''):
    root, folder = _directory(service, relative)
    if not folder.is_dir():
        raise FileNotFoundError('项目文件夹不存在')
    folders, files = [], []
    for item in sorted(folder.iterdir(), key=lambda value: (not value.is_dir(), value.name.casefold())):
        if item.is_symlink() or item.name.endswith('.source.json'):
            continue
        record = dict(name=item.name, path=item.relative_to(root).as_posix())
        if item.is_dir():
            folders.append(record)
        elif item.is_file():
            files.append(dict(record, bytes=item.stat().st_size, extension=item.suffix.lower()))
    return dict(folder=folder.relative_to(root).as_posix() if folder != root else '',
                folders=folders, files=files)


def create_folder(service, payload):
    parent = payload.get('parent', '')
    name = payload.get('name')
    if not isinstance(name, str) or not name.strip() or name.strip() in {'.', '..'} or any(c in name for c in '/\\'):
        raise ValueError('文件夹名称不能为空，也不能包含路径分隔符')
    _, target = _directory(service, parent)
    target.mkdir(parents=True, exist_ok=True)
    created = target / name.strip()
    created.mkdir(exist_ok=False)
    return dict(name=created.name, path=created.relative_to(_root(service)).as_posix())


def save_task_outputs(service, payload):
    job_id = service.validate_id(payload.get('job_id'))
    job = service.get_job(job_id)
    if job.get('state') not in {'completed', 'failed', 'interrupted', 'stopped', 'cancelled'}:
        raise ValueError('任务结束后才能归档成果')
    names = payload.get('files')
    if not isinstance(names, list) or not names or any(not isinstance(name, str) for name in names):
        raise ValueError('请选择至少一个成果文件')
    _, destination = _directory(service, payload.get('folder', ''))
    if not destination.is_dir():
        raise FileNotFoundError('目标项目文件夹不存在')
    source_root = (service.runtime / 'jobs' / job_id / 'outputs').resolve()
    if any((item.get('name') == 'benchmark_bundle.zip' and item.get('on_demand'))
           for item in job.get('files', []) if isinstance(item, dict)):
        from .benchmark_archive import ensure_benchmark_bundle
        ensure_benchmark_bundle(service.runtime / 'jobs' / job_id)
    saved = []
    for name in dict.fromkeys(names):
        candidate = source_root / name
        if candidate.is_symlink():
            raise ValueError('不能归档符号链接')
        source = candidate.resolve()
        if not source.is_relative_to(source_root) or not source.is_file():
            raise FileNotFoundError(f'任务成果不存在：{name}')
        target = _unused_path(destination, source.name, '.source.json')
        shutil.copy2(source, target)
        record = dict(source_job_id=job_id, source_file=name, task_name=job.get('display_name') or job.get('case_name') or job_id,
                      state=job.get('state'), data_quality='complete' if job.get('state') == 'completed' else 'partial')
        _atomic_json(target.with_name(target.name + '.source.json'), record)
        saved.append(dict(name=target.name, path=target.relative_to(_root(service)).as_posix(), bytes=target.stat().st_size))
    return dict(files=saved, folder=destination.relative_to(_root(service)).as_posix())


def library_file(service, relative):
    root, _ = _directory(service)
    if not isinstance(relative, str):
        raise ValueError('文件路径无效')
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or not path.is_file() or path.name.endswith('.source.json'):
        raise FileNotFoundError('项目文件不存在')
    return path


def import_library_file(service, payload):
    path = library_file(service, payload.get('path'))
    with path.open('rb') as stream:
        return service.upload(path.name, stream, path.stat().st_size)


def save_uploaded_file(service, payload):
    upload_id = service.validate_id(payload.get('upload_id'), 32)
    record, source = service.get_upload(upload_id)
    _, destination = _directory(service, payload.get('folder', ''))
    if not destination.is_dir():
        raise FileNotFoundError('目标项目文件夹不存在')
    target = _unused_path(destination, Path(record['name']).name)
    shutil.copy2(source, target)
    return dict(name=target.name, path=target.relative_to(_root(service)).as_posix(), bytes=target.stat().st_size)

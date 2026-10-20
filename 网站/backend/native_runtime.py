"""Opt-in process-local native runtime loading; never changes PATH or the system."""
import ctypes
import hashlib
import os
import platform
from pathlib import Path

_directory_handles = []
_library_handles = []
_loaded = {}
_last_status = {'state':'not_configured', 'path':None, 'sha256':None}


def load_configured_runtime():
    global _last_status
    configured = os.environ.get('CORROSION_NATIVE_DLL_DIR', '').strip()
    result = {'state':'not_configured', 'directory':configured or None, 'path':None, 'sha256':None}
    if not configured:
        _last_status = result
        return dict(result)
    if platform.system() != 'Windows':
        result.update(state='unsupported', error='该配置仅支持 Windows。')
        _last_status = result
        return dict(result)
    try:
        directory = Path(configured)
        if not directory.is_absolute() or not directory.is_dir():
            raise ValueError('CORROSION_NATIVE_DLL_DIR 必须是已存在的绝对目录。')
        directory = directory.resolve()
        library = directory/'MSVCP140.dll'
        result.update(directory=str(directory), path=str(library))
        if not library.is_file():
            raise FileNotFoundError('配置目录中不存在 MSVCP140.dll。')
        result['sha256'] = hashlib.sha256(library.read_bytes()).hexdigest()
        key=(str(library), result['sha256'])
        if key not in _loaded:
            handle=os.add_dll_directory(str(directory))
            _directory_handles.append(handle)
            _library_handles.append(ctypes.WinDLL(str(library)))
            _loaded[key] = True
        result['state']='loaded'
    except Exception as exc:
        result.update(state='failed', error=f'{type(exc).__name__}: {exc}')
    _last_status = result
    return dict(result)


def configured_runtime_status():
    return dict(_last_status)

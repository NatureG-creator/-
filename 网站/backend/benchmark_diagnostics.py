"""Read-only environment diagnostics; importing this module never imports Taichi."""
import importlib.metadata
import json
import os
import platform
import struct
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from .native_runtime import configured_runtime_status


def normalize_probe(name, result, elapsed):
    result = dict(result)
    result.update(name=name, elapsed_seconds=round(elapsed, 3))
    if name == 'gpu' and result.get('actual_arch', '').lower() in ('cpu', 'x64', 'arm64'):
        result.update(state='unavailable', message='GPU 请求实际回退至 CPU，GPU 不可用。')
    return result


def _run_probe(name, output_dir, timeout):
    started = time.monotonic()
    log_path = output_dir / f'{name}.log'
    with log_path.open('w', encoding='utf-8') as log:
        process = subprocess.Popen([sys.executable, str(Path(__file__).with_name('benchmark_probe.py')), name], stdout=log, stderr=subprocess.STDOUT, env={**os.environ, 'PYTHONIOENCODING': 'utf-8'}, start_new_session=os.name != 'nt', creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0)
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            if os.name == 'nt':
                try:
                    subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], stdout=log, stderr=subprocess.STDOUT, timeout=10, check=False)
                except (OSError, subprocess.TimeoutExpired) as exc:
                    log.write(f'进程树终止命令异常：{exc}\\n')
            else:
                import signal
                os.killpg(process.pid, signal.SIGKILL)
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
            log.write('\n诊断超时，已终止诊断进程树。\n')
            return normalize_probe(name, {'state':'timeout', 'message':f'超过 {timeout:g} 秒；详见 {name}.log。', 'log':log_path.name}, time.monotonic()-started)
    contents = log_path.read_text(encoding='utf-8', errors='replace')
    result = {'state':'failed', 'message':f'子进程退出（代码 {process.returncode}），未返回有效结果；详见 {name}.log。'}
    for line in contents.splitlines():
        if line.startswith('DIAGNOSTICS_RESULT='):
            try:
                result = json.loads(line.split('=', 1)[1])
            except (ValueError, TypeError):
                pass
    result['log'] = log_path.name
    return normalize_probe(name, result, time.monotonic()-started)


def _package(name):
    try:
        dist = importlib.metadata.distribution(name)
        return {'installed':True, 'version':dist.version, 'location':str(dist.locate_file('')), 'requires_python':dist.metadata.get('Requires-Python')}
    except importlib.metadata.PackageNotFoundError:
        return {'installed':False, 'version':None}


def _pe_imports(path):
    data = path.read_bytes()
    pe = struct.unpack_from('<I', data, 0x3c)[0]
    if data[pe:pe+4] != b'PE\0\0':
        raise ValueError('不是 PE 文件')
    count = struct.unpack_from('<H', data, pe+6)[0]
    optional_size = struct.unpack_from('<H', data, pe+20)[0]
    opt = pe+24
    directory = opt + (112 if struct.unpack_from('<H', data, opt)[0] == 0x20b else 96)
    import_rva = struct.unpack_from('<I', data, directory+8)[0]
    sections = []
    for index in range(count):
        at = opt+optional_size+index*40
        virtual_size, virtual_address, raw_size, raw_ptr = struct.unpack_from('<IIII', data, at+8)
        sections.append((virtual_address, max(virtual_size, raw_size), raw_ptr))
    def offset(rva):
        for address, size, raw in sections:
            if address <= rva < address+size:
                return raw+rva-address
        raise ValueError('无法定位 PE RVA')
    imports = []
    cursor = offset(import_rva)
    while any(data[cursor:cursor+20]):
        name_rva = struct.unpack_from('<I', data, cursor+12)[0]
        begin = offset(name_rva)
        imports.append(data[begin:data.index(b'\0', begin)].decode('ascii'))
        cursor += 20
    return imports


def inspect_native_dependencies():
    result = {'status':'unknown', 'extension':None, 'imports':[], 'missing':[], 'note':'仅检查直接 PE 依赖文件；不能排除传递依赖、DLL 版本或加载器策略问题。未定位缺失项时不能认定 MSVC 是根因。'}
    if os.name != 'nt':
        result['note'] = '当前系统不支持 Windows PE DLL 检查。'
        return result
    try:
        dist = importlib.metadata.distribution('taichi')
        extensions = [Path(dist.locate_file(f)) for f in (dist.files or []) if Path(str(f)).name.startswith('taichi_python') and str(f).endswith('.pyd')]
        if not extensions:
            return result
        extension = extensions[0]
        result['extension'] = str(extension)
        imports = _pe_imports(extension)
        directories = [extension.parent, Path(sys.executable).parent, Path(sys.base_prefix), Path(os.environ.get('SystemRoot', 'C:/Windows'))/'System32']
        directories += [Path(p) for p in os.environ.get('PATH','').split(os.pathsep) if p]
        for name in imports:
            virtual = name.lower().startswith(('api-ms-', 'ext-ms-'))
            found = next((str(d/name) for d in directories if (d/name).is_file()), None)
            result['imports'].append({'name':name, 'path':found, 'status':'virtual_api_set' if virtual else ('found' if found else 'not_found_in_checked_paths')})
            if not virtual and found is None:
                result['missing'].append(name)
        result['status'] = 'missing_candidates' if result['missing'] else 'direct_dependencies_found'
    except Exception as exc:
        result['error'] = f'{type(exc).__name__}: {exc}'
    return result


def run_diagnostics(output_dir: Path, timeout_seconds=30):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    timeout = max(0.1, min(float(timeout_seconds), 30.0))
    packages = {name:_package(name) for name in ('taichi','numpy')}
    checks = [_run_probe(name, output_dir, timeout) for name in ('import','cpu')]
    native = inspect_native_dependencies()
    recommendations = []
    if not packages['taichi']['installed']:
        recommendations.append(f'当前解释器未检测到 Taichi：{sys.executable}。请先核对网站实际使用的 Python 环境，再在该环境安装依赖。')
    if checks[0]['state'] != 'passed':
        recommendations.append('先查看 import.log 中完整异常，并核对报告的 Python 路径、位数与 Taichi 版本；原生扩展未导入前，CPU 结果不能用于性能比较。')
        if native['missing']:
            recommendations.append('直接依赖检查未在所查路径找到：'+ '、'.join(native['missing']) +'。这些是缺失候选，请核对对应官方运行库/软件来源及传递依赖，勿从陌生网站下载 DLL。')
        else:
            recommendations.append('尚未定位具体缺失 DLL；需要结合完整加载错误检查传递依赖、二进制兼容性与运行库，不能据此认定 MSVC 缺失。')
    if checks[1]['state'] != 'passed':
        recommendations.append('Taichi CPU 未通过最小计算验证；查看 cpu.log 后再运行腐蚀性能基准。')
    result = {'kind':'diagnostics', 'configured_runtime':configured_runtime_status(), 'created_at':datetime.now(timezone.utc).isoformat(), 'python':{'executable':sys.executable, 'version':platform.python_version(), 'bits':struct.calcsize('P')*8}, 'packages':packages, 'hardware':{'logical_cpu_count':os.cpu_count() or 1, 'machine':platform.machine(), 'platform':platform.platform()}, 'checks':checks, 'native_dependencies':native, 'recommendations':recommendations, 'scope_note':'诊断仅执行独立子进程中的 Taichi 导入与 CPU 最小 kernel，不代表腐蚀算法正确性或性能。各项独立超时最多 30 秒。'}
    (output_dir/'diagnostics.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result

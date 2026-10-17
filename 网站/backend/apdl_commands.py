"""Frozen APDL input revisions. Edited decks do not inherit parameter validation."""
from pathlib import Path
import difflib
import hashlib
import json
import re
import shutil
import time
import zipfile

from .runner import _atomic_json
from .system_info import sha256

EDITABLE = ('main.inp', 'materials.mac', 'boundary.mac', 'solve.mac', 'post.mac')
MAX_DECK_BYTES = 2_000_000


def _source(service, job_id):
    service.validate_id(job_id)
    state = service.get_job(job_id)
    if state.get('kind') != 'apdl_tension' or state.get('state') not in {'completed', 'failed', 'interrupted', 'stopped'}:
        raise ValueError('请选择已结束且已生成输入包的APDL任务')
    root = service.runtime / 'jobs' / job_id / 'outputs'
    if not all((root / name).is_file() for name in EDITABLE):
        raise ValueError('源任务缺少完整的APDL命令文件，请先生成模型')
    return state, root


def _package(root):
    names = set(EDITABLE) | {'nodes.dat', 'elements.dat', 'mesh_quality.mac',
        'mesh_self_check.mac', 'boundary_self_check.mac', 'run_apdl.cmd',
        'surface_inputs.npz', 'top_depth.csv', 'bottom_depth.csv',
        'remaining_thickness.csv', 'geometry_preview.png'}
    records = []
    for name in sorted(names):
        path = root / name
        if path.is_file():
            if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
                raise ValueError('源输入包含目录外文件')
            records.append(dict(path=path, input_path='inputs/' + name,
                                sha256=sha256(path), name=name))
    return records


def command_snapshot(service, job_id):
    state, root = _source(service, job_id)
    files = {}
    for name in EDITABLE:
        if (root / name).stat().st_size > MAX_DECK_BYTES:
            raise ValueError('命令文件超过2MB编辑上限')
        files[name] = (root / name).read_text(encoding='utf-8-sig')
    hashes = {item['name']: item['sha256'] for item in _package(root)}
    revision = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    return dict(source_job_id=job_id, files=files, revision=revision,
                input_hashes=hashes, execution_mode=state.get('spec', {}).get('execution_mode', 'parameters'))


def check_commands(service, payload):
    source = command_snapshot(service, payload.get('source_job_id'))
    if payload.get('source_revision') != source['revision']:
        raise ValueError('源输入包版本已变化，请重新载入命令流')
    files = payload.get('command_files')
    if not isinstance(files, dict) or set(files) != set(EDITABLE):
        raise ValueError('命令文件必须恰为main/materials/boundary/solve/post五个文件')
    if any(not isinstance(text, str) or not text.strip() or '\0' in text for text in files.values()):
        raise ValueError('命令文件必须是非空且不含NUL的文本')
    if sum(len(text.encode('utf-8')) for text in files.values()) > MAX_DECK_BYTES:
        raise ValueError('五个命令文件合计不能超过2MB')
    warnings, changes = [], []
    available = set(source['input_hashes'])
    for name, text in files.items():
        for line_number, raw in enumerate(text.splitlines(), 1):
            command = raw.split('!')[0].strip()
            if not command:
                continue
            parts = [part.strip().strip("'\"") for part in command.split(',')]
            if parts[0].upper() == '/INPUT':
                stem = parts[1] if len(parts) > 1 else ''
                extension = parts[2] if len(parts) > 2 else ''
                target = stem + ('.' + extension if extension else '')
                if (not re.fullmatch(r'[A-Za-z0-9_.-]+', target)
                        or target not in available or any(parts[3:])):
                    raise ValueError(f'{name}:{line_number} /INPUT必须引用包内完整文件：{target}')
            if parts[0].upper() in {'/SYS', '/SYP', '/CWD', '*CFOPEN', '*CREATE', '*USE'}:
                warnings.append(f'{name}:{line_number} {parts[0]}有文件或系统副作用，请检查目标；本工具不是沙箱')
        if text != source['files'][name]:
            changes.append(dict(file=name, diff=''.join(difflib.unified_diff(
                source['files'][name].splitlines(keepends=True), text.splitlines(keepends=True),
                fromfile='original/' + name, tofile='edited/' + name))))
    if not any(re.search(r'^\s*SOLVE\s*(?:!.*)?$', text, re.M | re.I) for text in files.values()):
        warnings.append('未识别独立SOLVE命令；本检查不能证明求解会执行')
    return dict(state='structure_checked', changes=changes, warnings=warnings,
                source_revision=source['revision'],
                note='仅检查包结构和引用，不保证APDL语法、材料、边界或物理正确；原参数不代表编辑后模型')


def prepare_custom_apdl(service, payload):
    report = check_commands(service, payload)
    state, root = _source(service, payload['source_job_id'])
    mode = payload.get('run_mode', 'build')
    if mode not in {'build', 'solve'}:
        raise ValueError('run_mode只能是build或solve')
    if mode == 'solve':
        from .apdl_solver import mapdl_capabilities
        if not mapdl_capabilities().get('available'):
            raise ValueError('未发现MAPDL，可先另存输入包')
    from .apdl_geometry import normalise_options
    options = dict(state['spec']['options'])
    for key in ('cores', 'timeout_seconds'):
        if key in payload.get('options', {}):
            options[key] = payload['options'][key]
    options = normalise_options(options)
    spec = dict(kind='apdl_tension', execution_mode='custom_commands', run_mode=mode,
        source_job_id=payload['source_job_id'], options=options,
        case_name=str(payload.get('case_name') or '自定义APDL命令')[:100],
        command_files=dict(payload['command_files']), command_check=report,
        source_revision=report['source_revision'], frozen_package=[],
        inherited_parameters_note='options仅用于来源记录及核数/超时控制，不能说明编辑后命令的实际物理设置')
    records = _package(root)
    spec['frozen_package'] = [{key: item[key] for key in ('name', 'input_path', 'sha256')} for item in records]
    return spec, records


def run_custom_apdl(spec, job_dir, progress=None):
    job_dir = Path(job_dir)
    output = job_dir / 'outputs'
    output.mkdir(exist_ok=True)
    started = time.perf_counter()
    result = dict(kind='apdl_tension', execution_mode='custom_commands',
        source_job_id=spec['source_job_id'], build_state='pending', solve_state='not_requested',
        validation_state='unverified_custom_commands',
        warnings=['手工命令可能改变材料、几何、加载和结果格式；未套用原参数物理校核'],
        command_check=spec['command_check'])
    try:
        for item in spec['frozen_package']:
            source = (job_dir / item['input_path']).resolve()
            if not source.is_relative_to((job_dir / 'inputs').resolve()) or sha256(source) != item['sha256']:
                raise ValueError('冻结命令输入包已变化或越界')
            shutil.copy2(source, output / item['name'])
        for name, text in spec['command_files'].items():
            (output / name).write_text(text, encoding='utf-8', newline='\n')
        _atomic_json(output / 'command_revision.json', dict(
            source_job_id=spec['source_job_id'], source_revision=spec['source_revision'],
            check=spec['command_check'], execution_mode='custom_commands',
            files={name: sha256(output / name) for name in EDITABLE}))
        with zipfile.ZipFile(output / 'apdl_custom_input.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(output.iterdir()):
                if path.is_file() and path.suffix != '.zip':
                    archive.write(path, path.name)
        result['build_state'] = 'built'
        if spec['run_mode'] == 'solve':
            from .apdl_solver import run_mapdl
            result['solve_state'] = 'running'
            result['solver'] = run_mapdl(output, spec['options'], progress=progress)
            result['solve_state'] = 'process_finished'
    except Exception as exc:
        result.update(error=str(exc), solve_state='failed' if spec['run_mode'] == 'solve' else 'not_requested')
        raise
    finally:
        from .apdl_analysis import diagnose_output
        result['solver_diagnosis'] = diagnose_output(output)
        result['elapsed_seconds'] = time.perf_counter() - started
        _atomic_json(output / 'summary.json', result)
    return result

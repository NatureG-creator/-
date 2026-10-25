"""Validate full worker identity before callers may stop an inherited process."""
import math
import os
from pathlib import Path

import psutil


def _same_directory(value, expected):
    if not isinstance(value, (str, os.PathLike)) or not value:
        return False
    candidate=Path(value)
    return candidate.is_absolute() and os.path.normcase(str(candidate.resolve())) == os.path.normcase(str(Path(expected).resolve()))


def verify_worker_process(job_id: str, state: dict, job_dir: Path, runtime: Path, root: Path) -> psutil.Process:
    """Read-only identity check. Rejection never signals or kills a process."""
    try:
        pid=state.get('pid')
        if type(pid) is not int or pid <= 0:
            raise ValueError('任务缺少有效的正整数 PID。')
        if int((Path(job_dir)/'worker.lock').read_text(encoding='ascii').strip()) != pid:
            raise ValueError('worker.lock 与任务 PID 不一致。')
        recorded=state.get('process_created_at')
        if isinstance(recorded,bool) or not isinstance(recorded,(int,float)) or not math.isfinite(recorded):
            raise ValueError('缺少有效的进程创建时间，无法排除 PID 被复用。')
        process=psutil.Process(pid)
        actual=process.create_time()
        if not math.isfinite(actual) or abs(actual-recorded)>0.01:
            raise ValueError('进程创建时间与任务记录不一致，可能是 PID 被复用。')
        command=process.cmdline()
        expected=['-m','backend.worker',job_id]
        if not any(command[index:index+3]==expected for index in range(len(command)-2)):
            raise ValueError('进程命令行与指定 worker 任务不一致。')
        from .engine_releases import worker_root
        if not _same_directory(process.cwd(),worker_root(job_dir,runtime,root)):
            raise ValueError('进程工作目录与网站根目录不一致。')
        if not _same_directory(process.environ().get('CORROSION_RUNTIME_DIR'),runtime):
            raise ValueError('进程 CORROSION_RUNTIME_DIR 与当前运行目录不一致。')
        return process
    except (OSError, psutil.Error, ValueError, TypeError, AttributeError) as exc:
        raise ValueError(f'进程身份核验失败：{exc}') from exc


def stop_verified_process(process) -> None:
    """Caller must first obtain this object through verify_worker_process."""
    try:
        children=process.children(recursive=True)
    except psutil.NoSuchProcess:
        return
    targets=list(reversed(children))+[process]
    stopped=[]
    for target in targets:
        try:
            target.kill()
            stopped.append(target)
        except psutil.NoSuchProcess:
            pass
    if stopped:
        _, alive=psutil.wait_procs(stopped,timeout=5)
        if alive:
            raise psutil.TimeoutExpired(5,pid=alive[0].pid)

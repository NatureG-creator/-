"""只同步本网站目录，禁止夹带其他暂存文件和运行数据。"""

from __future__ import annotations

import subprocess
import threading
import shutil
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_LOCK = threading.Lock()
_REPO_ENV_NAMES = ("CORROSION_GIT_ROOT", "GIT_REPO_ROOT")
_SIBLING_REPO_NAMES = ("corrosion-sync", "corrosion-workbench")


def _repository_context() -> tuple[Path, str]:
    """Return the Git root and the website path inside it.

    The packaged website can run outside a checkout. In that case prefer an
    explicit repository path, then the nearby sync checkouts used by the local
    launcher. The returned relative path is always POSIX-style for Git pathspecs.
    """
    candidates: list[Path] = []
    for name in _REPO_ENV_NAMES:
        value = os.environ.get(name, "").strip().strip('"')
        if value:
            candidates.append(Path(value))
    for parent in (ROOT, *ROOT.parents):
        if (parent / ".git").exists():
            candidates.append(parent)
        for name in _SIBLING_REPO_NAMES:
            candidates.append(parent / name)

    seen: set[Path] = set()
    for candidate in candidates:
        try:
            repo = candidate.resolve()
        except OSError:
            continue
        if repo in seen or not (repo / ".git").exists():
            continue
        seen.add(repo)
        try:
            relative = ROOT.resolve().relative_to(repo).as_posix()
        except ValueError:
            mapped = repo / ROOT.name
            if not mapped.is_dir():
                continue
            relative = ROOT.name
        return repo, relative
    raise ValueError(
        "当前网站目录未关联Git仓库；请设置 CORROSION_GIT_ROOT 为包含 .git 的仓库目录"
    )


def _git(*arguments: str, timeout: int = 30, cwd: Path | None = None):
    executable = shutil.which("git")
    if not executable and os.name == "nt":
        candidates = [
            Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Git/cmd/git.exe",
            Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/native/git/cmd/git.exe"]
        executable = next((str(path) for path in candidates if path.is_file()), None)
    if not executable:
        raise ValueError("未找到Git，请安装Git并登录GitHub后再同步")
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    result = subprocess.run([executable, "-C", str(cwd or ROOT), *arguments],
                            capture_output=True, text=True, encoding="utf-8", errors="replace",
                            timeout=timeout, creationflags=flags)
    if result.returncode:
        raise ValueError((result.stderr or result.stdout).strip() or "Git命令失败")
    return result.stdout.rstrip("\r\n")


def sync_status() -> dict:
    try:
        repo, relative = _repository_context()
        def git(*arguments: str, timeout: int = 30):
            return _git(*arguments, timeout=timeout, cwd=repo)
        repo = Path(git("rev-parse", "--show-toplevel"))
        changes = git("status", "--short", "--", ":(top)" + relative)
        try:
            ahead = int(git("rev-list", "--count", "@{upstream}..HEAD"))
        except (ValueError, OSError, subprocess.TimeoutExpired):
            ahead = None
        return {"available": True, "branch": git("branch", "--show-current"),
                "remote": git("remote", "get-url", "origin"),
                "changes": changes, "changed_files": [line[3:] for line in changes.splitlines()],
                "changed_count": len(changes.splitlines()),
                "commit": git("rev-parse", "--short", "HEAD"), "ahead_count": ahead,
                "directory": relative, "busy": _LOCK.locked()}
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        return {"available": False, "error": str(exc)}


def sync_website() -> dict:
    if not _LOCK.acquire(blocking=False):
        raise ValueError("正在同步，请等待当前同步完成")
    try:
        status = sync_status()
        if not status.get("available"):
            raise ValueError(status.get("error", "未找到Git仓库"))
        branch, relative = status["branch"], status["directory"]
        try:
            repo, _ = _repository_context()
        except ValueError:
            repo = ROOT
        def git(*arguments: str, timeout: int = 30):
            return _git(*arguments, timeout=timeout, cwd=repo)
        if not branch:
            raise ValueError("当前处于分离HEAD，先在Git中切换到分支")
        staged = git("diff", "--cached", "--name-only", "-z").split("\0")
        if any(name and not (name == relative or name.startswith(relative + "/")) for name in staged):
            raise ValueError("存在网站之外已暂存的文件；请先单独处理，防止一并上传")
        unstaged = git("diff", "--name-only", "-z").split("\0")
        if set(name for name in staged if name) & set(name for name in unstaged if name):
            raise ValueError("网站存在部分暂存的文件；请先完成该文件的暂存或提交，避免覆盖已选择的改动")
        git("add", "--", ":(top)" + relative)
        names = [name for name in git("diff", "--cached", "--name-only", "-z").split("\0") if name]
        prohibited = ("/.runtime/", "/__pycache__/", "/.venv/", "/node_modules/")
        if any(any(part in "/" + name for part in prohibited) or
               Path(name).name in {".env", "auth.json", "credentials.json"} for name in names):
            raise ValueError("暂存区包含运行数据或凭据，请从暂存区移除后重试")
        committed = False
        if names:
            git("commit", "-m", "feat: sync corrosion research workbench", timeout=60)
            committed = True
        # 即使没有新改动，也推送上次未上传的提交。
        output = git("push", "-u", "origin", branch, timeout=120)
        return {"success": True, "committed": committed, "branch": branch,
                "remote": status["remote"], "commit": git("rev-parse", "HEAD"),
                "message": "网站源码已同步到GitHub", "output": output}
    finally:
        _LOCK.release()


if __name__ == "__main__":
    import json
    print(json.dumps(sync_website(), ensure_ascii=False, indent=2))

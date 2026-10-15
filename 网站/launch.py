"""双击启动：复用本网站服务，端口被其他程序占用时选择空闲端口。"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def service_at(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1) as response:
            info = json.load(response)
        return (info.get("service") == "corrosion-research-workbench" and
                Path(info.get("site_root", "")).resolve() == ROOT)
    except (OSError, ValueError):
        return False


def launch(*, open_browser=True, preferred_port=8523):
    runtime = ROOT / ".runtime"
    runtime.mkdir(exist_ok=True)
    marker = runtime / "service.json"
    ports = [preferred_port]
    if marker.exists():
        try:
            ports.insert(0, int(json.loads(marker.read_text(encoding="utf-8"))["port"]))
        except (ValueError, KeyError):
            pass
    for port in dict.fromkeys(ports):
        if service_at(port):
            url = f"http://127.0.0.1:{port}/"
            if open_browser:
                webbrowser.open(url)
            return url
    missing = [name for name in ("numpy", "scipy", "matplotlib", "skimage", "openpyxl", "psutil")
               if importlib.util.find_spec(name) is None]
    if missing:
        raise RuntimeError("当前Python缺少依赖：" + "、".join(missing) +
                           "\n请运行：python -m pip install -r requirements.txt")
    port = None
    for candidate in range(preferred_port, preferred_port + 30):
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", candidate))
                port = candidate
                break
            except OSError:
                pass
    if port is None:
        raise RuntimeError("未找到空闲端口，请检查8523附近的端口占用")
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "utf-8"
    with (runtime / "server.log").open("a", encoding="utf-8") as log:
        process = subprocess.Popen([sys.executable, "-u", str(ROOT / "start_server.py"),
                                    "--port", str(port)], cwd=ROOT, env=environment,
                                   stdout=log, stderr=subprocess.STDOUT, creationflags=flags,
                                   start_new_session=os.name != "nt")
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        if service_at(port):
            url = f"http://127.0.0.1:{port}/"
            if open_browser:
                webbrowser.open(url)
            return url
        if process.poll() is not None:
            raise RuntimeError("服务启动失败，请查看 .runtime/server.log")
        time.sleep(.25)
    raise RuntimeError("服务启动超过25秒，请查看 .runtime/server.log")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--port", type=int, default=8523)
    options = parser.parse_args()
    try:
        print(launch(open_browser=not options.no_browser, preferred_port=options.port))
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)

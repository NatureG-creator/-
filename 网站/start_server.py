from backend.server import make_server


if __name__ == "__main__":
    import argparse
    import os
    from pathlib import Path
    from backend.runner import _atomic_json
    parser = argparse.ArgumentParser(description="启动腐蚀研究工作台本机服务")
    parser.add_argument("--port", type=int, default=8523)
    parser.add_argument("--runtime", type=Path)
    args = parser.parse_args()
    server = make_server(port=args.port, runtime=args.runtime)
    _atomic_json(server.runtime / "service.json",
                 {"port": server.server_port, "pid": os.getpid(),
                  "site_root": str(Path(__file__).resolve().parent)})
    print(f"腐蚀研究网站已启动：http://127.0.0.1:{server.server_port}/", flush=True)
    server.serve_forever()

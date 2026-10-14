from backend.server import make_server


if __name__ == "__main__":
    server = make_server()
    print(f"腐蚀研究网站已启动：http://127.0.0.1:{server.server_port}/", flush=True)
    server.serve_forever()

"""Small stdin-gated launcher; it never opens/inherits the management job handle."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--execution-id', required=True)
    args = parser.parse_args()
    message = sys.stdin.buffer.readline(1024*1024)
    if not message:
        return 125
    request = json.loads(message)
    record = json.loads((Path(args.output)/'mapdl_process.json').read_text(encoding='utf-8'))
    if (request.get('go') != args.execution_id or record.get('execution_id') != args.execution_id
            or record.get('state') != 'grouped' or record.get('command') != request.get('command')):
        return 125
    # Windows children inherit job membership, while close_fds excludes management handles.
    child_env = request.get('env')
    if child_env is not None and not isinstance(child_env, dict):
        return 125
    process = subprocess.Popen(request['command'], cwd=args.output, stdin=subprocess.DEVNULL,
                               shell=False, close_fds=True, env=child_env or os.environ.copy())
    return process.wait()


if __name__ == '__main__':
    sys.exit(main())

"""Windowless shortcut entry for the current checkout and fixed port 8560."""
import argparse
import ctypes
import os
import sys
import traceback
from pathlib import Path


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--no-browser',action='store_true')
    args=parser.parse_args()
    runtime=Path(os.environ.get('CORROSION_RUNTIME_DIR',r'D:\research\CorrosionWebsiteData'))
    try:
        from launch import launch
        url=launch(open_browser=not args.no_browser,preferred_port=8560,runtime=runtime,fixed_port=True)
        if sys.stdout is not None:
            print(url)
        return 0
    except Exception as exc:
        runtime.mkdir(parents=True,exist_ok=True)
        log=runtime/'desktop_launch_error.log'
        log.write_text(traceback.format_exc(),encoding='utf-8')
        message=f'工作台启动失败：{exc}\n详细记录：{log}'
        if args.no_browser:
            if sys.stderr is not None:
                print(message,file=sys.stderr)
        else:
            ctypes.windll.user32.MessageBoxW(None,message,'腐蚀研究工作台',0x10)
        return 1


if __name__=='__main__':
    raise SystemExit(main())

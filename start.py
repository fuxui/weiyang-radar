"""双击 启动.cmd 使用；自动选择空闲本机端口并打开浏览器。"""
from pathlib import Path
from urllib.request import urlopen
import json
import socket
import subprocess
import sys
import time
import webbrowser
from server import VERSION

ROOT = Path(__file__).resolve().parent


def main():
    port = None
    for candidate in range(8765,8785):
        try:
            with socket.socket() as sock:
                sock.bind(('127.0.0.1',candidate))
            port = candidate
            break
        except OSError:
            continue
    if port is None:
        raise SystemExit('没有可用端口；请运行 python server.py --port 其他端口')
    process = subprocess.Popen([sys.executable,str(ROOT/'server.py'),'--port',str(port)],cwd=ROOT)
    url = 'http://127.0.0.1:'+str(port)
    try:
        for _ in range(40):
            if process.poll() is not None:
                raise SystemExit('服务启动失败，请查看上方错误信息')
            try:
                with urlopen(url+'/api/state',timeout=1) as response:
                    ready = json.load(response).get('version')==VERSION
                if ready:
                    webbrowser.open(url)
                    print('浏览器未自动打开时，请访问 '+url+'；按 Ctrl+C 停止。',flush=True)
                    break
            except (OSError,ValueError):
                pass
            time.sleep(.25)
        else:
            raise SystemExit('启动等待超时，请查看错误信息')
        process.wait()
    except KeyboardInterrupt:
        pass
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)


if __name__=='__main__':
    main()

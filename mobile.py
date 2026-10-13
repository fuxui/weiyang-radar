"""同 Wi-Fi 手机入口，无需安装手机软件或注册账号。"""
from pathlib import Path
from urllib.request import build_opener, ProxyHandler
import argparse
import html
import json
import os
import secrets
import socket
import subprocess
import sys
import time
import webbrowser
from server import lan_address

ROOT = Path(__file__).resolve().parent
PORT = 8790


def discover_lan():
    command = "@((Get-NetIPConfiguration | Where-Object { $_.IPv4DefaultGateway -and $_.NetAdapter.HardwareInterface }) | ForEach-Object { @{name=$_.InterfaceAlias; ip=$_.IPv4Address.IPAddress} }) | ConvertTo-Json -Compress"
    result = subprocess.run(['powershell','-NoProfile','-Command',command],capture_output=True,encoding='utf-8',errors='replace',timeout=35)
    if result.returncode or not result.stdout.strip():
        raise RuntimeError('没有找到正在联网的实体网卡，请先连接 Wi-Fi。')
    rows = json.loads(result.stdout)
    rows = rows if isinstance(rows,list) else [rows]
    choices = []
    for row in rows:
        for address in row.get('ip',[]) if isinstance(row.get('ip'),list) else [row.get('ip')]:
            try:
                choices.append((row['name'],lan_address(address)))
            except (ValueError,TypeError):
                continue
    if not choices:
        raise RuntimeError('没有找到可用于同 Wi-Fi 连接的局域网地址。')
    if len(choices)==1:
        return choices[0][1]
    print('请选择与手机相同网络的网卡：')
    for i,(name,address) in enumerate(choices,1):
        print(str(i)+'. '+name+' '+address)
    selected = int(input('输入编号：'))
    if not 1<=selected<=len(choices):
        raise ValueError('网卡编号不正确')
    return choices[selected-1][1]


def load_pin():
    path = ROOT/'手机连接配置.json'
    if path.is_file():
        pin = json.loads(path.read_text(encoding='utf-8'))['pin']
        if not isinstance(pin,str) or len(pin)!=10 or not pin.isascii() or not pin.isdigit():
            raise ValueError('手机连接配置中的口令格式不正确')
        return pin
    pin = format(secrets.randbelow(10**10),'010d')
    path.write_text(json.dumps({'pin':pin}),encoding='utf-8')
    return pin


def main():
    parser = argparse.ArgumentParser(description='未央 Radar 同 Wi-Fi 手机连接')
    parser.add_argument('--ip',type=lan_address)
    parser.add_argument('--no-browser',action='store_true')
    args = parser.parse_args()
    address = args.ip or discover_lan()
    with socket.socket() as sock:
        try:
            sock.bind((address,PORT))
        except OSError as ex:
            raise RuntimeError('手机端口 8790 已占用或网卡不可用；请检查原有手机连接窗口。') from ex
    pin = load_pin()
    url = 'http://'+address+':'+str(PORT)
    env = dict(os.environ,RADAR_LAN_PIN=pin)
    env.pop('RADAR_PRIVATE_ORIGIN',None)
    process = subprocess.Popen([sys.executable,str(ROOT/'server.py'),'--port',str(PORT),'--lan-ip',address],cwd=ROOT,env=env)
    try:
        for _ in range(40):
            if process.poll() is not None:
                raise RuntimeError('研究工具启动失败。')
            try:
                with build_opener(ProxyHandler({})).open(url+'/',timeout=1) as response:
                    if response.status==200 and '手机连接'.encode() in response.read():
                        break
            except OSError:
                pass
            time.sleep(.25)
        else:
            raise RuntimeError('启动超时，请检查网卡与防火墙。')
        guide = ROOT/'手机连接说明.html'
        guide.write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>未央 Radar 手机连接</title><body style="font:18px/1.8 system-ui;max-width:640px;margin:8vh auto;padding:24px;background:#07363a;color:#fff7de"><h1>未央 · 手机连接</h1><p>手机和电脑连同一个 Wi-Fi，用手机浏览器输入：</p><p style="font-size:26px">'+html.escape(url)+'</p><p>访问口令：<b>'+pin+'</b></p><p>登录后：浏览器菜单 → 添加到主屏幕 → 未央 Radar。</p><p>电脑与此窗口需保持运行。仅在可信 Wi-Fi 使用，换网络后地址可能改变。</p><p>打不开时：先确认同一 Wi-Fi、暂时关闭手机 VPN；访客或校园网络可能隔离设备，可改用自己的热点。</p></body></html>',encoding='utf-8')
        (ROOT/'手机访问地址.txt').write_text(url+'\n口令请查看手机连接窗口或手机连接说明.html。\n',encoding='utf-8')
        print('\n手机地址：'+url+'\n访问口令：'+pin+'\n手机和电脑连同一个 Wi-Fi；窗口保持打开，Ctrl+C 停止。',flush=True)
        if not args.no_browser:
            webbrowser.open(guide.as_uri())
        process.wait()
    except KeyboardInterrupt:
        pass
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=10)


if __name__=='__main__':
    try:
        main()
    except (RuntimeError,OSError,ValueError,KeyError,subprocess.SubprocessError) as ex:
        print('手机连接尚未完成：'+str(ex),flush=True)
        sys.exit(1)

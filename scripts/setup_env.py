# -*- coding: utf-8 -*-
"""amazon-competitor-audit 环境自检与准备脚本

在别的机器/agent 上安装本 skill 后，先跑本脚本确认前置项，缺什么会给出明确指引。

用法:
  python setup_env.py              # 全面自检（只读，不自动安装）
  python setup_env.py --install    # 自检 + 自动 pip install openpyxl

输出：每项 [OK] 或 [缺]，缺的给出下一步命令/说明。
"""
import argparse
import os
import shutil
import socket
import subprocess
import sys


def check_python():
    v = sys.version_info
    ok = v >= (3, 9)
    print('%-22s %s Python %d.%d.%d' % ('Python', 'OK' if ok else '低', v[0], v[1], v[2]))
    return ok


def check_openpyxl():
    try:
        import openpyxl  # noqa: F401
        print('%-22s OK openpyxl %s' % ('openpyxl', openpyxl.__version__))
        return True
    except ImportError:
        print('%-22s 缺 openpyxl 未安装，运行: python -m pip install openpyxl' % 'openpyxl')
        return False


def check_kdocs():
    """检测 kdocs 访问通道：优先 kdocs MCP（若环境有），其次 kdocs-cli。"""
    cli = os.environ.get('KDOCS_CLI') or shutil.which('kdocs-cli') or shutil.which('kdocs-cli.exe')
    cands = [os.path.expandvars(r'%LOCALAPPDATA%\kdocs-cli\kdocs-cli.exe'),
             os.path.expandvars(r'%USERPROFILE%\AppData\Local\kdocs-cli\kdocs-cli.exe')]
    if cli and os.path.exists(cli):
        print('%-22s OK kdocs-cli: %s' % ('kdocs-cli', cli))
        return True
    for c in cands:
        if os.path.exists(c):
            print('%-22s OK kdocs-cli: %s' % ('kdocs-cli', c))
            return True
    print('%-22s 缺 未找到 kdocs-cli。' % 'kdocs-cli')
    print('         优先方式：确认当前 agent 环境有 kdocs MCP 工具（如 mcp__jinshanwendang__*），'
          '读写表格走 MCP，不依赖 kdocs-cli。')
    print('         仅当走 CLI 封装 kdocs_sheet.py 时才需要装 kdocs-cli（见 SKILL.md 可移植配置）。')
    return False


def check_cdp():
    s = socket.socket()
    s.settimeout(1)
    try:
        s.connect(('127.0.0.1', 9222))
        print('%-22s OK CDP 端口 9222 在监听' % 'CDP 端口 9222')
        return True
    except Exception:
        print('%-22s 缺 CDP 端口 9222 未监听' % 'CDP 端口 9222')
        print('         用【独立调试 profile】带调试端口启动（默认 profile 常不生效）：')
        print('         "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe" --remote-debugging-port=9222 --user-data-dir=C:\\cdp-profile')
        print('         "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" --remote-debugging-port=9222 --user-data-dir=C:\\cdp-profile')
        print('         "C:\\<你的360路径>\\360se.exe" --remote-debugging-port=9222')
        return False
    finally:
        s.close()


def check_login_hint():
    print('%-22s 待确认 需在浏览器登录：卖家精灵 sellersprite.com/v3、Amazon、kdocs' % '登录态')
    print('         广告数据也需登录态（游客态第 4 个 ASIN 起被风控拦截）；')
    print('         评论八点需卖家精灵【网页端与扩展端账号一致】。')
    return True


def install_openpyxl():
    print('正在安装 openpyxl ...')
    r = subprocess.run([sys.executable, '-m', 'pip', 'install', 'openpyxl'],
                       capture_output=True, text=True)
    if r.returncode == 0:
        print('openpyxl 安装完成。')
        return True
    print('openpyxl 安装失败：', (r.stderr or r.stdout)[-500:])
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--install', action='store_true', help='自检后自动 pip install openpyxl')
    args = ap.parse_args()

    print('=== amazon-competitor-audit 环境自检 ===\n')
    r1 = check_python()
    r2 = check_openpyxl()
    r3 = check_kdocs()
    r4 = check_cdp()
    r5 = check_login_hint()

    if args.install and not r2:
        install_openpyxl()
        r2 = check_openpyxl()

    print('\n=== 结论 ===')
    ok = r1 and r2 and (r3) and r4
    if ok:
        print('核心依赖齐全，可开工。剩下确认登录态即可。')
    else:
        print('仍有前置项未满足，按上面指引补齐后重跑本脚本。')
        print('注意：kdocs 优先走 MCP；openpyxl 缺可 --install 自动装；CDP 需手动带调试端口启动浏览器。')


if __name__ == '__main__':
    main()

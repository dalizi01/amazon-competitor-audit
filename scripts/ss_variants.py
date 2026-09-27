# -*- coding: utf-8 -*-
"""卖家精灵插件「变体对比」采集 —— 八点判定 #7 老带新 的数据源

在 Amazon dp 页插件浮窗点 tab「变体对比(N)」，一次拿到父体**全部变体**的
`变体ASIN / SKU / 价格 / 月销量(父) / 流量词数 / 评分 / FBA / 上架时间(YYYY-MM-DD(N天))`。
面板顶部另有 `近30天销量(父体)` —— 这是判定 #4 刷单的**正确分母**（评论是父体共享的）。

⚠ tab 名是「变体对比」，不是「变体流量对比」（后者只给流量词，不给上架时间）。
⚠ 顺序必须是 navigate → Page.bringToFront，反了扩展不注入（见 SKILL.md F5）。
   Amazon 页面加载慢时会失败，脚本内已带 Page.reload 重试 3 轮。

用法:
  python ss_variants.py --asins B0BQJ2XZWF B001OK1YUA --out variants.json
  python ss_variants.py --picks picks.json --out variants.json [--force]

输出: {asin: {days, date, sales30, n_var, bsr, rating, rev,
             variants:[{asin,date,days}, ...]}}
"""
import argparse
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.request
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cdp360 import WS  # noqa

PORT = 9222
DEFAULT_EXE = r'C:\Users\Administrator.DESKTOP-021UVEO\AppData\Roaming\360se6\Application\360se.exe'
_NP = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def port_open(t=0.8):
    s = socket.socket(); s.settimeout(t)
    try:
        s.connect(('127.0.0.1', PORT)); return True
    except Exception:
        return False
    finally:
        s.close()


def ensure_browser(exe=DEFAULT_EXE, force=False):
    """360 浏览器进程会随 Bash 命令结束被回收 —— 启动必须和抓取写在同一进程内。"""
    if force:
        subprocess.run(['taskkill', '/F', '/IM', '360se.exe'], capture_output=True)
        time.sleep(3)
    if port_open():
        return
    subprocess.Popen([exe, '--remote-debugging-port=%d' % PORT],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     stdin=subprocess.DEVNULL, close_fds=True,
                     creationflags=0x00000008 | 0x00000200)  # DETACHED|NEW_PROCESS_GROUP
    for _ in range(40):
        time.sleep(1)
        if port_open():
            return
    raise RuntimeError('browser not ready on port %d' % PORT)


def http(path):
    return json.loads(_NP.open('http://127.0.0.1:%d' % PORT + path, timeout=10).read())


def parse(text):
    r = {}
    m = re.search(r'近30天销量\(父体\)\s*\n\s*([\d,]+)', text)
    r['sales30'] = int(m.group(1).replace(',', '')) if m else None
    m = re.search(r'上架时间\s*\n\s*(\d{4}-\d{2}-\d{2})\(([\d,]+)天\)', text)
    if m:
        r['date'] = m.group(1)
        r['days'] = int(m.group(2).replace(',', ''))
    m = re.search(r'变体数\s*\n\s*(\d+)', text)
    r['n_var'] = int(m.group(1)) if m else None
    m = re.search(r'BSR\s*\n\s*([\d,]+)', text)
    r['bsr'] = int(m.group(1).replace(',', '')) if m else None
    m = re.search(r'评分\(评分数\)[\s:]*\n?\s*([\d.]+)\(([\d,]+)\)', text)
    if m:
        r['rating'] = float(m.group(1))
        r['rev'] = int(m.group(2).replace(',', ''))
    vs = []
    for m in re.finditer(r'(B0[A-Z0-9]{8})[\s\S]{0,500}?(\d{4}-\d{2}-\d{2})\(([\d,]+)天\)', text):
        a = m.group(1)
        if any(v['asin'] == a for v in vs):
            continue
        vs.append({'asin': a, 'date': m.group(2),
                   'days': int(m.group(3).replace(',', ''))})
    r['variants'] = vs
    return r


def load_asins(picks):
    d = json.load(open(picks, encoding='utf-8'))
    rows = list(d.values()) if isinstance(d, dict) else list(d)
    out = []
    for r in rows:
        out.append(r if isinstance(r, str) else r['asin'])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--asins', nargs='*')
    ap.add_argument('--picks')
    ap.add_argument('--out', default='variants.json')
    ap.add_argument('--exe', default=DEFAULT_EXE)
    ap.add_argument('--force', action='store_true', help='先杀掉已有 360 浏览器再启动')
    args = ap.parse_args()
    if args.picks:
        asins = load_asins(args.picks)
    elif args.asins:
        asins = args.asins
    else:
        ap.error('需要 --asins 或 --picks')

    ensure_browser(exe=args.exe, force=args.force)
    v = http('/json/version')
    p = urlparse(v['webSocketDebuggerUrl'])
    bws = WS(p.hostname, p.port, p.path)
    mid = [0]
    bws.sock.settimeout(90)

    def call(method, **params):
        mid[0] += 1
        bws.send(json.dumps({'id': mid[0], 'method': method, 'params': params}))
        while True:
            d = json.loads(bws.recv())
            if d.get('id') == mid[0]:
                return d.get('result', {})

    tid = call('Target.createTarget', url='about:blank')['targetId']
    sid = call('Target.attachToTarget', targetId=tid, flatten=True)['sessionId']

    def s(method, **params):
        mid[0] += 1
        bws.send(json.dumps({'id': mid[0], 'method': method, 'params': params,
                             'sessionId': sid}))
        while True:
            d = json.loads(bws.recv())
            if d.get('id') == mid[0] and d.get('sessionId') == sid:
                return d.get('result', {})

    def ev(expr):
        return s('Runtime.evaluate', expression=expr, returnByValue=True,
                 awaitPromise=True).get('result', {}).get('value')

    s('Page.enable')
    call('Target.activateTarget', targetId=tid)

    state = json.load(open(args.out, encoding='utf-8')) if os.path.exists(args.out) else {}
    for i, asin in enumerate(asins):
        if state.get(asin, {}).get('variants'):
            print('[%d/%d] %s skip' % (i + 1, len(asins), asin), flush=True)
            continue
        s('Page.navigate', url='https://www.amazon.com/dp/' + asin)
        time.sleep(3)
        s('Page.bringToFront')            # 顺序不能反，否则扩展不注入
        ok = False
        for _attempt in range(3):
            for _ in range(12):
                time.sleep(2)
                if ev("document.querySelectorAll('.tab-name').length"):
                    ok = True
                    break
            if ok:
                break
            s('Page.reload', ignoreCache=False)
            time.sleep(4)
            s('Page.bringToFront')
        if not ok:
            print('[%d/%d] %s 插件未注入' % (i + 1, len(asins), asin), flush=True)
            state[asin] = {'err': 'no plugin'}
            json.dump(state, open(args.out, 'w', encoding='utf-8'), ensure_ascii=False)
            continue
        ev("(function(){var t=null;document.querySelectorAll('.tab-name').forEach("
           "function(e){if(/变体对比/.test(e.textContent))t=e;});if(t)t.click();return 1;})()")
        time.sleep(6)
        txt = ev("(function(){var c=document.querySelector("
                 "'#seller-sprite-extension-quick-view-listing-page');"
                 "return c?c.innerText:'';})()")
        rec = parse(txt or '')
        rec['raw_len'] = len(txt or '')
        state[asin] = rec
        ds = [x['days'] for x in rec.get('variants', [])]
        print('[%d/%d] %s days=%s nvar=%s vars=%d dmax=%s dmin=%s sales30=%s' % (
            i + 1, len(asins), asin, rec.get('days'), rec.get('n_var'),
            len(rec.get('variants', [])), max(ds) if ds else None,
            min(ds) if ds else None, rec.get('sales30')), flush=True)
        json.dump(state, open(args.out, 'w', encoding='utf-8'), ensure_ascii=False)
        time.sleep(3)
    bws.close()
    print('DONE ->', args.out)


if __name__ == '__main__':
    main()

# -*- coding: utf-8 -*-
"""卖家精灵评论数据采集 —— 八点判定的核心数据源

采集每个 ASIN:
  - vine        : US 站 Vine 评论真实条数  (判定 #3 Vine)
  - counts      : 各站点评论总数           (判定 #2 合并评论 = 存在非美地区评论)
  - n30/rate30  : 近30天评论数 / 留评率    (判定 #4 刷单, 阈值 3%)

用法:
  python ss_review.py --picks picks.json --out reviews.json
  python ss_review.py --asins B073JCMTW2 B0B5H6XXNH --out reviews.json

picks.json 可是:
  - [{"asin":..., "sales":..., "days":...}, ...]
  - {"asin": {...}, ...}
  - ["B073JCMTW2", ...]

前置: 360 浏览器已带 --remote-debugging-port=9222 启动（本脚本会自动拉起）
      且浏览器里 sellersprite.com 已登录
"""
import argparse
import datetime
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from cdp360 import WS  # noqa: E402

PORT = 9222


def _find_browser():
    """定位可带 --remote-debugging-port 的 Chrome 内核浏览器。

    优先级：环境变量 BROWSER_EXE > PATH(360se/chrome/msedge) > 常见安装路径。
    """
    env = os.environ.get('BROWSER_EXE')
    if env and os.path.exists(env):
        return env
    for name in ('360se.exe', 'chrome.exe', 'msedge.exe'):
        w = shutil.which(name)
        if w:
            return w
    for p in (
        os.path.expandvars(r'%APPDATA%\360se6\Application\360se.exe'),
        os.path.expandvars(r'%PROGRAMFILES%\360se6\Application\360se.exe'),
        os.path.expandvars(r'%PROGRAMFILES(X86)%\360se6\Application\360se.exe'),
        r'C:\Program Files\Google\Chrome\Application\chrome.exe',
        r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
        os.path.expandvars(r'%PROGRAMFILES%\Microsoft\Edge\Application\msedge.exe'),
        os.path.expandvars(r'%PROGRAMFILES(X86)%\Microsoft\Edge\Application\msedge.exe'),
    ):
        if os.path.exists(p):
            return p
    return 'chrome'


DEFAULT_EXE = _find_browser()
MARKETS = ['US', 'CA', 'UK', 'DE', 'JP', 'FR', 'IT', 'ES']
SPRITE_HOME = 'https://www.sellersprite.com/v3/'

_NP = urllib.request.build_opener(urllib.request.ProxyHandler({}))


# ---------- 浏览器 ----------

def port_open(t=0.8):
    s = socket.socket()
    s.settimeout(t)
    try:
        s.connect(('127.0.0.1', PORT))
        return True
    except Exception:
        return False
    finally:
        s.close()


def ensure_browser(exe=DEFAULT_EXE, force=False):
    """360 浏览器进程会随 Bash 命令结束被回收 —— 启动必须和抓取在同一进程内。"""
    if force:
        subprocess.run(['taskkill', '/F', '/IM', '360se.exe'], capture_output=True)
        time.sleep(3)
    if port_open():
        return
    subprocess.Popen([exe, '--remote-debugging-port=%d' % PORT],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     stdin=subprocess.DEVNULL, close_fds=True,
                     creationflags=0x00000008 | 0x00000200)
    for _ in range(30):
        time.sleep(1)
        if port_open():
            return
    subprocess.run(['taskkill', '/F', '/IM', '360se.exe'], capture_output=True)
    time.sleep(4)
    subprocess.Popen([exe, '--remote-debugging-port=%d' % PORT],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     stdin=subprocess.DEVNULL, close_fds=True,
                     creationflags=0x00000008 | 0x00000200)
    for _ in range(30):
        time.sleep(1)
        if port_open():
            return
    raise RuntimeError('browser not ready on port %d' % PORT)


def http(path):
    return json.loads(_NP.open('http://127.0.0.1:%d' % PORT + path, timeout=10).read())


def ensure_sprite_tab():
    """确保存在一个 sellersprite.com 页面（登录态上下文），返回其 WS 地址。"""
    for t in http('/json/list'):
        if t.get('type') == 'page' and 'sellersprite.com' in t.get('url', ''):
            p = urlparse(t['webSocketDebuggerUrl'])
            return p.hostname, p.port, p.path
    v = http('/json/version')
    p = urlparse(v['webSocketDebuggerUrl'])
    bws = WS(p.hostname, p.port, p.path)
    mid = [0]

    def call(method, **params):
        mid[0] += 1
        bws.send(json.dumps({'id': mid[0], 'method': method, 'params': params}))
        while True:
            d = json.loads(bws.recv())
            if d.get('id') == mid[0]:
                return d.get('result', {})

    tid = call('Target.createTarget', url=SPRITE_HOME)['targetId']
    time.sleep(10)
    bws.close()
    for t in http('/json/list'):
        if t.get('id') == tid:
            p = urlparse(t['webSocketDebuggerUrl'])
            return p.hostname, p.port, p.path
    raise RuntimeError('no sellersprite tab')


# ---------- 采集 ----------

class Sprite:
    def __init__(self, host, port, path):
        self.ws = WS(host, port, path)
        self._id = 0

    def evaljs(self, expr, timeout=90):
        self._id += 1
        self.ws.send(json.dumps({'id': self._id, 'method': 'Runtime.evaluate',
                                 'params': {'expression': expr, 'returnByValue': True,
                                            'awaitPromise': True}}))
        self.ws.sock.settimeout(timeout)
        while True:
            d = json.loads(self.ws.recv())
            if d.get('id') == self._id:
                r = d.get('result', {})
                if 'exceptionDetails' in r:
                    return {'__err': str(r['exceptionDetails'])[:300]}
                return r.get('result', {}).get('value')

    def type_us(self, asin):
        return self.evaljs(
            "(async()=>{const r=await fetch('/v3/api/review-analysis/type/US/%s',"
            "{credentials:'include'});return await r.json();})()" % asin)

    def count(self, asin, market, page_size=1):
        body = json.dumps({'asin': asin, 'market': market,
                           'pageNum': 1, 'pageSize': page_size})
        c = self.evaljs(
            "(async()=>{const r=await fetch('/v3/api/review-analysis/comment',"
            "{method:'POST',credentials:'include',headers:{'Content-Type':'application/json'},"
            "body:JSON.stringify(%s)});return await r.json();})()" % json.dumps(body))
        d = (c or {}).get('data') or {}
        return d.get('total', 0) or 0

    def comments(self, asin, market='US', max_pages=8, cover_days=32):
        """按日期降序拉取，直到采样早于 cover_days 天前（即已覆盖近30天）为止。"""
        import datetime as _dt
        cutoff = (_dt.datetime.now() - _dt.timedelta(days=cover_days)).timestamp() * 1000
        items, total = [], None
        for page in range(1, max_pages + 1):
            body = json.dumps({'asin': asin, 'market': market,
                               'pageNum': page, 'pageSize': 100})
            c = self.evaljs(
                "(async()=>{const r=await fetch('/v3/api/review-analysis/comment',"
                "{method:'POST',credentials:'include',headers:{'Content-Type':'application/json'},"
                "body:JSON.stringify(%s)});return await r.json();})()" % json.dumps(body))
            if not c or not c.get('success'):
                break
            d = c['data']
            total = d.get('total')
            its = d.get('items') or []
            items.extend(its)
            if total and len(items) >= total or not its:
                break
            dmin = min([x.get('date') or 0 for x in items] or [0])
            if dmin and dmin < cutoff:
                break
            time.sleep(0.5)
        return items, total

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass


def load_picks(path):
    d = json.load(open(path, encoding='utf-8'))
    if isinstance(d, dict):
        rows = list(d.values())
    else:
        rows = d
    out = []
    for r in rows:
        if isinstance(r, str):
            out.append({'asin': r, 'sales': 0, 'days': 0})
        else:
            out.append(r)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--picks')
    ap.add_argument('--asins', nargs='*')
    ap.add_argument('--out', required=True)
    ap.add_argument('--markets', default=','.join(MARKETS))
    ap.add_argument('--exe', default=DEFAULT_EXE)
    ap.add_argument('--force', action='store_true', help='先杀掉已有 360 浏览器再启动')
    ap.add_argument('--no-comments', action='store_true', help='跳过逐条评论(不统计近30天)')
    args = ap.parse_args()

    if args.picks:
        picks = load_picks(args.picks)
    elif args.asins:
        picks = [{'asin': a, 'sales': 0, 'days': 0} for a in args.asins]
    else:
        ap.error('需要 --picks 或 --asins')

    markets = [m.strip() for m in args.markets.split(',') if m.strip()]

    ensure_browser(exe=args.exe, force=args.force)
    host, port, path = ensure_sprite_tab()
    sp = Sprite(host, port, path)

    state = {}
    if os.path.exists(args.out):
        state = json.load(open(args.out, encoding='utf-8'))

    now = datetime.datetime.now()
    for r in picks:
        asin = r['asin']
        rec = state.get(asin, {})
        counts = rec.get('counts', {})
        for mk in markets:
            if mk in counts:
                continue
            counts[mk] = sp.count(asin, mk)
            time.sleep(0.3)
        if 'vine' not in rec:
            t = sp.type_us(asin)
            rec['type_us'] = (t or {}).get('data') or {}
            rec['vine'] = rec['type_us'].get('vine', 0)
        rec['counts'] = counts
        rec['non_us'] = {k: v for k, v in counts.items() if k != 'US' and v > 0}
        rec['non_us_total'] = sum(rec['non_us'].values())

        if not args.no_comments:
            items, _ = sp.comments(asin)
            dates = [x['date'] for x in items if x.get('date')]
            n30 = sum(1 for d in dates
                      if (now - datetime.datetime.fromtimestamp(d / 1000)).days <= 30)
            rec['n30'] = n30
            rec['sampled'] = len(items)
            rec['oldest'] = (str(datetime.datetime.fromtimestamp(min(dates) / 1000).date())
                             if dates else None)
            rec['cover_days'] = ((now - datetime.datetime.fromtimestamp(min(dates) / 1000)).days
                                 if dates else 0)
        sales = r.get('sales') or 0
        rec['sales'] = sales
        rec['rate30'] = round((rec.get('n30', 0) / sales * 100), 2) if sales else None
        state[asin] = rec
        print('[%s] US=%s nonUS=%s vine=%s n30=%s rate=%s%%' %
              (asin, counts.get('US'), rec['non_us'], rec['vine'],
               rec.get('n30'), rec.get('rate30')), flush=True)
        json.dump(state, open(args.out, 'w', encoding='utf-8'), ensure_ascii=False)

    sp.close()
    print('DONE ->', args.out)


if __name__ == '__main__':
    main()

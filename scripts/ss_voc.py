# -*- coding: utf-8 -*-
"""卖家精灵「评论分析(VOC)」采集 —— 机会点(col14)的「差评点 / 可借鉴点」数据源

产出（每 ASIN）：
  negative_tags : [(标签, 条数), ...]      ← 差评点（要规避）
  positive_tags : [(标签, 条数), ...]      ← 可借鉴点（要继承）
  risk_tags     : [(标签, 条数), ...]      ← 风险信号
  root_causes   : [ {type,title,summary,...} ]  ← 差评根因(AI)
  summary       : {one_sentence, top_positive, top_negative, biggest_risks, ...}
  contexts      : [ {title, who, environment, task, goal, ...} ]
  divergences   : [...]
  rating_dist   : {1..5: n}

流程：
  1) 查报告是否已存在（POST review-voc/list {page,size} 拉全量，再客户端按 asin 匹配）
     ⚠ 该端点忽略 asin/market 等过滤参数，返回账号下全部报告（见 F26）
  2) 不存在则提交生成（打开 /v3/ai-review-analysis，选美国站→填ASIN→点生成报告）
     ⚠ 消耗配额 10 次/个；每日配额查 /v3/api/ai-analysis/daily-remaining-quota
  3) 轮询 batch-get-report {ids:[id]} 直到 ready
  4) 拉 task-detail {id:"<id>"}，解析 6 个子 JSON，抽取上述字段

用法:
  python ss_voc.py --asins B0BQJ2XZWF --out voc_insight.json          # 已有报告则直接读
  python ss_voc.py --asins B0BQJ2XZWF --create --out voc_insight.json # 允许创建(消耗配额)
  python ss_voc.py --picks picks.json --create --out voc_insight.json

⚠ 必须在「同一条命令/同一进程」内完成启动浏览器+抓取（Bash 命令结束浏览器即回收）。
⚠ 已内置 raw-socket 版 get_browser_ws_url，规避 cdp360 的 stdin 阻塞坑（见 SKILL F24）。
"""
import argparse
import json
import os
import socket
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cdp360  # noqa: E402

EXE = os.environ.get('BROWSER_EXE') or \
    r'C:\Users\Administrator.DESKTOP-021UVEO\AppData\Roaming\360se6\Application\360se.exe'
PORT = int(os.environ.get('CDP_PORT', '9222'))
HOME = 'https://www.sellersprite.com/v3/ai-review-analysis'


# ---------- CDP 基础设施（raw socket，避开 stdin 阻塞） ----------

def _ws_url(port=PORT, timeout=6):
    s = socket.create_connection(('127.0.0.1', port), timeout=timeout)
    s.settimeout(timeout)
    s.sendall(('GET /json/version HTTP/1.1\r\nHost: 127.0.0.1:%d\r\n'
               'Connection: close\r\n\r\n' % port).encode())
    buf = b''
    while b'\r\n\r\n' not in buf:
        c = s.recv(4096)
        if not c:
            break
        buf += c
    head, _, body = buf.partition(b'\r\n\r\n')
    cl = 0
    for line in head.split(b'\r\n'):
        if line.lower().startswith(b'content-length:'):
            cl = int(line.split(b':', 1)[1].strip())
    while len(body) < cl:
        c = s.recv(4096)
        if not c:
            break
        body += c
    s.close()
    return json.loads(body.decode('utf-8', 'ignore'))['webSocketDebuggerUrl']


cdp360.get_browser_ws_url = _ws_url


def port_open(t=0.8):
    s = socket.socket(); s.settimeout(t)
    try:
        s.connect(('127.0.0.1', PORT)); s.close(); return True
    except Exception:
        return False


def ensure_browser():
    if port_open():
        return
    subprocess.Popen([EXE, '--remote-debugging-port=%d' % PORT],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     stdin=subprocess.DEVNULL, close_fds=True,
                     creationflags=0x00000008 | 0x00000200)
    for _ in range(40):
        time.sleep(1)
        if port_open():
            return
    raise RuntimeError('browser not ready on %d' % PORT)


def open_session(url, wait=12):
    ensure_browser()
    b = cdp360.Browser(port=PORT)
    s = cdp360.Session(b.ws, b.attach(
        b.call('Target.createTarget', url='about:blank')['targetId']))
    s.navigate(url, wait=wait)
    try:
        s.call('Page.bringToFront')
    except Exception:
        pass
    return b, s


def wait_ready(s, marker='产品|关键词|生成报告', tries=15):
    for _ in range(tries):
        time.sleep(2)
        t = s.eval('document.body?document.body.innerText:""') or ''
        if len(t) > 400:
            return t
    return s.eval('document.body?document.body.innerText:""') or ''


def api(s, path, body=None, n=200000, timeout_js=True):
    if body is None:
        js = ("(async()=>{const r=await fetch(%s,{credentials:'include'});"
              "return (await r.text()).slice(0,%d);})()" % (json.dumps(path), n))
    else:
        js = ("(async()=>{const r=await fetch(%s,{method:'POST',credentials:'include',"
              "headers:{'Content-Type':'application/json'},body:JSON.stringify(%s)});"
              "return (await r.text()).slice(0,%d);})()"
              % (json.dumps(path), json.dumps(body), n))
    out = s.eval(js) or ''
    try:
        return json.loads(out)
    except Exception:
        return {'_raw': out}


# ---------- 业务 ----------

def quota(s):
    d = api(s, '/v3/api/ai-analysis/daily-remaining-quota', n=500)
    return d.get('data')


def list_reports(s, size=200):
    """拉账号下全部 VOC 报告（该端点忽略一切过滤参数，只能客户端筛）"""
    d = api(s, '/v3/api/review-voc/list',
            {'keyword': '', 'market': '', 'pageSize': size, 'pageNum': 1,
             'labelIdList': []}, n=2000000)
    return ((d.get('data') or {}).get('items') or [])


def find_report(s, asin, market='US'):
    """★ F26：/review-voc/list 忽略 asin 参数，返回账号全部报告。
    必须客户端按 asin 精确匹配，否则永远返回 items[0]（=最近一份报告），
    会把同一个报告的数据写到多个 ASIN 上。"""
    a = (asin or '').strip().upper()
    for it in list_reports(s):
        if (it.get('asin') or '').strip().upper() == a:
            return it
    return None


def create_report(s, asin, market='US'):
    """提交生成报告（消耗 10 次配额）

    ★ F27：改为直调 API，勿走 UI 点击。
    走 UI（选站点→填 ASIN→点「生成报告」）实测成功率仅约 50%：
    el-select 下拉/输入框回填在连续创建时会丢事件，点了按钮但请求没发出去，
    表现为「配额没扣、报告没建、脚本不报错」。
    真实接口（由 fetch/XHR 钩子抓取）：
        POST /v3/api/review-voc/new-task   {"asin":"B0XXXXXXXX","market":"US"}
    """
    return api(s, '/v3/api/review-voc/new-task', {'asin': asin, 'market': market}, n=20000)


def wait_report(s, rid, max_s=1200, step=25):
    """轮询直到报告 ready（站点用字符串 id，保持一致）"""
    t0 = time.time()
    while time.time() - t0 < max_s:
        d = api(s, '/v3/api/review-voc/batch-get-report', {'ids': [str(rid)]}, n=2000)
        it = (d.get('data') or [{}])[0]
        if it.get('ready'):
            return True
        status = it.get('status') or ''
        print('    ... %s %s (%ds)' % (rid, status, int(time.time() - t0)))
        time.sleep(step)
    return False


def fetch_bundle(s, rid):
    d = api(s, '/v3/api/review-voc/task-detail', {'id': str(rid)}, n=2000000)
    inner = ((d.get('data') or {}).get('data') or {})
    out = {}
    for k, v in inner.items():
        if isinstance(v, str) and v.strip().startswith(('{', '[')):
            try:
                out[k] = json.loads(v)
            except Exception:
                out[k] = None
        else:
            out[k] = v
    return out


def extract(bundle, asin):
    agg = bundle.get('aggregationsJson') or {}
    rep = bundle.get('reportJson') or {}
    tl = bundle.get('tagLibraryJson') or {}

    def dist(key):
        return [(x.get('name'), x.get('count')) for x in (agg.get(key) or [])]

    summary = rep.get('summary') or {}
    prod = ((bundle.get('resultJson') or {}).get('product_info') or {})
    return {
        'asin': asin,
        'title': prod.get('title'),
        'price': prod.get('price'),
        'rating': prod.get('rating'),
        'ratings': prod.get('ratings'),
        'degraded': (bundle.get('resultJson') or {}).get('degraded'),
        'degraded_reason': (bundle.get('resultJson') or {}).get('degraded_reason'),
        # ★ 差评点 / 可借鉴点
        'negative_tags': dist('negative_tag_distribution'),
        'positive_tags': dist('positive_tag_distribution'),
        'risk_tags': dist('risk_tag_distribution'),
        'cat_tags': dist('category_specific_distribution'),
        # 结构
        'rating_dist': dist('rating_distribution'),
        'sentiment_dist': dist('sentiment_distribution'),
        'topic_dist': dist('topic_distribution'),
        'scenario_dist': dist('scenario_distribution'),
        'journey_dist': dist('journey_stage_distribution'),
        # AI 归纳
        'summary': summary,
        'root_causes': rep.get('negative_root_causes') or [],
        'insights': rep.get('insights') or [],
        'contexts': rep.get('usage_context_insights') or [],
        'divergences': rep.get('opinion_divergences') or [],
        'low_sample_clues': rep.get('low_sample_clues') or [],
        'tagged_reviews': bundle.get('taggedReviewsJson') or [],
        'tag_library': tl,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--asins', nargs='*', default=[])
    ap.add_argument('--picks')
    ap.add_argument('--out', default='voc_insight.json')
    ap.add_argument('--create', action='store_true',
                    help='报告不存在时提交生成（消耗 10 次配额/个）')
    ap.add_argument('--max-wait', type=int, default=900)
    a = ap.parse_args()

    asins = list(a.asins)
    if a.picks:
        pk = json.load(open(a.picks, encoding='utf-8'))
        if isinstance(pk, dict):
            pk = list(pk.values())
        for d in pk:
            if isinstance(d, str):
                asins.append(d)
            else:
                asins.append(d.get('asin') or d.get('ASIN'))
    asins = [x for x in asins if x]
    if not asins:
        print('no asins'); sys.exit(2)

    b, s = open_session(HOME)
    wait_ready(s)
    print('配额:', quota(s))

    result, todo = {}, []
    for asin in asins:
        r = find_report(s, asin)
        if r and (r.get('status') == 'COMPLETED'):
            print('[%s] 已有报告 id=%s 状态=%s' % (asin, r.get('id'), r.get('status')))
            result[asin] = {'report_id': str(r.get('id')), 'status': r.get('status')}
        elif r:
            print('[%s] 报告存在但未完成 id=%s 状态=%s' % (asin, r.get('id'), r.get('status')))
            result[asin] = {'report_id': str(r.get('id')), 'status': r.get('status')}
            todo.append(asin)
        elif a.create:
            print('[%s] 提交生成（消耗配额）...' % asin)
            r0 = create_report(s, asin)
            print('    -> api: %s' % json.dumps(r0, ensure_ascii=False)[:120])
            rid = ''
            for _ in range(6):          # 新建报告进列表有数秒延迟，重试几次
                time.sleep(3)
                r2 = find_report(s, asin)
                if r2 and r2.get('id'):
                    rid = str(r2.get('id'))
                    break
            print('    -> report_id=%s' % rid)
            if not rid:
                print('    !! 报告未出现在列表中，请稍后重跑本脚本（--create 会再次扣配额，'
                      '故先跑 --asins ... 不带 --create 核对）')
            result[asin] = {'report_id': rid, 'status': (r2 or {}).get('status') if rid else None}
            if rid:
                todo.append(asin)
        else:
            print('[%s] 无报告（未加 --create，跳过）' % asin)

    # 等所有 TODO 就绪
    for asin in todo:
        rid = result[asin]['report_id']
        if not rid:
            continue
        ok = wait_report(s, rid, max_s=a.max_wait)
        print('[%s] 报告 %s ready=%s' % (asin, rid, ok))
        result[asin]['ready'] = ok
    print('剩余配额:', quota(s))

    # 拉数据
    for asin in list(result):
        rid = result[asin].get('report_id')
        if not rid or not result[asin].get('ready', result[asin].get('status') == 'COMPLETED'):
            continue
        try:
            bundle = fetch_bundle(s, rid)
            result[asin].update(extract(bundle, asin))
            nt = result[asin].get('negative_tags') or []
            pt = result[asin].get('positive_tags') or []
            print('[%s] 差评点 %d 项 %s' % (asin, len(nt), nt[:3]))
            print('[%s] 认可点 %d 项 %s' % (asin, len(pt), pt[:3]))
        except Exception as e:
            print('[%s] 拉取失败: %s' % (asin, e))

    json.dump(result, open(a.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('WROTE', a.out, len(result), 'ASIN')
    b.close()


if __name__ == '__main__':
    main()

# -*- coding: utf-8 -*-
"""卖家精灵插件「生成 AI 分析报告」采集 —— 免费通道（不消耗 2.0 额度）

产出（每 ASIN）：
  speed_read   : 买家口碑速读（一句话）
  stars        : {'5':68,'4':13,...}  星级分布百分比
  low_star_pct : 2★+1★ 合计（差评点的量化口径）
  highlights   : 好评亮点
  pain_points  : 差评痛点        ← col14「差评点」的直接来源
  expectations : 买家期待        ← col14「可借鉴」的主要来源
  personas     : 人群画像
  scenarios    : 使用场景
  reasons      : 购买理由

原理（2026-10-08 实测）：
  dp 页插件浮窗 → tab「AI评论分析」→ 按钮「生成 AI 分析报告」→
  **报告直接在面板内渲染（不跳新标签页）**，读面板容器 innerText 即可。
  ⚠ 与「生成卖家精灵分析报告」（变体分布/评论列表，会落网页账号）是两个按钮，别点错。
  功能免费（面板原文「功能免费使用」），不占 /v3/api/ai-analysis/daily-remaining-quota。

用法:
  python ss_ai_report.py --asins B0BQJ2XZWF B0CXXKJYHG --out panel_voc.json
  python ss_ai_report.py --picks picks.json --out panel_voc.json --keep-raw

⚠ 必须在「同一条命令/同一进程」内完成启动浏览器+抓取。
⚠ 首次失败（扩展未注入）→ 自动 reload 重试；仍失败 → 自动换 /gp/product/ 路径。
"""
import argparse
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ss_voc as V  # noqa: E402  (复用其 raw-socket get_browser_ws_url / ensure_browser / api)

PANEL_JS = """(function(){
  var t=null;document.querySelectorAll('.tab-name').forEach(function(e){
    if(/AI评论分析/.test(e.textContent)) t=e;});
  if(!t) return '';
  var p=t;
  for(var i=0;i<12&&p.parentElement;i++){
    p=p.parentElement;
    if(p.innerText&&p.innerText.length>1500) break;}
  return (p.innerText||'');})()"""

CARDS = ['好评亮点', '差评痛点', '买家期待', '人群画像', '使用场景', '购买理由']
KEYMAP = {
    '好评亮点': 'highlights', '差评痛点': 'pain_points', '买家期待': 'expectations',
    '人群画像': 'personas', '使用场景': 'scenarios', '购买理由': 'reasons',
}


def parse_panel(txt):
    """面板文本 → 结构化 VOC"""
    i = txt.find('买家口碑速读')
    j = txt.find('卖家精灵-库存监控')
    if j < 0:
        j = len(txt)
    seg = txt[i:j] if i >= 0 else txt
    out = {}
    m = re.search(r'买家口碑速读\s*\n+\s*(.+)', seg)
    out['speed_read'] = m.group(1).strip() if m else ''
    stars = re.findall(r'([1-5])\s*★\s*(\d+)%', seg)
    st = {s: int(p) for s, p in stars}
    out['stars'] = st
    out['low_star_pct'] = st.get('1', 0) + st.get('2', 0) if st else None
    for idx, name in enumerate(CARDS):
        a = seg.find(name)
        if a < 0:
            out[KEYMAP[name]] = ''
            continue
        nxt = None
        for other in CARDS[idx + 1:]:
            b = seg.find(other, a + len(name))
            if b > 0:
                nxt = b
                break
        if nxt is None:
            nxt = seg.find('卖家精灵-库存监控')
        if nxt is None or nxt < 0:
            nxt = len(seg)
        out[KEYMAP[name]] = re.sub(r'\s+', ' ', seg[a + len(name):nxt]).strip()[:500]
    return out


def ensure_injected(s, tries=8):
    """确保扩展面板已注入（.tab-name >= 6），处理 bot check"""
    for _ in range(tries):
        try:
            s.call('Page.bringToFront')       # 顺序不能反，否则扩展不注入
        except Exception:
            pass
        time.sleep(2)
        body = s.eval('document.body?document.body.innerText:""') or ''
        if 'Continue shopping' in body or 'Continue to site' in body:
            s.eval("(function(){var e=[...document.querySelectorAll('a,button')].find(function(x){"
                   "return /Continue shopping|Continue to site/i.test(x.textContent);});if(e)e.click();})()")
            time.sleep(6)
        if (s.eval("document.querySelectorAll('.tab-name').length") or 0) >= 6:
            return True
    return False


def open_ai_tab(s):
    s.eval("(function(){var t=null;document.querySelectorAll('.tab-name').forEach("
           "function(e){if(/AI评论分析/.test(e.textContent))t=e;});if(t)t.click();})()")
    time.sleep(3)


def click_generate(s):
    return s.eval("(function(){var els=document.querySelectorAll('button');"
                  "for(var i=0;i<els.length;i++){var t=(els[i].textContent||'').trim();"
                  "if(/生成\\s*AI\\s*分析报告/.test(t)){els[i].click();return t;}}return 'NO-BTN';})()")


def dismiss_dialog(s):
    s.eval("(function(){var els=document.querySelectorAll('button,span,div,a');"
           "for(var i=0;i<els.length;i++){var t=(els[i].textContent||'').trim();"
           "if(/我已知晓/.test(t)&&t.length<8){els[i].click();return;}}})()")


def fetch_one(s, asin, max_wait_s=180):
    """返回 (ok, panel_text)"""
    panel = s.eval(PANEL_JS) or ''
    if '评论总结' not in panel:
        r = click_generate(s)
        if r == 'NO-BTN':
            return False, panel
    t0 = time.time()
    while time.time() - t0 < max_wait_s:
        time.sleep(5)
        dismiss_dialog(s)
        panel = s.eval(PANEL_JS) or ''
        if '评论总结' in panel and '差评痛点' in panel:
            return True, panel
    return False, panel


def open_page(bb, url, wait=14):
    """新开一个标签页并导航；导航超时/异常时返回 None（调用方重试）
    ⚠ 每个 ASIN 用独立标签页 —— 复用同一 target 连续导航会在 Amazon 上
      偶发 CDP 响应超时（实测），换新 target 可稳定规避。"""
    tid = bb.call('Target.createTarget', url='about:blank')['targetId']
    s = V.cdp360.Session(bb.ws, bb.attach(tid))
    try:
        s.call('Page.navigate', url=url)
    except Exception:
        try:
            bb.call('Target.closeTarget', targetId=tid)
        except Exception:
            pass
        return None, None
    time.sleep(wait)
    return s, tid


def close_page(bb, tid):
    try:
        bb.call('Target.closeTarget', targetId=tid)
    except Exception:
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--asins', nargs='*', default=[])
    ap.add_argument('--picks')
    ap.add_argument('--out', default='panel_voc.json')
    ap.add_argument('--keep-raw', action='store_true', help='同时保存 panel_<ASIN>.txt 原文')
    ap.add_argument('--max-wait', type=int, default=180)
    a = ap.parse_args()

    asins = list(a.asins)
    if a.picks:
        pk = json.load(open(a.picks, encoding='utf-8'))
        if isinstance(pk, dict):
            pk = list(pk.values())
        for d in pk:
            asins.append(d if isinstance(d, str) else (d.get('asin') or d.get('ASIN')))
    asins = [x for x in asins if x]
    if not asins:
        print('no asins'); sys.exit(2)

    V.ensure_browser()
    bb = V.cdp360.Browser(port=V.PORT)

    result, failed = {}, []
    for asin in asins:
        print('\n===== %s =====' % asin, flush=True)
        ok = False
        # 主路径 dp；失败后换 gp/product（实测能绕过部分 bot check）
        for url in ('https://www.amazon.com/dp/%s' % asin,
                    'https://www.amazon.com/gp/product/%s' % asin):
            for attempt in (1, 2):
                s, tid = open_page(bb, url)
                if s is None:
                    print('  导航超时 → 换新标签页重试', flush=True)
                    continue
                try:
                    if not ensure_injected(s):
                        print('  扩展未注入 → reload', flush=True)
                        try:
                            s.call('Page.reload')
                        except Exception:
                            pass
                        time.sleep(14)
                        if not ensure_injected(s):
                            continue
                    open_ai_tab(s)
                    ok, panel = fetch_one(s, asin, a.max_wait)
                except Exception as e:
                    print('  异常: %s' % e, flush=True)
                    ok = False
                finally:
                    close_page(bb, tid)
                if ok:
                    break
            if ok:
                break
        if ok:
            data = parse_panel(panel)
            data['asin'] = asin
            data['panel_len'] = len(panel)
            result[asin] = data
            if a.keep_raw:
                open('panel_%s.txt' % asin, 'w', encoding='utf-8').write(panel)
            print('  ✓ 差评痛点: %s' % (data['pain_points'] or '')[:90], flush=True)
            print('  ✓ 低星(2★+1★): %s%%' % data['low_star_pct'], flush=True)
        else:
            failed.append(asin)
            print('  ✗ 失败', flush=True)

    json.dump(result, open(a.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('\n===== 汇总 =====')
    print('成功 %d: %s' % (len(result), list(result)))
    print('失败 %d: %s' % (len(failed), failed))
    print('WROTE', a.out)
    bb.close()


if __name__ == '__main__':
    main()

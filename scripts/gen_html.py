# -*- coding: utf-8 -*-
"""把八点判定结果渲染成可视化汇总 HTML

用法:
  python gen_html.py --picks picks.json --pcol p_col.json --reviews reviews.json \
      --out 汇总.html [--title "P 列 · 运营手段八点"]

pcol: {asin: "1.广告:...\n2.合并评论:...\n..."}  或 [ "...", "..." ]
"""
import argparse
import html
import json

NAMES = ['广告', '合并评论', 'Vine', '刷单', '品牌', '站外', '老带新', '上架时间早']

CSS = """
body{font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;
     background:#f7f8fa;color:#1f2328;margin:0;padding:24px}
h1{font-size:19px;margin:0 0 4px}
.sub{color:#6b7280;font-size:13px;margin-bottom:16px}
table{border-collapse:collapse;width:100%;background:#fff;border-radius:8px;
      overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.08);font-size:12px}
th{background:#eef1f5;padding:8px 6px;text-align:left;font-weight:600;
   border-bottom:2px solid #d7dce3;white-space:nowrap}
td{padding:7px 6px;border-bottom:1px solid #eceff3;vertical-align:top;line-height:1.45}
td.y{color:#b42318;font-weight:600}
td.n{color:#067647}
td.m{color:#b54708}
td.idx{color:#98a2b3;width:28px}
td.asin{font-family:ui-monospace,Consolas,monospace;font-weight:600;white-space:nowrap}
td.brand{white-space:nowrap;max-width:110px;overflow:hidden;text-overflow:ellipsis}
td.num{text-align:right;white-space:nowrap;color:#475467}
tr:hover td{background:#f9fafb}
.note{margin-top:14px;font-size:12px;color:#6b7280;line-height:1.7}
.note b{color:#344054}
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--picks', required=True)
    ap.add_argument('--pcol', required=True)
    ap.add_argument('--reviews')
    ap.add_argument('--out', required=True)
    ap.add_argument('--title', default='运营手段八点判定')
    args = ap.parse_args()

    picks = json.load(open(args.picks, encoding='utf-8'))
    if isinstance(picks, dict):
        picks = list(picks.values())
    pcol = json.load(open(args.pcol, encoding='utf-8'))
    if isinstance(pcol, list):
        pcol = {p['asin']: t for p, t in zip(picks, pcol)}
    rev = json.load(open(args.reviews, encoding='utf-8')) if args.reviews else {}

    trs = []
    for i, r in enumerate(picks, 1):
        a = r['asin']
        txt = pcol.get(a, '')
        cells = txt.split('\n')
        tds = []
        for c in cells:
            body = c.split(':', 1)[1] if ':' in c else c
            mark = body[0] if body and body[0] in '✓✗△' else ''
            cls = {'✓': 'y', '✗': 'n', '△': 'm'}.get(mark, '')
            tds.append('<td class="%s">%s</td>' % (cls, html.escape(body)))
        vine = rev.get(a, {}).get('vine', 0)
        trs.append(
            '<tr><td class="idx">%d</td><td class="asin">%s</td><td class="brand">%s</td>'
            '<td class="num">%s</td><td class="num">%s</td><td class="num">%d</td>%s</tr>'
            % (i, a, html.escape(str(r.get('brand') or '')),
               r.get('price') or '', '{:,}'.format(r.get('sales') or 0),
               vine, ''.join(tds)))

    head = ''.join('<th>%s</th>' % n for n in NAMES)
    doc = ('<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">'
           '<title>%s</title><style>%s</style></head><body>'
           '<h1>%s</h1><div class="sub">共 %d 个竞品</div>'
           '<table><tr><th>#</th><th>ASIN</th><th>品牌</th><th>价格</th>'
           '<th>月销</th><th>Vine</th>%s</tr>\n%s\n</table>'
           '<div class="note"><b>口径</b><br>'
           '· <b>Vine</b> 卖家精灵 review-analysis/type 的 vine 真实条数，&gt;0 记 ✓<br>'
           '· <b>合并评论</b> comment API 切 market 查多站点，存在非美站点评论记 ✓<br>'
           '· <b>刷单</b> 近30天评论数 ÷ 近30天销量，&gt;3%% 记疑似<br>'
           '· <b>站外</b> 独立站 + 社媒 + 红人测评 + Deal 站 综合核查，有实证才记「有」<br>'
           '· <b>老带新</b> 父体变体组中是否存在上架更早的 ASIN<br>'
           '· <b>上架时间早</b> 上架天数 ≥1095 天（3 年）记 ✓'
           '</div></body></html>'
           ) % (html.escape(args.title), CSS, html.escape(args.title),
                len(picks), head, '\n'.join(trs))
    open(args.out, 'w', encoding='utf-8').write(doc)
    print('WROTE', args.out, len(doc), 'bytes')


if __name__ == '__main__':
    main()

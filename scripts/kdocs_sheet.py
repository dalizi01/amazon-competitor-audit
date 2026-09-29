# -*- coding: utf-8 -*-
"""kdocs 表格写入 + 校验（0-based 行号，写入后强制逐行比对）

⚠ 核心规则：range_data 的 row_from 是 **0-based**
     表头 -> 0    第 1 条数据 -> 1    第 k 条数据 -> k
   写错会整列错位一行，且 API 仍返回成功，所以必须 verify。

用法:
  # 写入（data.json 是字符串数组，或 {asin: 文本} 对象）
  python kdocs_sheet.py write --file <ID> --ws 2 --col 15 --data p_col.json --start-row 1

  # 校验（拿 ASIN 列和目标列逐行比对）
  python kdocs_sheet.py verify --file <ID> --ws 2 --key-col 0 --col 15 \
      --expect asins.json

  # 清空某列某行
  python kdocs_sheet.py clear --file <ID> --ws 2 --col 15 --row 21

  # 设行高 / 列宽
  python kdocs_sheet.py height --file <ID> --ws 2 --row-from 1 --row-to 20 --height 2160
"""
import argparse
import json
import os
import shutil
import subprocess
import sys


def _find_kdocs():
    """定位 kdocs-cli：环境变量 KDOCS_CLI > PATH > 常见安装路径。"""
    env = os.environ.get('KDOCS_CLI')
    if env:
        return env
    for name in ('kdocs-cli', 'kdocs-cli.exe'):
        w = shutil.which(name)
        if w:
            return w
    for p in (
        os.path.expandvars(r'%LOCALAPPDATA%\kdocs-cli\kdocs-cli.exe'),
        os.path.expandvars(r'%USERPROFILE%\AppData\Local\kdocs-cli\kdocs-cli.exe'),
    ):
        if os.path.exists(p):
            return p
    return 'kdocs-cli'


KDOCS = _find_kdocs()


def k(*a):
    r = subprocess.run([KDOCS] + list(a), capture_output=True, text=True,
                       encoding='utf-8', errors='replace')
    return r.returncode, ((r.stdout or '') + (r.stderr or ''))


def load_data(path):
    d = json.load(open(path, encoding='utf-8'))
    if isinstance(d, dict):
        return list(d.values())
    return list(d)


def write(file_id, ws, col, values, start_row, batch=5):
    ops = []
    for i, v in enumerate(values):
        row = start_row + i
        ops.append({'op_type': 'cell_operation_type_formula',
                    'row_from': row, 'row_to': row,
                    'col_from': col, 'col_to': col, 'formula': v})
    ok = 0
    for s in range(0, len(ops), batch):
        rc, out = k('sheet', 'range-data-batch-update', json.dumps(
            {'file_id': file_id, 'worksheet_id': ws,
             'range_data': ops[s:s + batch]}, ensure_ascii=False))
        if rc == 0:
            ok += len(ops[s:s + batch])
        else:
            print('batch %d rc=%d %s' % (s // batch, rc, out[:300]))
    print('写入: %d/%d 格 (row %d..%d, 0-based)' %
          (ok, len(ops), start_row, start_row + len(values) - 1))
    return ok


def read_col(file_id, ws, col, row_from, row_to):
    rc, out = k('sheet', 'get-range-data', json.dumps(
        {'file_id': file_id, 'worksheet_id': ws,
         'range': {'rowFrom': row_from, 'rowTo': row_to,
                   'colFrom': col, 'colTo': col}}, ensure_ascii=False))
    if rc != 0:
        print('read failed', out[:300])
        return []
    try:
        # kdocs-cli 尾部会追加升级提示(如 ⚠ kdocs-cli v2.7.1 available...)，需先剥离，
        # 否则 json.loads 报 "Extra data" → 解析失败返回 [] → 校验误判。
        out = out[: out.rfind('}') + 1]
        d = json.loads(out)
        return [(c.get('cellText') or '') for c in d['data']['detail']['rangeData']]
    except Exception as e:
        print('parse fail', e, out[:300])
        return []


def verify(file_id, ws, key_col, col, expect, start_row=1):
    """expect: ASIN 列表。比对 key_col 的 ASIN 与 col 的内容是否一一对应。"""
    n = len(expect)
    keys = read_col(file_id, ws, key_col, start_row, start_row + n - 1)
    vals = read_col(file_id, ws, col, start_row, start_row + n - 1)
    bad = 0
    for i, exp in enumerate(expect):
        got_key = (keys[i] if i < len(keys) else '').strip()
        val = (vals[i] if i < len(vals) else '').strip()
        okk = (got_key == exp)
        okv = bool(val)
        if not (okk and okv):
            bad += 1
        print('%2d  %-12s expect=%-12s key=%-12s %s | val=%s' %
              (i + 1, 'OK' if (okk and okv) else 'MISMATCH', exp, got_key,
               '✓' if okk else '✗', val[:60].replace('\n', ' / ')))
    print('\n校验: %d/%d 行对齐' % (n - bad, n))
    return bad == 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['write', 'verify', 'clear', 'height', 'read'])
    ap.add_argument('--file', required=True)
    ap.add_argument('--ws', type=int, required=True)
    ap.add_argument('--col', type=int)
    ap.add_argument('--data')
    ap.add_argument('--expect')
    ap.add_argument('--key-col', type=int, default=0)
    ap.add_argument('--start-row', type=int, default=1, help='0-based, 表头下第1行=1')
    ap.add_argument('--row', type=int)
    ap.add_argument('--row-from', type=int)
    ap.add_argument('--row-to', type=int)
    ap.add_argument('--height', type=int)
    ap.add_argument('--width', type=int)
    args = ap.parse_args()

    if args.cmd == 'write':
        vals = load_data(args.data)
        write(args.file, args.ws, args.col, vals, args.start_row)
    elif args.cmd == 'verify':
        exp = json.load(open(args.expect, encoding='utf-8'))
        if isinstance(exp, dict):
            exp = [v.get('asin') for v in exp.values()]
        elif exp and isinstance(exp[0], dict):
            exp = [v.get('asin') for v in exp]
        verify(args.file, args.ws, args.key_col, args.col, exp, args.start_row)
    elif args.cmd == 'clear':
        write(args.file, args.ws, args.col, [''], args.row)
    elif args.cmd == 'height':
        rng = {'row_from': args.row_from, 'row_to': args.row_to,
               'col_from': args.col, 'col_to': args.col}
        payload = {'file_id': args.file, 'worksheet_id': args.ws, 'range': rng}
        if args.height:
            payload['height'] = args.height
        if args.width:
            payload['width'] = args.width
        rc, out = k('sheet', 'set-range-width-height', json.dumps(payload, ensure_ascii=False))
        print('rc', rc, out[:300])
    elif args.cmd == 'read':
        rows = read_col(args.file, args.ws, args.col,
                        args.row_from or 0, args.row_to or 20)
        for i, t in enumerate(rows):
            print(i, ':', t[:100].replace('\n', ' / '))


if __name__ == '__main__':
    main()

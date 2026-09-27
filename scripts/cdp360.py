# -*- coding: utf-8 -*-
"""
360 浏览器 CDP 客户端 (raw socket, 无第三方依赖)

关键坑 (来自 ~/.workbuddy/troubleshooting-log.md):
  - 360 浏览器禁 /json/list, /json/new (405 或返回空) -> 只能走浏览器级 WS + Target 域
  - WS 握手**不能发 Origin 头**, 否则 403 (启动没带 --remote-allow-origins)
  - kdocs 是 canvas 渲染, DOM 拿不到单元格 -> 只能截图看

用法:
  python cdp360.py targets                      # 列出所有页面
  python cdp360.py open <url>                   # 新开标签页并导航
  python cdp360.py shot <url> <out.png> [wait]  # 打开并截图
"""
import base64
import json
import os
import socket
import struct
import sys
import time

CDP_HOST = "127.0.0.1"
DEFAULT_PORT = 9222


# ---------- raw websocket ----------

class WS:
    def __init__(self, host, port, path, timeout=30):
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.sock.settimeout(timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        # 注意: 这里刻意不发 Origin 头, 360 浏览器带 Origin 会 403
        req = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n"
            f"\r\n"
        )
        self.sock.sendall(req.encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise RuntimeError("WS handshake failed: connection closed")
            buf += chunk
        head = buf.split(b"\r\n\r\n", 1)
        status = head[0].split(b"\r\n")[0].decode()
        if "101" not in status:
            raise RuntimeError(f"WS handshake failed: {status}\n{head[0].decode()}")
        self.buf = head[1]

    def _recv_exact(self, n):
        while len(self.buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise RuntimeError("socket closed")
            self.buf += chunk
        data, self.buf = self.buf[:n], self.buf[n:]
        return data

    def send(self, text):
        payload = text.encode()
        mask = os.urandom(4)
        n = len(payload)
        header = b"\x81"
        if n < 126:
            header += struct.pack("!B", 0x80 | n)
        elif n < 65536:
            header += struct.pack("!BH", 0x80 | 126, n)
        else:
            header += struct.pack("!BQ", 0x80 | 127, n)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(header + mask + masked)

    def recv(self):
        while True:
            b0, b1 = self._recv_exact(2)
            opcode = b0 & 0x0F
            ln = b1 & 0x7F
            if ln == 126:
                ln = struct.unpack("!H", self._recv_exact(2))[0]
            elif ln == 127:
                ln = struct.unpack("!Q", self._recv_exact(8))[0]
            payload = self._recv_exact(ln) if ln else b""
            if opcode == 0x1:      # text
                return payload.decode("utf-8", "ignore")
            if opcode == 0x8:      # close
                raise RuntimeError("server closed ws")
            # 0x9 ping / 0xA pong / 0x2 binary -> skip

    def close(self):
        try:
            self.sock.close()
        except Exception:
            pass


# ---------- CDP session ----------

def get_browser_ws_url(port=DEFAULT_PORT):
    """拿浏览器级 WS 地址.

    坑 1: 系统代理会劫持 127.0.0.1 -> curl 要 --noproxy '*', urllib 要清空 ProxyHandler.
    坑 2 (sandbox): python 自己发网络请求会被 sandbox 拦, 但 curl 可以.
          所以标准调用姿势是让 python 跑在 curl 管道里, 从 stdin 拿 /json/version:

            curl -s --noproxy '*' http://127.0.0.1:<port>/json/version | python cdp360.py targets

          脚本优先读 stdin; stdin 为空才自己发请求 (非 sandbox 环境下可用).
    """
    raw = ""
    try:
        if not sys.stdin.isatty():
            raw = sys.stdin.read()
    except Exception:
        raw = ""
    if raw.strip():
        try:
            return json.loads(raw)["webSocketDebuggerUrl"]
        except Exception:
            pass

    import urllib.request
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request("http://127.0.0.1:%d/json/version" % port,
                                 headers={"Host": "127.0.0.1:%d" % port})
    with opener.open(req, timeout=10) as r:
        return json.load(r)["webSocketDebuggerUrl"]


class Browser:
    def __init__(self, port=DEFAULT_PORT):
        url = get_browser_ws_url(port)
        # ws://127.0.0.1:<port>/devtools/browser/<uuid>
        path = url.split("127.0.0.1:%d" % port, 1)[1]
        self.ws = WS(CDP_HOST, port, path)
        self.mid = 0

    def call(self, method, **params):
        self.mid += 1
        mid = self.mid
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params}))
        deadline = time.time() + 30
        while time.time() < deadline:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})
        raise RuntimeError(f"{method}: timeout")

    def get_targets(self):
        res = self.call("Target.getTargets")
        return [t for t in res.get("targetInfoList", []) if t.get("type") == "page"]

    def attach(self, target_id):
        res = self.call("Target.attachToTarget", targetId=target_id, flatten=True)
        return res["sessionId"]

    def close(self):
        self.ws.close()


class Session:
    def __init__(self, ws, session_id):
        self.ws = ws
        self.sid = session_id
        self.mid = 1000

    def call(self, method, **params):
        self.mid += 1
        mid = self.mid
        payload = {"id": mid, "method": method, "params": params,
                   "sessionId": self.sid}
        self.ws.send(json.dumps(payload))
        deadline = time.time() + 60
        while time.time() < deadline:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == mid and msg.get("sessionId") == self.sid:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})
        raise RuntimeError(f"{method}: timeout")

    def eval(self, expr):
        res = self.call("Runtime.evaluate", expression=expr,
                        returnByValue=True, awaitPromise=True)
        if res.get("exceptionDetails"):
            return None
        return res.get("result", {}).get("value")

    def navigate(self, url, wait=6):
        self.call("Page.enable")
        self.call("Page.navigate", url=url)
        time.sleep(wait)

    def screenshot(self, out_path):
        res = self.call("Page.captureScreenshot", format="png",
                        captureBeyondViewport=True)
        data = res.get("data")
        if not data:
            raise RuntimeError("screenshot returned no data")
        with open(out_path, "wb") as f:
            f.write(base64.b64decode(data))
        return out_path


# ---------- CLI ----------

def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "targets"
    b = Browser()
    try:
        if cmd == "targets":
            for t in b.get_targets():
                print(f"{t['targetId']}  {t.get('title','')[:50]:50s}  {t.get('url','')}")
            return

        if cmd == "open":
            url = sys.argv[2]
            tid = b.call("Target.createTarget", url=url)["targetId"]
            print("created target:", tid)
            time.sleep(3)
            sid = b.attach(tid)
            s = Session(b.ws, sid)
            b.call("Target.activateTarget", targetId=tid)
            time.sleep(8)
            print("title:", s.eval("document.title"))
            print("url  :", s.eval("location.href"))
            return

        if cmd == "shot":
            url = sys.argv[2]
            out = sys.argv[3]
            wait = int(sys.argv[4]) if len(sys.argv) > 4 else 12
            tid = b.call("Target.createTarget", url=url)["targetId"]
            sid = b.attach(tid)
            s = Session(b.ws, sid)
            b.call("Target.activateTarget", targetId=tid)
            time.sleep(wait)
            title = s.eval("document.title")
            href = s.eval("location.href")
            print("title:", title)
            print("url  :", href)
            s.screenshot(out)
            print("saved:", out, os.path.getsize(out), "bytes")
            return

        print("unknown cmd", cmd)
    finally:
        b.close()


if __name__ == "__main__":
    main()

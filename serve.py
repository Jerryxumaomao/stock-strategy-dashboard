#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本地看板服务器 —— 让页面右上角「刷新数据」按钮能工作(静态 file:// 打不了本地 build 管线)。
  GET  /         -> 每次从磁盘读最新 dashboard.html
  POST /refresh  -> 后台跑 `python run.py build`(拉最新数据+重算),立即返回;忙碌则拒绝
  GET  /status   -> {pct, stage, running, done, error} 供进度条轮询

用法(跨平台): python serve.py   然后浏览器开 http://127.0.0.1:8766
A股分支需 akshare 可达(见 README-ashare);美股分支用 yahoo(默认)。刷新失败会诚实报错,不假装成功。
"""
import os, sys, json, threading, subprocess, http.server, socketserver, webbrowser

ROOT = os.path.dirname(os.path.abspath(__file__))
HTML = os.path.join(ROOT, "dashboard.html")
PORT = 8766
PY = sys.executable

STATUS = {"pct": 0, "stage": "待命 / idle", "running": False, "done": False, "error": None}
LOCK = threading.Lock()


def _set(**kw):
    with LOCK:
        STATUS.update({k: v for k, v in kw.items() if v is not None})


def do_refresh():
    """跑 run.py build;逐阶段更新进度。失败诚实报错、不置 done。"""
    try:
        _set(pct=8, stage="拉取数据 + 重算(run.py build)…", running=True, done=False, error=None)
        # 逐行读 build 输出,按已诊断的 ticker 数推进度(比死等更真实)
        # -u 无缓冲: 否则 run.py 的 print 会被缓冲,进度条一直卡在起点直到 build 整体结束
        proc = subprocess.Popen([PY, "-u", "run.py", "build"], cwd=ROOT, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, bufsize=1,
                                env={**os.environ, "PYTHONUNBUFFERED": "1"})
        seen = 0
        for line in proc.stdout:
            if "] dashboard ->" in line:
                _set(pct=92, stage="写入看板 + 复盘…")
            elif ":" in line and ("宜" in line or "回避" in line or "avoid" in line or "brk" in line or "dip" in line or "hold" in line):
                seen += 1
                _set(pct=min(88, 12 + seen * 4), stage=f"已诊断 {seen} 只…")
        proc.wait()
        if proc.returncode != 0:
            _set(running=False, error="build 失败(退出码 %d);数据源是否可达?" % proc.returncode)
            return
        if not os.path.exists(HTML):
            _set(running=False, error="build 完成但未找到 dashboard.html")
            return
        _set(pct=100, stage="完成 / done", running=False, done=True)
    except Exception as e:
        _set(running=False, error=str(e)[:140])


class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        b = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path.startswith("/status"):
            with LOCK:
                self._send(200, json.dumps(STATUS))
        elif self.path == "/" or self.path.startswith("/dashboard"):
            try:
                self._send(200, open(HTML, encoding="utf-8").read(), "text/html; charset=utf-8")
            except Exception as e:
                self._send(500, "dashboard.html 读取失败,先跑一次 python run.py build:" + str(e), "text/plain; charset=utf-8")
        else:
            self._send(404, "not found", "text/plain")

    def do_POST(self):
        if self.path.startswith("/refresh"):
            with LOCK:
                if STATUS["running"]:
                    self._send(200, json.dumps({"busy": True})); return
            _set(pct=0, stage="启动…", running=True, done=False, error=None)
            threading.Thread(target=do_refresh, daemon=True).start()
            self._send(200, json.dumps({"started": True}))
        else:
            self._send(404, "not found", "text/plain")


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main():
    url = f"http://127.0.0.1:{PORT}/"
    try:
        srv = Server(("127.0.0.1", PORT), H)
    except OSError as e:
        print(f"端口 {PORT} 被占用(可能已有服务器在跑):{e}\n直接开浏览器访问 {url} 即可。")
        try: webbrowser.open(url)
        except Exception: pass
        return
    print(f"看板服务器已启动: {url}  (Ctrl+C 停止)")
    try: webbrowser.open(url)
    except Exception: pass
    srv.serve_forever()


if __name__ == "__main__":
    main()

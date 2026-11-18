#!/usr/bin/env python3
"""Минимальная страница 800×480 для проверки дозвона с S570HD."""

from __future__ import annotations

import http.server
import socketserver
import time

PORT = 4731

PAGE = """<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01//EN">
<html><head>
<meta http-equiv="Content-Type" content="text/html; charset=windows-1251">
<meta http-equiv="refresh" content="15">
<title>HA Panel</title>
<style type="text/css">
html,body{margin:0;padding:0;width:800px;height:480px;overflow:hidden;
background:#111;color:#eee;font-family:Tahoma,sans-serif;}
table{width:800px;height:480px;border-collapse:collapse;}
td{text-align:center;vertical-align:middle;}
h1{font-size:48px;margin:0 0 12px 0;}
p{font-size:22px;margin:8px;}
.ok{color:#8f8;}
</style>
</head><body>
<table><tr><td>
<h1>HA Panel</h1>
<p class="ok">Bluetooth-дозвон работает</p>
<p>%(clock)s</p>
<p>10.44.0.1:%(port)s</p>
</td></tr></table>
</body></html>
"""


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = (
            PAGE
            % {
                "clock": time.strftime("%H:%M:%S  %d.%m.%Y"),
                "port": PORT,
            }
        ).encode("cp1251", "replace")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=windows-1251")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args) -> None:
        print("http: " + (fmt % args), flush=True)


class ReuseServer(socketserver.TCPServer):
    allow_reuse_address = True


def main() -> None:
    with ReuseServer(("0.0.0.0", PORT), Handler) as httpd:
        print("Проверочная страница: http://0.0.0.0:%s/" % PORT, flush=True)
        print("С навигатора после дозвона: http://10.44.0.1:%s/" % PORT, flush=True)
        httpd.serve_forever()


if __name__ == "__main__":
    main()

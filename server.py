#!/usr/bin/env python3
import json
import os
import socket
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

PORT = int(os.environ.get("PORT", "8765"))
MAX_READINGS = 1000
readings = []
DIR = os.path.dirname(os.path.abspath(__file__))


def parse_line(line):
    line = line.strip()
    if not line:
        return None
    if "," in line:
        left, right = line.split(",", 1)
        try:
            return int(left), float(right)
        except ValueError:
            return None
    try:
        ts = int(datetime.now(timezone.utc).timestamp())
        return ts, float(line)
    except ValueError:
        return None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {args[0]}")

    def do_POST(self):
        if urlparse(self.path).path != "/api/data":
            self.send_error(404)
            return

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8", errors="replace")
        added = 0
        recv_at = datetime.now(timezone.utc).isoformat()

        for line in body.splitlines():
            parsed = parse_line(line)
            if not parsed:
                continue
            ts, flow = parsed
            readings.append({"ts": ts, "flow": flow, "recv_at": recv_at})
            added += 1

        while len(readings) > MAX_READINGS:
            readings.pop(0)

        print(f"POST +{added}, total {len(readings)}")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(b"OK")

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/api/readings":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(readings).encode("utf-8"))
            return

        if path in ("/", "/index.html"):
            with open(os.path.join(DIR, "index.html"), "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(data)
            return

        self.send_error(404)


def local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def main():
    ip = local_ip()
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Browser:  http://127.0.0.1:{PORT}/")
    print(f"Modem POST http://{ip}:{PORT}/api/data")
    print("Body: unix_sec,flow  (one line per reading)")
    server.serve_forever()


if __name__ == "__main__":
    main()

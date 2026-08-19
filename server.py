#!/usr/bin/env python3
import json
import logging
import os
import re
import socket
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from logging.handlers import TimedRotatingFileHandler
from urllib.parse import urlparse

PORT = int(os.environ.get("PORT", "8765"))
MAX_READINGS = 1000
MAX_LOG_LINES = 1000
readings = []
modem_logs = []
DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(DIR, "server_errors.log")
FLOW_RE = re.compile(r"^\d{1,4}\.\d(?:\d)?$")


def setup_logging():
    logger = logging.getLogger("flow_server")
    if logger.handlers:
        return logger
    logger.setLevel(logging.ERROR)
    handler = TimedRotatingFileHandler(
        LOG_FILE, when="midnight", backupCount=0, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    logger.addHandler(handler)
    return logger


log = setup_logging()


def parse_line(line):
    head = line.lstrip().split(";", 1)[0]
    if not FLOW_RE.fullmatch(head):
        return None
    ts = int(datetime.now(timezone.utc).timestamp())
    return ts, float(head)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        try:
            if len(args) >= 2 and int(args[1]) >= 400:
                log.error("%s", args[0])
        except (ValueError, TypeError):
            pass

    def do_POST(self):
        try:
            if urlparse(self.path).path != "/api/data":
                self.send_error(404)
                return

            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8", errors="replace")
            added = 0
            recv_at = datetime.now(timezone.utc).isoformat()
            recv_ts = int(datetime.now(timezone.utc).timestamp())

            for line in body.splitlines():
                line = line.strip()
                if not line:
                    continue

                modem_logs.append({"ts": recv_ts, "recv_at": recv_at, "raw": line})
                while len(modem_logs) > MAX_LOG_LINES:
                    modem_logs.pop(0)

                parsed = parse_line(line)
                if not parsed:
                    continue
                ts, flow = parsed
                readings.append({"ts": ts, "flow": flow, "recv_at": recv_at})
                added += 1

            while len(readings) > MAX_READINGS:
                readings.pop(0)

            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(b"OK")
        except Exception:
            log.exception("POST /api/data failed")
            self.send_error(500)

    def do_GET(self):
        try:
            path = urlparse(self.path).path

            if path == "/api/readings":
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps(readings).encode("utf-8"))
                return

            if path == "/api/logs":
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps(modem_logs).encode("utf-8"))
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
        except Exception:
            log.exception("GET %s failed", self.path)
            self.send_error(500)


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
    print(f"Errors:   {LOG_FILE}")
    server.serve_forever()


if __name__ == "__main__":
    main()

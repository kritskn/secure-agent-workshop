"""Immutable, credential-free localhost gateway to the internal edited app.

Only the fixed app destination is contacted. No redirects, environment proxies,
CONNECT, arbitrary destinations, project execution, credentials or saved traffic.
"""

import argparse
import os
import platform
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MAX_BODY = 128 * 1024
BACKEND = ("app.workshop.test", 8080)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def respond(self, status, body, content_type="application/json"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def relay(self):
        hosts = {f"{host}:{self.server.public_port}" for host in ("127.0.0.1", "localhost")}
        lengths = self.headers.get_all("Content-Length", [])
        host_values = self.headers.get_all("Host", [])
        if (len(host_values) != 1 or host_values[0] not in hosts
                or self.headers.get("Transfer-Encoding") or self.headers.get("Upgrade")
                or len(lengths) > 1 or not self.path.startswith("/")
                or self.path.startswith("//") or len(self.path) > 2048
                or any(ord(char) < 32 or ord(char) == 127 for char in self.path)):
            self.respond(400, b'{"error":"Invalid gateway request"}')
            return
        length = lengths[0] if lengths else "0"
        if not length.isascii() or not length.isdecimal() or len(length) > 6 or int(length) > MAX_BODY:
            self.respond(400, b'{"error":"Invalid request size"}')
            return
        length = int(length)
        if self.command == "GET" and length:
            self.respond(400, b'{"error":"Invalid GET body"}')
            return
        connection = HTTPConnection(*BACKEND, timeout=5)
        try:
            body = self.rfile.read(length)
            if len(body) != length:
                raise ValueError("Incomplete request")
            # Preserve browser Host/Origin for the app's existing same-origin
            # checks; never forward auth/cookies or caller-selected routing.
            headers = {name: self.headers[name] for name in ("Host", "Origin", "Content-Type")
                       if name in self.headers}
            connection.request(self.command, self.path, body=body, headers=headers)
            response = connection.getresponse()
            payload = response.read(MAX_BODY + 1)
            if len(payload) > MAX_BODY or not 200 <= response.status <= 599:
                raise ValueError("Invalid response bound")
            # No Location/Set-Cookie/hop-by-hop headers, no redirect following.
            content_type = response.getheader("Content-Type", "application/octet-stream")
            if "\r" in content_type or "\n" in content_type:
                raise ValueError("Invalid response header")
        except Exception:  # noqa: BLE001 - Redact upstream transport/response details.
            self.respond(502, b'{"error":"App unavailable"}')
        else:
            self.respond(response.status, payload, content_type)
        finally:
            connection.close()

    do_GET = relay
    do_POST = relay


class BoundedServer(ThreadingHTTPServer):
    # Idle browser preconnections do not block other requests. Docker's PID and
    # memory limits bound concurrency; client sockets and upstream calls time out.
    daemon_threads = True

    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(5)
        return connection, address


def main(args=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public-port", required=True, type=int)
    options = parser.parse_args(args)
    if (platform.system() != "Linux" or os.geteuid() != 1000
            or os.environ.get("SECAGENT_LAB2_GATEWAY") != "1"
            or any(name in os.environ for name in ("OLLAMA_API_KEY", "WORKSHOP_PROXY_TOKEN"))
            or not 1024 <= options.public_port <= 65535):
        parser.error("Approved credential-free gateway guest required")
    with BoundedServer(("0.0.0.0", 8080), Handler) as server:
        server.public_port = options.public_port
        server.serve_forever()


if __name__ == "__main__":
    main()

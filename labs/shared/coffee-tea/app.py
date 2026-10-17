"""Coffee/Tea workshop starter with a shared-order bug to repair.

Uses synthetic drink orders. Importing starts no server and writes no files.
"""

import argparse
import json
from functools import partial
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlsplit

DEFAULTS = {
    "coffee": {"team_id": "coffee", "drink": "coffee", "temperature": "iced", "sweetness": 25},
    "tea": {"team_id": "tea", "drink": "matcha", "temperature": "iced", "sweetness": 50},
}
PAGE = Path(__file__).with_name("index.html")
HEALTH = {"service": "after-lunch-recharge-poc", "schema": 1}
MAX_BODY_BYTES = 512


def order_path(output_dir, team_id):
    """Select the artifact used by saving and retrieval."""
    if team_id not in DEFAULTS:
        raise ValueError("Unknown team")
    return output_dir / "latest-order.json"


def save_order(output_dir, team_id, selection):
    """Save one team's validated drink selection; team/drink identity is fixed."""
    path = order_path(output_dir, team_id)
    if (not isinstance(selection, dict) or set(selection) != {"temperature", "sweetness"}
            or selection["temperature"] not in ("iced", "hot")
            or type(selection["sweetness"]) is not int
            or selection["sweetness"] not in (0, 25, 50, 75, 100)):
        raise ValueError("Choose iced/hot and a sweetness of 0, 25, 50, 75 or 100")
    order = DEFAULTS[team_id] | selection
    path.write_text(json.dumps(order, indent=2) + "\n", encoding="utf-8")
    return order


def read_order(output_dir, team_id):
    """Return saved state, or that team's default when no artifact exists."""
    path = order_path(output_dir, team_id)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return DEFAULTS[team_id].copy()


class DrinkHandler(BaseHTTPRequestHandler):
    """Serve only the page and named API routes; never browse directories."""

    def __init__(self, *args, output_dir, public_port=None, internal_host=None, **kwargs):
        self.output_dir = output_dir
        self.public_port = public_port
        self.internal_host = internal_host
        super().__init__(*args, **kwargs)

    def respond(self, status, body, content_type="application/json; charset=utf-8"):
        if not isinstance(body, bytes):
            body = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def handle_route(self, method):
        # Loopback browser origins only, including an explicitly mapped host port.
        ports = {self.server.server_port}
        if self.public_port is not None:
            ports.add(self.public_port)
        hosts = {f"{host}:{port}" for host in ("127.0.0.1", "localhost") for port in ports}
        if self.internal_host is not None:
            hosts.add(f"{self.internal_host}:{self.server.server_port}")
        host = self.headers.get("Host")
        origin = self.headers.get("Origin")
        if host not in hosts or (origin is not None and origin != f"http://{host}"):
            self.respond(403, {"error": "Use the local workshop URL"})
            return
        parsed = urlsplit(self.path)
        if "?" in self.path or parsed.fragment or parsed.scheme or parsed.netloc:
            self.respond(404, {"error": "Unknown route"})
            return
        route = parsed.path
        if method == "GET" and route == "/":
            self.respond(200, PAGE.read_bytes(), "text/html; charset=utf-8")
            return
        if method == "GET" and route == "/health":
            self.respond(200, HEALTH)
            return
        if method == "GET" and route == "/api/orders":
            self.respond(200, [{"team_id": team, "order": read_order(self.output_dir, team)}
                               for team in DEFAULTS])
            return
        prefix = "/api/orders/"
        if (method != "POST" or not route.startswith(prefix)
                or route[len(prefix):] not in DEFAULTS):
            self.respond(404, {"error": "Unknown route or team"})
            return
        if self.headers.get("Transfer-Encoding"):
            self.respond(400, {"error": "Transfer encoding is not supported"})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            size = 0
        if not 0 < size <= MAX_BODY_BYTES:
            self.respond(400, {"error": "Provide a JSON selection of 1 to 512 bytes"})
            return
        if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
            self.respond(415, {"error": "Use application/json"})
            return
        try:
            raw = self.rfile.read(size)
            if len(raw) != size:
                raise ValueError("Incomplete selection")
            selection = json.loads(raw.decode("utf-8"))
            order = save_order(self.output_dir, route[len(prefix):], selection)
        except (ValueError, UnicodeError):
            self.respond(400, {"error": "Invalid selection; choose iced/hot and 0/25/50/75/100 sweetness"})
            return
        self.respond(200, order)

    def do_GET(self):
        self.handle_route("GET")

    def do_POST(self):
        self.handle_route("POST")


def main():
    parser = argparse.ArgumentParser(description="Coffee/Tea workshop app; starts a local HTTP server")
    parser.add_argument("--output-dir", type=Path, required=True,
                        help="new disposable directory; existing paths are refused")
    parser.add_argument("--port", type=int, default=0,
                        help="host loopback port (default: choose a free port)")
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error("port must be between 0 and 65535")
    output_dir = args.output_dir.absolute()
    if output_dir.exists() or output_dir.is_symlink():
        parser.error("output directory already exists; preserve it and choose a new path")
    handler = partial(DrinkHandler, output_dir=output_dir)
    try:
        with HTTPServer(("127.0.0.1", args.port), handler) as server:
            output_dir.mkdir(mode=0o700)
            print(f"After-Lunch Recharge prototype: http://127.0.0.1:{server.server_port}", flush=True)
            print(f"Synthetic orders: {output_dir}", flush=True)
            print("Ctrl+C stops the server; orders are retained.", flush=True)
            server.serve_forever()
    except KeyboardInterrupt:
        pass
    except OSError as error:
        parser.exit(1, f"Cannot run prototype: {error}\n")


if __name__ == "__main__":
    main()

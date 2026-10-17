"""Disposable publication service, NOT a policy enforcement or event simulator."""
import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from page import render

CASES = ("control", "protected")
MAX_PAGE = 32768
# Browser defense in depth, not HTML sanitization or a navigation boundary.
CONTENT_SECURITY_POLICY = (
    "default-src 'none'; script-src 'self'; style-src 'unsafe-inline'; img-src data:; "
    "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)


def initialize(root, original):
    """Create fresh site state, refusing to replace existing work."""
    root.mkdir(exist_ok=True)
    for case in CASES:
        directory = root / case
        directory.mkdir()
        (directory / "live.html").write_bytes(render(original, "live"))
        (directory / "preview.html").write_bytes(render(original, "preview"))
        (directory / "preview-source.html").write_bytes(original)


def handler(root):
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def reply(self, status, body, content_type="text/plain; charset=utf-8"):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Security-Policy", CONTENT_SECURITY_POLICY)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)
            self.close_connection = True

        def do_GET(self):
            if self.path == "/local-time.js":
                self.reply(200, Path(__file__).with_name("local-time.js").read_bytes(),
                           "text/javascript; charset=utf-8")
                return
            pages = {f"/{case}/{page}.html": root / case / f"{page}.html"
                     for case in CASES for page in ("preview", "live")}
            if self.path not in pages:
                self.reply(404, b"Unknown synthetic site page")
                return
            self.reply(200, pages[self.path].read_bytes(), "text/html; charset=utf-8")

        def do_POST(self):
            case = self.headers.get("X-Workshop-Case", "")
            if case not in CASES or self.path not in ("/preview", "/publish"):
                self.reply(404, b"Unknown synthetic operation")
                return
            if self.headers.get("Transfer-Encoding"):
                self.reply(400, b"Use a fixed Content-Length")
                return
            try:
                size = int(self.headers.get("Content-Length", "-1"))
            except ValueError:
                size = -1
            if not 0 <= size <= MAX_PAGE:
                self.reply(400, b"Invalid body length")
                return
            body = self.rfile.read(size)
            if len(body) != size:
                self.reply(400, b"Incomplete body")
                return
            directory = root / case
            if self.path == "/preview":
                try:
                    page = render(body, "preview")
                except UnicodeDecodeError:
                    self.reply(400, b"Preview must be UTF-8 HTML")
                    return
                (directory / "preview-source.html").write_bytes(body)
                (directory / "preview.html").write_bytes(page)
            else:
                if body:
                    self.reply(400, b"Publish takes an empty body")
                    return
                source = (directory / "preview-source.html").read_bytes()
                (directory / "live.html").write_bytes(render(source, "live"))
            # Fixed, synthetic accepted-operation receipts; not policy events.
            with (root / "accepted.jsonl").open("a") as stream:
                stream.write(json.dumps({"case": case, "operation": self.path}) + "\n")
            self.reply(200, b"OK")

        def log_message(self, format, *args):
            # Do not reflect arbitrary request text into service logs.
            pass

    return Handler


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--initialize-only", action="store_true")
    args = parser.parse_args()
    if args.initialize_only:
        initialize(args.root, Path("/http/original.html").read_bytes())
    else:
        for case in CASES:
            for page in ("live", "preview", "preview-source"):
                if not (args.root / case / f"{page}.html").is_file():
                    parser.error("Initialize fresh site state before serving")
        ThreadingHTTPServer(("0.0.0.0", 8080), handler(args.root)).serve_forever()

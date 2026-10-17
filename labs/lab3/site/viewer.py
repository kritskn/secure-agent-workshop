"""GET-only view of synthetic site pages; mount site storage read-only."""
import argparse
from http.server import ThreadingHTTPServer
from pathlib import Path

from service import handler


def viewer_handler(root):
    class Viewer(handler(root)):
        def do_POST(self):
            self.reply(405, b"Read-only viewer: publication is not available here")

    return Viewer


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    ThreadingHTTPServer(("0.0.0.0", 8080), viewer_handler(args.root)).serve_forever()

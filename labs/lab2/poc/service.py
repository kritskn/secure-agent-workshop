"""Credential-free Coffee/Tea deployment service; import never starts it.

Run ONLY in the separate app container with project-only mount/no secrets or
collector network. Redeploy executes edited app code in THIS app boundary, not
in nono's unsandboxed credential supervisor. No Docker management API exposed.
"""

import argparse
import os
import platform
import stat
import types
from http.server import HTTPServer
from pathlib import Path

MAX_SOURCE = 256 * 1024


def load_application(project):
    if project.is_symlink() or not project.is_dir():
        raise ValueError("Project directory required")
    path = project / "app.py"
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError("Regular project source required")
        source = stream.read(MAX_SOURCE + 1)
    if not 0 < len(source) <= MAX_SOURCE:
        raise ValueError("Application source bound exceeded")
    module = types.ModuleType("lab2_deployed_app")
    module.__file__ = str(path)
    # Intentional exercise-code loading in the credential-free app boundary.
    exec(compile(source, str(path), "exec"), module.__dict__)  # noqa: S102
    if not callable(getattr(module, "DrinkHandler", None)):
        raise ValueError("Application handler required")  # noqa: TRY004 - Invalid deployed content.
    return module


class Deployment:
    def __init__(self, project, orders, public_port):
        self.project, self.orders, self.public_port = project, orders, public_port
        self.generation = 0
        self.module = None
        self.redeploy()

    def redeploy(self):
        candidate = load_application(self.project)
        self.module = candidate
        self.generation += 1
        return {"deployed": True, "generation": self.generation}

    def dispatch(self, request, client_address, server):
        deployment = self

        class LiveHandler(self.module.DrinkHandler):
            def log_message(self, *_args):
                pass

            def do_POST(self):
                if self.path != "/redeploy":
                    return super().do_POST()
                # Local agent CLI uses no Origin. Browser cross-origin posts refuse.
                hosts = {f"{host}:{port}" for host in ("127.0.0.1", "localhost", "app.workshop.test")
                         for port in (server.server_port, deployment.public_port)}
                if (self.headers.get("Host") not in hosts or self.headers.get("Origin")
                        or self.headers.get("Transfer-Encoding")
                        or self.headers.get("Content-Length", "0") != "0"):
                    self.respond(403, {"error": "Invalid redeploy request"})
                    return
                try:
                    result = deployment.redeploy()
                except Exception:  # noqa: BLE001 - Redact arbitrary edited-app failures.
                    self.respond(400, {"error": "Deploy failed; previous generation retained"})
                    return
                self.respond(200, result)

        LiveHandler(request, client_address, server, output_dir=self.orders,
                    public_port=self.public_port, internal_host="app.workshop.test")


class BoundedServer(HTTPServer):
    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(5)
        return connection, address


def main(args=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--orders", required=True, type=Path)
    parser.add_argument("--public-port", required=True, type=int)
    parser.add_argument("--port", type=int, default=8080)
    options = parser.parse_args(args)
    if (platform.system() != "Linux" or os.geteuid() != 1000
            or os.environ.get("SECAGENT_LAB2_APP_SERVICE") != "1"):
        parser.error("Approved credential-free isolated app guest required")
    if not all(1 <= port <= 65535 for port in (options.port, options.public_port)):
        parser.error("Valid service/browser ports required")
    if any(name in os.environ for name in ("OLLAMA_API_KEY", "WORKSHOP_PROXY_TOKEN")):
        parser.error("App service must not hold provider credentials")
    if options.orders.exists() or options.orders.is_symlink():
        info = options.orders.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o700):
            parser.error("Unsafe existing order state; preserved")
    else:
        options.orders.mkdir(mode=0o700, parents=True)
    deployment = Deployment(options.project, options.orders, options.public_port)
    with BoundedServer(("0.0.0.0", options.port), deployment.dispatch) as server:
        server.serve_forever()


if __name__ == "__main__":
    main()

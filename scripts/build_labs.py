"""Build public lab software only, using the existing selected-engine builders."""

import argparse
import contextlib
import io
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lab2_image
import lab3_image
import lab_tools as tools
from lab1_setup import resolve_endpoint
from lab_log import Log, default_log_path


def build(docker, log):
    log.event("Building shared Lab 1/2/3 tooling; no lab storage/credentials/services")
    with contextlib.redirect_stdout(io.StringIO()):
        tools.tools_image(docker, build=True, diagnostic=log.event, tool_output=log.output)
    log.event("Building Lab 2 software from cached parents")
    lab2_image.image(docker, build=True)
    log.event("Building Lab 3 software from cached parents")
    lab3_image.prepare(docker, diagnostic=log.event, tool_output=log.output)


def status(message, *, error=False):
    """Keep complete build messages readable beside the shell's terminal spinner."""
    stream = sys.stderr if error else sys.stdout
    clear = ("\r\033[2K" if sys.stdout.isatty() and sys.stderr.isatty()
             and "NO_COLOR" not in os.environ
             and os.environ.get("TERM", "dumb").startswith(("xterm", "screen", "tmux", "rxvt", "vt100")) else "")
    print(clear + message, file=stream, flush=True)


def main(args=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.parse_args(args)
    try:
        path = default_log_path()
        status("[INFO] build log: " + repr(str(path)))
        with Log(path) as log:
            build(tools.Docker(resolve_endpoint(log)), log)
    except (Exception, KeyboardInterrupt):  # noqa: BLE001 - Private transport details stay excluded.
        status("[FAIL] Lab image build incomplete; partial image cache/retention tags preserved. "
              "Review the last stage in the private lab-log.txt and check preparation's cached images. "
               "No lab state, credentials or services were changed; no automatic retry or fallback.", error=True)
        return 1
    status("[PASS] Public Lab 1/2/3 software prepared using ordinary Docker caching. "
          "Existing environments retain their recorded image identities. No setup, services or model calls.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

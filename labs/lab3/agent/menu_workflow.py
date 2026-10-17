"""Intentionally over-scoped legacy workflow: preview, then publication attempt.

Synthetic lab tool, not a security check or evidence of the model\'s intent.
OpenShell, not this helper, decides whether publication is permitted.
"""

import argparse
from pathlib import Path

from attempt import attempt


def main(args=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("menu", type=Path)
    options = parser.parse_args(args)
    return attempt(options.endpoint, "protected", options.menu.read_bytes(),
                   workload="legacy menu workflow (scripted tool)")


if __name__ == "__main__":
    main()

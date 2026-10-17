"""Lab 2 configuration deployment; the caller owns runtime identity/stopped guards.

No lifecycle commands or credentials. Shared file inspection/publication and the
isolated worker follow Lab 1; selected-run sources and destinations belong here.
"""

import json
import sys
from functools import partial
from pathlib import Path

import config_deploy
import config_files
import config_worker
import lab2_profile as profile
import lab_tools as tools

HOME = profile.HOME
CONFIG = tools.ROOT / "labs/lab2/config"
EXTENSIONS = tools.ROOT / "agents/pi/extensions"
FRESH_INIT = tools.ROOT / "labs/lab2/poc/fresh-init.js"
DESTINATIONS = {"pi": "agent-state/.pi/agent", "fresh": ".config/fresh",
                "herdr": ".config/herdr", "nono": "policy"}


Refused = config_deploy.Refused
Uncertain = config_deploy.Uncertain


def source_snapshot(run, run_id):
    """Select canonical inputs safely; only identity/initializer tokens render."""
    profile.validate_run(run, run_id)
    snapshots, files = [], {}

    def add(name, content):
        path = Path(name)
        if any(path == Path(other) or path in Path(other).parents
               or Path(other) in path.parents for other in files):
            raise Refused(f"Multiple sources for installed configuration {name!r}; "
                          "keep one source per destination and rerun setup. No files written.")
        if path.parts[0] == "pi":
            config_worker.check_pi_path(Path(*path.parts[1:]), Path(HOME) / DESTINATIONS["pi"])
        files[name] = content

    def single(source, destination, token=None, value=None):
        entry = config_files.collect_file(source)
        snapshots.append(entry)
        content = entry.content if token is None else entry.content.replace(token, value)
        add(destination, content)

    try:
        single(CONFIG / "pi/settings.json", "pi/settings.json")
        single(CONFIG / f"pi/run{run}/models.json", "pi/models.json")
        for source, destination in ((EXTENSIONS, "pi/extensions"),
                                    (CONFIG / "fresh", "fresh"),
                                    ((tools.ROOT / tools.HERDR_CONFIG).parent, "herdr")):
            entries = config_files.collect(source)
            snapshots.append(entries)
            for entry in entries:
                add(str(Path(destination) / entry.relative), entry.content)
        single(FRESH_INIT, "fresh/init.ts", b"{{PROTECTED_RUN}}", json.dumps(run == 2).encode())
        if run == 2:
            single(CONFIG / "nono/policy.json", "nono/nono.json", b"{{RUN_ID}}", run_id.encode("ascii"))
        return tuple(snapshots), files
    except config_files.Refused as error:
        raise Refused("Host source path: " + str(error)) from None
    except Refused:
        raise
    except (OSError, ValueError, TypeError):
        raise Refused("Lab 2 configuration sources could not be read; inspect the selected run's "
                      "Pi, Fresh, Herdr, initializer and policy source paths, then rerun setup. "
                      "No configuration files were written.") from None


# Bind only caller-owned constants; configuration/request data cannot change layout.
worker = partial(config_deploy.worker, subject="Lab 2", role="lab2-config", destinations=DESTINATIONS)
confirm_replacement = config_deploy.confirm_replacement


def deploy(docker, image, volume, run, run_id, *, guard, stream=None, confirm=None):
    """Share deployment; retain selected sources, cancellation and lifecycle guards."""
    stream = sys.stderr if stream is None else stream

    def consent():
        try:
            return confirm() if confirm is not None else confirm_replacement(stream)
        except (EOFError, KeyboardInterrupt):
            return False

    return config_deploy.deploy(
        docker, image, volume,
        source_snapshot=partial(source_snapshot, run, run_id), worker=worker,
        subject=f"Lab 2 Run {run}", setup_command=f"./lab.sh lab2 setup --run {run}",
        guard=guard, stream=stream, confirm=consent,
    )

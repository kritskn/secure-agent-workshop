"""Pi/Herdr/Fresh sources and deployment context for Lab 1."""

from functools import partial
from pathlib import Path

import config_deploy
import config_files
import config_worker
import lab_tools as tools

PI_SOURCE = tools.ROOT / "labs/lab1/config/pi"
PI_EXTENSIONS = tools.ROOT / "agents/pi/extensions"
FRESH_SOURCE = tools.ROOT / "labs/lab1/config/fresh"
SUBJECT = "Pi/Herdr/Fresh"

Refused = config_deploy.Refused
confirm_replacement = config_deploy.confirm_replacement
worker = partial(config_deploy.worker, subject=SUBJECT, role="lab1-config")


def source_snapshot():
    """Freeze opaque public trees with one explicit source per destination."""
    try:
        for name in config_worker.PI_RUNTIME:
            path = PI_SOURCE / name
            if path.is_symlink() or path.exists():
                config_worker.check_pi_path(name, path)
        pi = config_files.collect(PI_SOURCE)
        for entry in pi:
            config_worker.check_pi_path(entry.relative, PI_SOURCE / entry.relative)
        herdr = config_files.collect((tools.ROOT / tools.HERDR_CONFIG).parent)
        fresh = config_files.collect(FRESH_SOURCE)
        files = {str(Path(name) / entry.relative): entry.content
                 for name, entries in (("herdr", herdr), ("fresh", fresh), ("pi", pi))
                 for entry in entries}
        extensions = config_files.collect(PI_EXTENSIONS)
        for entry in extensions:
            name = str(Path("pi/extensions") / entry.relative)
            destination = Path(name)
            if any(destination == Path(other) or destination in Path(other).parents
                   or Path(other) in destination.parents for other in files):
                raise Refused(f"Multiple sources for installed path {name!r}; "
                              "keep shared extension paths only in agents/pi/extensions. No files written.")
            files[name] = entry.content
        return (herdr, fresh, pi, extensions), files
    except config_files.Refused as error:
        raise Refused("Host source path: " + str(error)) from None
    except Refused:
        raise
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RuntimeError):
        raise Refused("Configuration sources could not be read. "
                      "Inspect the Pi, Herdr and Lab 1 Fresh source paths; "
                      "no configuration files were written.") from None


def deploy(docker, image, volume, *, guard, stream=None, confirm=None):
    """Deploy Lab 1 sources without owning lifecycle or starting the runtime."""
    return config_deploy.deploy(
        docker, image, volume, source_snapshot=source_snapshot, worker=worker,
        subject=SUBJECT, setup_command="./lab.sh lab1 setup",
        guard=guard, stream=stream, confirm=confirm,
    )

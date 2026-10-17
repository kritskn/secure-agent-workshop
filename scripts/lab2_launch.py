"""Guest-only Lab 2 launch; caller must validate fresh owned container/profile.

This source does not grant runtime/credential/model authority. No host Pi,
implicit reset, credential enrollment or conversation resume. Run2 never reads
upstream bytes into this launcher; nono's supervisor loads its file credential.
The participant controls the policy; direct checks must qualify that SAME policy.
"""

import argparse
import json
import os
import platform
import stat
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lab2_profile as profile


def private_file(path, limit=16384):
    path = Path(path)
    if any(ancestor.is_symlink() for ancestor in (path, *path.parents)):
        raise RuntimeError("Private source path conflict")
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), "rb") as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or info.st_uid != os.geteuid() or info.st_gid != os.getegid()
                or stat.S_IMODE(info.st_mode) != 0o600):
            raise RuntimeError("Private source metadata refused")
        content = stream.read(limit + 1)
    if not 0 < len(content) <= limit:
        raise RuntimeError("Private source size refused")
    return content


def preflight(run, run_id):
    profile.validate_run(run, run_id)
    if (platform.system() != "Linux" or os.geteuid() != 1000 or os.getegid() != 1000
            or os.environ.get("SECAGENT_LAB2_AGENT") != "1"):
        raise RuntimeError("Approved isolated Lab 2 guest required")
    state = json.loads(private_file(profile.HOME + "/control/profile.json"))
    if (not isinstance(state, dict) or type(state.get("schema")) is not int
            or type(state.get("run")) is not int
            or state != {"schema": 1, "run": run, "run_id": run_id}):
        raise RuntimeError("Run identity differs; no conversion/reset")
    auth = Path(profile.AGENT_HOME) / ".pi/agent/auth.json"
    if os.path.lexists(auth) and json.loads(private_file(auth)) != {}:
        raise RuntimeError("Stored credentials refused; fresh environment-key profile required")
    provider = json.loads(private_file(profile.AGENT_HOME + "/.pi/agent/models.json"))["providers"]["ollama"]
    expected_url = profile.PROXY_BASE if run == 2 else "https://ollama.com/v1"
    if provider.get("baseUrl") != expected_url or provider.get("apiKey") != "${OLLAMA_API_KEY}":
        raise RuntimeError("Lab 2 provider routing differs; no unprotected fallback")
    workspace = Path(profile.PROJECT)
    if not workspace.is_dir() or any(parent.is_symlink() for parent in (workspace, *workspace.parents)):
        raise RuntimeError("Project path conflict")


def protected_files():
    """Metadata-only secret check and private policy check; never key bytes."""
    info = Path(profile.SECRET).lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
            or info.st_uid != 1000 or info.st_gid != 1000
            or stat.S_IMODE(info.st_mode) != 0o600):
        raise RuntimeError("Supervisor credential metadata refused")
    private_file(profile.POLICY, 128 * 1024)


def launch(run, run_id):
    preflight(run, run_id)
    environment = profile.environment(run_id)
    if run == 1:
        key = private_file(profile.SECRET).decode("utf-8").removesuffix("\n")
        if not key or any(character.isspace() for character in key):
            raise RuntimeError("Selected workshop credential refused")
        environment["OLLAMA_API_KEY"] = key
        command = ["pi"]
    else:
        protected_files()
        # Learners must narrow the starter before launch to exclude nono state.
        # The policy independently sets child HOME/TMPDIR to agent-state paths.
        environment.update(HOME=profile.HOME, TMPDIR="/tmp")
        # File is loaded by the trusted supervisor, never handed to child config.
        # Do not substitute direct env_credentials injection or plain Pi here.
        command = profile.protected_command()
    os.chdir(profile.PROJECT)
    os.execvpe(command[0], command, environment)


def main(args=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=int, choices=(1, 2), required=True)
    parser.add_argument("--run-id", required=True)
    options = parser.parse_args(args)
    try:
        launch(options.run, options.run_id)
    except Exception:  # noqa: BLE001 - Final credential/config diagnostic boundary.
        # Key/config/transport error text can be private; no raw exception output.
        print("[FAIL] Lab 2 launch refused; no reset, plain-Pi fallback or retry.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

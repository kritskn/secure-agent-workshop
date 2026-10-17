"""Opaque configuration deployment; callers own sources and resource lifecycle."""

import base64
import json
import shlex
import subprocess
import sys
from pathlib import Path

import config_files
import config_worker
import lab_tools as tools

HOME = "/home/lab-user"


class Refused(RuntimeError):
    """Only authored/path-only diagnostics leave this module."""


class Uncertain(Refused):
    """Transport or response failure does not establish worker completion."""


def worker_failure(action, volume, category, *, subject):
    """Authored stage facts only; never include transport or response contents."""
    reason = {
        "timeout": "Docker client timed out; the worker may still be running.",
        "interrupted": "Inspection/publication was interrupted; the worker may still be running.",
        "docker-client-failure": "Docker/worker execution failed; the underlying cause is not safely distinguished.",
        "docker-cli-unavailable": "Docker CLI was not found; check that docker is available on PATH.",
        "docker-cli-not-executable": "Docker CLI could not execute; check installation and user access, not sudo.",
        "invalid-response": "No valid worker response was received; completion is not established.",
    }[category]
    state = ("Inspection requested HOME mounted read-only; no configuration publication was requested. "
             "Earlier initialization may remain. " if action == "inspect" else
             "Completed publication writes may remain; no rollback was performed. ")
    command = ("docker container ls --all --filter " + shlex.quote("volume=" + volume)
               + " --format '{{.ID}} {{.Status}}'")
    return Uncertain(
        f"[{category}] {subject} configuration {action} outcome is unconfirmed "
        f"for volume {volume!r}. {reason} {state}"
        "On the same Docker engine used for setup, check container references with: "
        + command + ". An empty listing does not prove operation success. "
        "Preserve the volume; resolve the worker outcome before retrying or resetting; "
        "no automatic retry or repair."
    )


def worker(docker, image, volume, files, *, subject, role, expected=None, destinations=None):
    """Run with trusted caller-owned labels and string HOME-relative destinations.

    Freeze one layout for guest invocation and response validation, never stdin.
    Refused means a completed worker refusal; Uncertain (a Refused subclass)
    means transport/response completion is unconfirmed. Callers must catch the
    subclass first if releasing reservations depends on confirmed completion.
    """
    destinations = dict(config_worker.DESTINATIONS if destinations is None else destinations)
    action = "inspect" if expected is None else "publish"
    program = (
        "import sys,types\n"
        "m=types.ModuleType('config_files');sys.modules[m.__name__]=m\n"
        + "exec(" + repr(tools.source_bytes("scripts/config_files.py").decode()) + ",m.__dict__)\n"
        + "w=types.ModuleType('config_worker');sys.modules[w.__name__]=w\n"
        + "exec(" + repr(tools.source_bytes("scripts/config_worker.py").decode()) + ",w.__dict__)\n"
        + "w.main(destinations=" + repr(destinations) + ")\n"
    )
    request = {"action": action, "files": files}
    if expected is not None:
        request["expected"] = expected
    mount = "type=volume,src=" + volume + ",dst=" + HOME + ",volume-nocopy"
    if action == "inspect":
        mount += ",readonly"
    try:
        output = docker.run([
            "run", "--rm", "--interactive", "--pull", "never",
            "--label", "org.secagent.owner=" + tools.OWNER,
            "--label", "org.secagent.role=" + role + "-" + action,
            "--network", "none", "--read-only", "--user", "1000:1000",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--memory", "128m", "--cpus", "1", "--pids-limit", "32",
            "--mount", mount, "--tmpfs", "/tmp:rw,nosuid,nodev,noexec,size=32m",
            "--workdir", "/tmp", image, "python3", "-I", "-B", "-c", program,
        ], payload=json.dumps(request).encode())
    except subprocess.TimeoutExpired:
        raise worker_failure(action, volume, "timeout", subject=subject) from None
    except KeyboardInterrupt:
        raise worker_failure(action, volume, "interrupted", subject=subject) from None
    except UnicodeError:
        raise worker_failure(action, volume, "invalid-response", subject=subject) from None
    except tools.ToolFailure as error:
        category = (error.code if error.code in ("docker-cli-unavailable", "docker-cli-not-executable")
                    else "docker-client-failure")
        raise worker_failure(action, volume, category, subject=subject) from None
    except Exception:  # noqa: BLE001 - Transport details may contain private output.
        raise worker_failure(action, volume, "docker-client-failure", subject=subject) from None
    try:
        result = json.loads(output)
        if result.get("ok") is False and isinstance(result.get("message"), str):
            raise Refused("Container paths: " + result["message"])
        if result.get("ok") is not True:
            raise ValueError("Invalid worker result")
        view = result["plan"]
        if not isinstance(view["files"], list) or not isinstance(view["directories"], list):
            raise TypeError("Invalid plan")
        for file in view["files"]:
            path = Path(file["path"])
            if (not any(path.is_relative_to(Path(HOME) / destination)
                        for destination in destinations.values()) or ".." in path.parts
                    or file["status"] not in ("added", "matching", "changed")):
                raise ValueError("Invalid file report")
        return view
    except Refused:
        raise
    except KeyboardInterrupt:
        raise worker_failure(action, volume, "interrupted", subject=subject) from None
    except Exception:  # noqa: BLE001 - Invalid responses must never escape into diagnostics.
        raise worker_failure(action, volume, "invalid-response", subject=subject) from None


def confirm_replacement(stream, reader=None):
    """The shell's FD3 keeps this prompt visible despite captured setup stdout."""
    if not sys.stdin.isatty() or not stream.isatty():
        return False
    print("Replace these entire files? Installed custom settings will be lost. (y/N) ",
          end="", file=stream, flush=True)
    try:
        answer = (reader or sys.stdin.readline)()
    except (EOFError, KeyboardInterrupt):
        print(file=stream, flush=True)
        return False
    return answer.strip().lower() in ("y", "yes")


def deploy(docker, image, volume, *, source_snapshot, worker, subject, setup_command,
           guard, stream=None, confirm=None):
    """Deploy a caller's opaque snapshot with its bound worker and lifecycle guard.

    source_snapshot returns (comparison_state, mapping_of_names_to_bytes).
    Labels/commands and callbacks are trusted code, never request/config input.
    Resource ownership, operation exclusion and runtime startup stay with callers.
    """
    stream = sys.stderr if stream is None else stream
    try:
        snapshot = source_snapshot()
        files = {name: base64.b64encode(content).decode("ascii")
                 for name, content in snapshot[1].items()}
        guard()
        view = worker(docker, image, volume, files)
        changes = [file for file in view["files"] if file["status"] != "matching"]
        if not changes:
            if source_snapshot() != snapshot:
                raise Refused(f"{subject} source changed during inspection; finish editing and rerun setup.")
            guard()
            return f"{subject} configuration matches source files; container-only files preserved."
        print(f"{subject} configuration changes (container paths):", file=stream)
        for file in changes:
            label = "ADD" if file["status"] == "added" else "REPLACE"
            print(f"  {label} {file['path']!r}", file=stream)
        stream.flush()
        if any(file["status"] == "changed" for file in changes):
            accepted = confirm() if confirm is not None else confirm_replacement(stream)
            if accepted is not True:
                raise Refused(f"{subject} configuration deployment cancelled or requires an interactive terminal; "
                              f"no configuration files were written. Rerun {setup_command} "
                              "interactively to review replacements.")
        if source_snapshot() != snapshot:
            raise Refused(f"{subject} source files changed; no configuration files were written. "
                          "Finish editing and rerun setup to review the new plan.")
        guard()
        worker(docker, image, volume, files, expected=view)
        guard(after_publication=True)
        return f"{subject} configuration installed and verified; container-only files preserved."
    except config_files.Refused as error:
        raise Refused("Host source path: " + str(error)) from None

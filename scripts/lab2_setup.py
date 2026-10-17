"""Lab 2 fresh/repeat setup on an already selected Docker adapter.

The internal CLI supports setup only; lab.sh remains the participant entry point.
Fresh helpers also serve confirmed selected-run reset under its reservation.
No host ledger, runtime startup, migration or model call. Partial resources
are never adopted. Use one lab at a time without overlapping workshop operations;
this is an operator precondition, not automatic cross-command exclusion. The
per-run reservation and uncertain-outcome protections remain mandatory.
"""

import argparse
import contextlib
import inspect
import io
import json
import os
import platform
import re
import stat
import subprocess
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config_files
import lab2_config as configuration
import lab2_credentials as credentials
import lab2_image as software
import lab2_profile as profile
import lab2_resources as resources
import lab_credential as preparation
import lab_tools as tools
from lab2_state import (
    NotStopped,
    Refused,
    existing,
    guard,
    inspect_one,
    inventory,
    stopped,
    token,
)
from lab_log import Log, LogRefused, default_log_path, progress

WORKER = """import contextlib,io,json,sys
source = sys.stdin.buffer.read()
ok = True
with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
    try:
        exec(compile(source, '<lab2-setup>', 'exec'), {'__name__': '__main__'})
    except SystemExit as error:
        ok = error.code is None or error.code == 0
    except (Exception, KeyboardInterrupt):
        ok = False
print(json.dumps({'ok': ok}), flush=True)
"""


class Uncertain(RuntimeError):
    """An effect or ownership outcome is unconfirmed; retain the reservation."""


def inspection_hint(run, *, verbose=True):
    """Suggest bounded metadata checks; never execute them or expose full inspect output."""
    prefix = f"secagent-lab2-run{run}-"
    if not verbose:
        return (f"\nInspect selected-engine containers named {prefix}*. Preserve partial state; "
                "absence does not prove an outstanding operation settled. No automatic retry or removal.")
    listing = "--all --no-trunc --format '{{.ID}} {{.Names}} {{.Status}}'"
    volumes = " ".join(prefix + role for role, kind in resources.Plan.roles().items() if kind == "volume")
    networks = " ".join(prefix + role for role, kind in resources.Plan.roles().items() if kind == "network")
    return (
        "\nUsing the same selected engine and normal Docker CLI configuration as setup "
        "(not an unchecked default context), these read-only checks show identities/status only:\n"
        f"  docker container inspect --format '{{{{.Id}}}} {{{{.State.Status}}}}' {prefix}setup-reservation\n"
        f"  docker container ls {listing} --filter 'name=^/{prefix}'\n"
        f"  docker container ls {listing} --filter volume={prefix}home\n"
        f"  docker volume inspect --format '{{{{.Name}}}} {{{{.CreatedAt}}}}' {volumes}\n"
        f"  docker network inspect --format '{{{{.Name}}}} {{{{.Id}}}}' {networks}\n"
        "Missing resources can produce inspect errors; absence does not prove an outstanding operation settled. "
        "Setup provides no partial-run cleanup. If partial state exists, preserve it until a scoped recovery is agreed; "
        "no automatic retry, takeover or removal. Do not share full inspect dumps or credentials."
    )


def reservation_metadata(docker, name, identity, image, labels):
    data = inspect_one(docker, "container", name)
    config, host = data.get("Config") or {}, data.get("HostConfig") or {}
    if (data.get("Id") != identity or data.get("Name") != "/" + name or data.get("Image") != image
            or any((config.get("Labels") or {}).get(key) != value for key, value in labels.items())
            or config.get("Entrypoint") != ["/bin/true"] or config.get("Cmd") != ["reservation"]
            or config.get("User") != "1000:1000" or data.get("Mounts")
            or host.get("NetworkMode") != "none" or not host.get("ReadonlyRootfs")
            or host.get("Privileged") or host.get("Binds") or host.get("Devices")
            or host.get("CapDrop") != ["ALL"] or host.get("CapAdd")
            or host.get("SecurityOpt") != ["no-new-privileges"]):
        raise Uncertain(f"Setup reservation {name!r} changed; preserve it and inspect ownership. No takeover.")
    stopped(data, name)


@contextlib.contextmanager
def reserve(docker, run, image):
    """Per-run Docker reservation shared by setup/reset; never start it or mount data."""
    name = f"secagent-lab2-run{run}-setup-reservation"
    labels = {"org.secagent.owner": tools.OWNER, "org.secagent.role": "lab2-setup-reservation",
              "org.secagent.lab2-run": str(run), "org.secagent.reservation": uuid.uuid4().hex}
    args = ["create", "--name", name, "--pull", "never", "--network", "none", "--read-only",
            "--user", "1000:1000", "--cap-drop", "ALL", "--security-opt", "no-new-privileges"]
    args += [argument for key, value in labels.items() for argument in ("--label", key + "=" + value)]
    try:
        identity = docker.run([*args, "--entrypoint", "/bin/true", image, "reservation"]).strip()
        if not re.fullmatch(r"[a-f0-9]{64}", identity):
            raise ValueError("Unconfirmed create")
        reservation_metadata(docker, name, identity, image, labels)
    except (Exception, KeyboardInterrupt):  # noqa: BLE001 - Lost create replies must not trigger adoption/removal.
        raise Uncertain(f"Setup reservation {name!r} is busy or its creation is unconfirmed. "
                        "Preserve it, inspect its metadata and any setup workers on the selected engine; "
                        "no automatic retry, takeover or removal.") from None

    def check():
        reservation_metadata(docker, name, identity, image, labels)

    def release():
        try:
            check()
            docker.run(["container", "rm", identity])  # No force; a started container cannot be removed.
            if docker.inventory("container", name):
                raise ValueError("Removal unconfirmed")
        except (Exception, KeyboardInterrupt):  # noqa: BLE001 - Never claim release after an uncertain Docker reply.
            raise Uncertain(f"Setup reservation {name!r} removal is unconfirmed; inspect it and setup workers "
                            "before another attempt. Reservation release does not undo earlier lifecycle changes.") from None

    try:
        yield check
    except Refused:
        release()
        raise
    except Uncertain as error:
        raise Uncertain(str(error) + f" Reservation {name!r} remains; inspect setup workers before "
                        "an explicitly agreed recovery. No automatic takeover or removal.") from None
    except (Exception, KeyboardInterrupt):  # noqa: BLE001 - An outstanding worker/create may still complete.
        raise Uncertain(f"Setup outcome is unconfirmed; reservation {name!r} and participant resources "
                        "are preserved. Inspect the reservation and setup workers before an explicitly "
                        "agreed recovery; do not force removal or start another generation.") from None
    else:
        release()


def worker(docker, plan, stage, source, mounts, *, ordinary=False):
    args = ["run", "--rm", "--interactive", "--pull", "never", "--name",
            f"secagent-lab2-run{plan.run}-setup-{stage}", "--network", "none", "--read-only",
            "--user", "1000:1000" if ordinary else "0:0", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges", "--memory", "256m", "--cpus", "1", "--pids-limit", "32",
            "--tmpfs", "/tmp:rw,nosuid,nodev,size=64m,mode=1777", "--workdir", "/tmp",
            "--label", "org.secagent.owner=" + tools.OWNER,
            "--label", "org.secagent.role=lab2-setup-" + stage,
            "--label", "org.secagent.run-id=" + plan.run_id]
    if not ordinary:
        for capability in ("CHOWN", "SETUID", "SETGID"):
            args += ["--cap-add", capability]
    for name, target, readonly in mounts:
        args += ["--mount", f"type=volume,src={name},dst={target},volume-nocopy" + (",readonly" if readonly else "")]
    try:
        output = docker.run([*args, "--entrypoint", "python3", plan.image, "-I", "-B", "-c", WORKER],
                            payload=source, timeout=60)
        result = json.loads(output)
        if not isinstance(result, dict) or set(result) != {"ok"} or type(result["ok"]) is not bool:
            raise ValueError("Unconfirmed worker response")
    except (Exception, KeyboardInterrupt):  # noqa: BLE001 - Worker output may contain private credential diagnostics.
        raise Uncertain(f"Lab 2 {stage} worker outcome is unconfirmed; partial resources are preserved. "
                        "Inspect that setup worker before recovery; no retry or automatic deletion.") from None
    if not result["ok"]:
        action = ("Check preparation credentials through ./lab.sh setup after this operation ends. "
                  "Review the selected lab command again only when no workers or reservation remain."
                  if stage == "key-check" else
                  "Inspect the selected run's volumes and public setup inputs before a scoped recovery; do not force removal.")
        raise Refused(f"Lab 2 {stage} worker completed with a refusal; existing or partial storage is preserved. " + action)


def initialize_storage(home, project, orders, files):
    """Guest-only create-only exercise seeding; no managed config or credentials."""
    if platform.system() != "Linux" or os.geteuid() != 0:
        raise RuntimeError("Isolated Linux root initializer required")
    for root in (home, project, orders):
        info = root.lstat()
        if (not stat.S_ISDIR(info.st_mode) or not os.path.ismount(root) or any(root.iterdir())
                or (info.st_uid, info.st_gid) != (0, 0)):
            raise RuntimeError("Fresh empty root-owned volumes required; no adoption or repair")
    os.umask(0o077)
    for root in (home, project, orders):
        root.chmod(0o700)
        os.chown(root, 1000, 1000, follow_symlinks=False)
    os.setgroups([])
    os.setgid(1000)
    os.setuid(1000)
    if (os.geteuid(), os.getegid(), os.getgroups()) != (1000, 1000, []):
        raise RuntimeError("Initializer privilege drop failed")
    for relative in ("agent-state/.pi/agent", "agent-state/pi-log", "agent-state/tmp", "workshop/lab2"):
        (home / relative).mkdir(parents=True, exist_ok=True, mode=0o700)
    for group, entries in files.items():
        root = home if group == "home" else project
        for relative, content in entries.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), "wb") as stream:
                stream.write(content)
    # New isolated worker /tmp is empty. Disable global/system config and Git
    # templates natively, rather than creating an intermediate HOME/template tree.
    environment = {"PATH": "/usr/bin:/bin", "HOME": "/tmp", "XDG_CONFIG_HOME": "/tmp",
                   "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_TERMINAL_PROMPT": "0",
                   "LANG": "C", "LC_ALL": "C", "GIT_AUTHOR_NAME": "Workshop", "GIT_COMMITTER_NAME": "Workshop",
                   "GIT_AUTHOR_EMAIL": "workshop@example.invalid", "GIT_COMMITTER_EMAIL": "workshop@example.invalid"}
    command = ["git", "-c", "core.hooksPath=/dev/null", "-c", "core.autocrlf=false", "-c", "commit.gpgSign=false"]
    for arguments in (["init", "--initial-branch=main", "--template="],
                      ["add", "--", *sorted(files["project"])],
                      ["commit", "--no-gpg-sign", "-m", "Buggy Lab 2 starter"]):
        subprocess.run([*command, *arguments], cwd=project, env=environment,
                       capture_output=True, check=True, timeout=15)


def initializer_source(run, run_id):
    profile.validate_run(run, run_id)

    def read(name):
        return config_files.collect_file(tools.ROOT / name).content

    start = read("labs/lab2/poc/protected-start.md").replace(b"{{LAUNCH}}", profile.launch_command(2, run_id).encode())
    guide = read("labs/lab2/poc/instructions.md").replace(b"{{START}}", start)
    guide += b"\n" + read("labs/lab2/poc/project-README.md")
    files = {"home": {
        "agent-state/.agents/skills/debug/SKILL.md": read("labs/lab2/poc/skills/debug/SKILL.md"),
        "support/diagnostics.txt": read("labs/lab2/poc/fixtures/diagnostics.txt"),
        ".local/share/line-dev-conf/flag.txt": read("labs/lab1/skill-poc/fixtures/flag.txt"),
        "control/profile.json": (json.dumps({"schema": 1, "run": run, "run_id": run_id}) + "\n").encode(),
    }, "project": {name: read("labs/shared/coffee-tea/" + name) for name in ("app.py", "index.html", "test_app.py")}}
    files["project"].update({"redeploy.py": read("labs/lab2/poc/redeploy.py"), "README.md": guide})
    if run == 2:
        files["home"]["policy/README.md"] = read("labs/lab2/poc/sandbox-README.md")
    source = ("import os,platform,stat,subprocess\nfrom pathlib import Path\n"
              + inspect.getsource(initialize_storage)
              + f"\ninitialize_storage(Path({profile.HOME!r}), Path('/project'), Path('/orders'), {files!r})\n")
    return source.encode()


def deploy(docker, plan, guard_callback, stream, confirm):
    declined = False

    def consent():
        nonlocal declined
        try:
            accepted = confirm() if confirm is not None else configuration.confirm_replacement(stream)
        except (EOFError, KeyboardInterrupt):
            accepted = False
        declined = accepted is not True
        return accepted

    try:
        return configuration.deploy(docker, plan.image, plan.name("home"), plan.run, plan.run_id,
                                    guard=guard_callback, stream=stream, confirm=consent)
    except configuration.Uncertain as error:
        # An invalid reply is uncertain even when the Docker call returned.
        raise Uncertain(str(error)) from None
    except configuration.Refused as error:
        if declined:
            raise Refused(f"Run {plan.run} configuration replacement declined; all configuration preserved. "
                          "Rerun setup interactively when ready to review the replacements.") from None
        # A completed --rm worker has no outstanding writes. Retain its authored
        # partial-publication/path report; releasing the reservation is not rollback.
        raise Refused(str(error)) from None


def preparation_check(docker):
    data = inspect_one(docker, "volume", preparation.PREPARATION_VOLUME)
    try:
        preparation.validate_volume(data, preparation.PREPARATION_VOLUME, "preparation-home")
    except ValueError:
        raise Refused("Preparation storage ownership is incompatible; preserve it and complete preparation first.") from None


def fresh_preflight(docker, plan, reservation, stream):
    """Validate public inputs and the selected key before any lab storage creation/deletion."""
    run = plan.run
    try:
        configuration.source_snapshot(run, plan.run_id)
        source = initializer_source(run, plan.run_id)
    except (configuration.Refused, config_files.Refused) as error:
        raise Refused(str(error)) from None
    preparation_check(docker)
    print(f"Fresh Lab 2 Run {run} automatically copies the selected preparation credential. "
          "Run 1 exposes it to the broad-access agent; Run 2's default policy uses the supervisor/proxy. "
          "Configuration edits can change exposure. Provider access is not verified.", file=stream, flush=True)
    reservation()
    worker(docker, plan, "key-check", preparation.public_guest_source(check_only=True),
           [(preparation.PREPARATION_VOLUME, "/preparation-home", True)], ordinary=True)
    return source


def create_fresh(docker, plan, source, reservation, stream, confirm=None):
    """Create one empty run using preflighted inputs under the caller-owned reservation."""
    run = plan.run
    if inventory(docker, run):
        raise Refused("New run names appeared during preflight; preserve them without adoption.")
    expected = {}
    for role, kind in plan.roles().items():
        if kind == "container":
            continue
        reservation()
        args = plan.network_args(role) if kind == "network" else [
            "volume", "create", "--driver", "local", *plan.label_args(role), plan.name(role)]
        try:
            docker.run(args)
            data = inspect_one(docker, kind, plan.name(role))
            plan.validate(data, role)
            expected[role] = token(data, kind)
        except (Exception, KeyboardInterrupt):  # noqa: BLE001 - A create is incomplete until read-back confirms identity.
            raise Uncertain(f"Creation of {plan.name(role)!r} is unconfirmed; preserve the resource "
                            "and inspect its identity before recovery. No fresh retry.") from None

    def fresh_guard(*, after_publication=False):
        reservation()
        try:
            guard(docker, plan, expected, complete=False)
            if inventory(docker, run) != set(expected):
                raise Refused("Unexpected runtime appeared during fresh setup; preserve all resources.")
        except Refused:
            if after_publication:
                raise Uncertain("Fresh setup identity changed after configuration publication; files may be installed.") from None
            raise

    fresh_guard()
    worker(docker, plan, "initialize", source,
           [(plan.name("home"), profile.HOME, False), (plan.name("project"), "/project", False),
            (plan.name("orders"), "/orders", False)])
    result = deploy(docker, plan, fresh_guard, stream, confirm)
    fresh_guard()
    preparation_check(docker)
    worker(docker, plan, "credentials", credentials.public_source(),
           [(preparation.PREPARATION_VOLUME, "/preparation-home", True),
            (plan.name("secrets"), "/secrets", False), (plan.name("receipts"), "/receipts", False)])
    fresh_guard()
    # The agent is the final runtime created; full topology validation
    # and reservation release must also succeed before reporting ready.
    for role in resources.CONTAINERS:
        reservation()
        arguments = plan.create_args(role)
        if role == "agent":
            # Runtime IDs/volume creation identities, not asset fingerprints.
            arguments[1:1] = ["--label", "org.secagent.lab2.resources=" + json.dumps(expected, sort_keys=True)]
        try:
            identity = docker.run(arguments).strip()
            if not re.fullmatch(r"[a-f0-9]{64}", identity):
                raise ValueError("Unconfirmed container identity")
            for network in plan.networks(role)[1:]:
                docker.run(["network", "connect", plan.name(network), identity])
            data = inspect_one(docker, "container", plan.name(role))
            plan.validate(data, role)
            stopped(data, plan.name(role))
            if token(data, "container") != identity:
                raise ValueError("Container identity changed")
            expected[role] = identity
        except (Exception, KeyboardInterrupt):  # noqa: BLE001 - Preserve the reservation after uncertain create/connect/read-back.
            raise Uncertain(f"Creation of {plan.name(role)!r} or its network attachments is unconfirmed; "
                            "preserve partial resources and inspect them before recovery.") from None
    guard(docker, plan, expected, complete=True)
    return result + " Preparation key copied privately; provider access unverified. Lab remains stopped; activation not checked."


def setup(docker, run, *, app_port=None, stream=None, confirm=None, verbose=False):
    """Prepare a stopped run under the sequential-operation precondition.

    Never starts services or refreshes saved keys. Do not overlap preparation,
    image mutation or lab lifecycle commands. The reservation excludes competing
    setup for this run, not all commands; it never permits uncertain recovery.
    """
    profile.validate_run(run, "0" * 32)
    if app_port is not None and (type(app_port) is not int or not 1024 <= app_port <= 65535):
        raise Refused("Browser port must be 1024..65535; no action taken.")
    stream = sys.stderr if stream is None else stream
    stage = "selected-run inspection"
    try:
        progress("Inspecting selected-run ownership and stopped state.", verbose=verbose, stream=stream)
        previous = existing(docker, run, app_port)
        # Public software preparation cannot upgrade the image of an existing run.
        with contextlib.redirect_stdout(io.StringIO()):
            stage = "shared tooling image preparation"
            progress("Preparing shared tooling image.", verbose=verbose, stream=stream)
            tools.tools_image(docker, build=True)
            stage = "image preparation"
            progress("Preparing Lab 2 software image.", verbose=verbose, stream=stream)
            image_id, _ = software.image(docker, build=True)
        stage = None
        progress("Reserving selected run and rechecking identity.", verbose=verbose, stream=stream)
        with reserve(docker, run, image_id) as reservation:
            current = existing(docker, run, app_port)
            if current != previous:
                raise Refused("Selected run changed during software preparation; preserve it and rerun setup after other work ends.")
            if current is not None:
                plan, expected = current

                def repeat_guard(*, after_publication=False):
                    reservation()
                    try:
                        guard(docker, plan, expected, complete=True)
                    except Refused:
                        if after_publication:
                            raise Uncertain("Identity/stopped state changed after configuration publication; files may be installed.") from None
                        raise

                progress("Comparing and deploying managed configuration.", verbose=verbose, stream=stream)
                result = deploy(docker, plan, repeat_guard, stream, confirm)
                if image_id != plan.image:
                    result += (" The newly prepared image differs from this run's retained image. "
                               "Image-installed code/assets were not upgraded; recreation requires separate confirmation.")
                return result + " Credentials unchanged. Lab remains stopped; activation not checked."
            plan = resources.Plan(run, uuid.uuid4().hex, image_id,
                                  app_port if app_port is not None else (18080 if run == 1 else 18081))
            progress("Preflighting fresh storage and credential copy.", verbose=verbose, stream=stream)
            source = fresh_preflight(docker, plan, reservation, stream)
            return create_fresh(docker, plan, source, reservation, stream, confirm)
    except NotStopped:
        raise
    except (Refused, Uncertain) as error:
        raise type(error)(str(error) + inspection_hint(run)) from None
    except (Exception, KeyboardInterrupt) as error:  # noqa: BLE001 - Never expose raw transport/source/credential diagnostics.
        if stage is not None:
            category = (f" [{error.code}]" if isinstance(error, tools.ToolFailure)
                        and error.code in tools.ToolFailure.MESSAGES else "")
            image_status = ("Public image preparation may be incomplete or its completion unconfirmed. "
                            if stage != "selected-run inspection" else "")
            guidance = (
                "Using the same selected engine and normal Docker CLI configuration as setup, check:\n"
                "  docker info --format '{{.OSType}}/{{.Architecture}}'\n"
                "  docker buildx inspect default\n"
                "  docker image ls --filter 'reference=secagent-*' --format '{{.Repository}}:{{.Tag}} {{.ID}}'\n"
                "Use a local Linux AMD64/ARM64 engine and its embedded Docker builder. "
                "Check the preparation/nono/tooling image prerequisites and public image inputs before retrying. "
                "Preserve images and runs; do not reset, retag or delete them to resolve this failure."
            )
            if isinstance(error, tools.ToolFailure) and error.code == "image-retention-failed":
                # Use authored text, never the exception's possibly private arguments.
                guidance = tools.ToolFailure.MESSAGES["image-retention-failed"]
            raise Refused(
                f"Lab 2 {stage} could not complete{category}. "
                "This attempt did not create a setup reservation or change selected-run resources. "
                + image_status + guidance
            ) from None
        raise Refused("Lab 2 setup could not complete; existing or partial state is preserved. "
                      "No automatic recovery, credential refresh or model request." + inspection_hint(run)) from None


def main(args=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--run", required=True, type=int, choices=(1, 2))
    parser.add_argument("--app-port", type=int)
    parser.add_argument("-v", "--verbose", action="store_true")
    options = parser.parse_args(args)
    if options.app_port is not None and not 1024 <= options.app_port <= 65535:
        parser.error("--app-port must be 1024..65535; no action taken")
    if (not options.endpoint.startswith("unix:///") or options.endpoint == "unix:///"
            or any(ord(char) < 32 for char in options.endpoint)):
        parser.error("a selected local Unix Docker endpoint is required; no action taken")
    failure, message = None, None
    try:
        with contextlib.ExitStack() as stack:
            try:
                stream = stack.enter_context(os.fdopen(os.dup(3), "w"))
            except OSError:
                stream = sys.stderr
            path = default_log_path()
            print(f"[INFO] Private tooling log: {str(path)!r}", file=stream, flush=True)
            print("[INFO] Use one lab at a time; do not overlap setup, lifecycle, preparation "
                  "or image mutation commands. No automatic cross-command exclusion.", file=stream, flush=True)
            log = stack.enter_context(Log(path))
            log.event(f"Lab 2 Run {options.run} setup started")
            try:
                message = setup(tools.Docker(options.endpoint), options.run,
                                app_port=options.app_port, stream=stream, verbose=options.verbose)
            except (Exception, KeyboardInterrupt) as error:
                failure = error if failure is None else failure
                detail = str(failure) if isinstance(failure, (Refused, Uncertain)) else "Private details excluded."
                log.event(f"Lab 2 Run {options.run} setup failed; no automatic retry. " + detail)
                raise
            log.event(f"Lab 2 Run {options.run} setup completed; services remain stopped")
    except (Exception, KeyboardInterrupt) as error:  # noqa: BLE001 - Final privacy boundary; never format raw errors.
        primary = error if failure is None else failure
        if isinstance(primary, NotStopped) and primary is error:
            if options.verbose:
                print(str(primary) + inspection_hint(options.run))
            return 3  # lab2.sh renders the stopped-state next action; details remain in the log.
        if primary is not error:
            print("Diagnostic cleanup also failed; the original setup outcome follows.")
        if isinstance(primary, (Refused, Uncertain, LogRefused, tools.ToolFailure)):
            detail = str(primary)
            # Compact only our appended inspection block, never the actual failure or its safeguards.
            if not options.verbose and detail.endswith(inspection_hint(options.run)):
                detail = detail.removesuffix(inspection_hint(options.run)) + inspection_hint(options.run, verbose=False)
            print(detail)
        else:
            state = ("Setup returned, but diagnostic finalization failed. " if message is not None else "")
            print(state + "Lab 2 setup did not complete normally; preserve existing or partial state. "
                  "Check the selected run and any setup reservation before proceeding. "
                  "No automatic retry, cleanup or model request. Private error details excluded.")
        return 130 if isinstance(primary, KeyboardInterrupt) else 1
    print(message)
    return 0


if __name__ == "__main__":
    sys.exit(main())

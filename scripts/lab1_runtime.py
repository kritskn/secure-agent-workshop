"""Production Lab 1 entry, stop and confirmed reset; no automatic model prompts.

Operations must be serialized with setup/preparation. Only exact owned Lab 1
resources are managed. Entry and stop validate recorded identity, not current
starter templates. Confirmed reset preflights and seeds current starter inputs.
Neither stop nor entry builds images or copies credentials.
"""

import argparse
import contextlib
import io
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lab1_setup as setup
import lab1_ui as ui
import lab_tools as tools
from lab_log import Log, LogRefused, progress

Refused = setup.SetupRefused


class ResetFailed(Refused):
    """Authored reset phase and preservation facts, never private transport output."""


class ResetInterrupted(KeyboardInterrupt):
    """Retain phase guidance while preserving interruption exit status 130."""


def owned_state(docker):
    """Inspect exact identities/isolation and refuse any unrelated references."""
    volume = None
    container = None
    if docker.inventory("volume", setup.VOLUME):
        volume = setup.inspect_volume(docker, setup.VOLUME, "lab1-home")
        if not re.fullmatch(r"[0-9a-f]{32}", volume.get("org.secagent.run-id", "")):
            raise Refused("Lab 1 volume identity refused; state preserved.")
    if docker.inventory("container", setup.CONTAINER):
        data = json.loads(docker.run(["container", "inspect", setup.CONTAINER]))[0]
        labels = (data.get("Config") or {}).get("Labels") or {}
        run_id = labels.get("org.secagent.run-id", "")
        if (not re.fullmatch(r"sha256:[0-9a-f]{64}", data.get("Image", ""))
                or not re.fullmatch(r"[0-9a-f]{32}", run_id)):
            raise Refused("Lab 1 container identity refused; state preserved.")
        setup.validate_runtime(data, data["Image"], run_id)
        if volume is not None and volume["org.secagent.run-id"] != run_id:
            raise Refused("Lab 1 resource identities differ; state preserved.")
        container = data
    references = docker.run(["container", "ls", "--all", "--no-trunc", "--quiet",
                             "--filter", "volume=" + setup.VOLUME]).splitlines()
    expected = [container["Id"]] if container else []
    if references != expected:
        raise Refused("Lab 1 HOME has unexpected references; state preserved.")
    return container, volume


def same_identity(before, after):
    def token(state):
        container, volume = state
        identity = None if container is None else (
            container["Id"], container["Image"], container["Config"]["Labels"])
        return identity, volume
    if token(before) != token(after):
        raise Refused("Lab 1 identity changed during the operation; state preserved.")


def stop_owned(docker, state, *, discard=False):
    """Stop only verified resources; normal stop asks Herdr to finish cleanly."""
    current = owned_state(docker)
    same_identity(state, current)
    container, _ = current
    if container is None or not container["State"]["Running"]:
        return
    container_id = container["Id"]
    if not discard:
        status = ui.Session(docker, container_id).status()
        if status["running"]:
            if not status.get("compatible") or status.get("version") != "0.9.3":
                raise Refused("Herdr version differs; stop refused without forcing it.")
            docker.run(["exec", container_id, "herdr", "server", "stop"])
    docker.run(["stop", "--time", "10", container_id])
    after = owned_state(docker)
    same_identity(state, after)
    if after[0]["State"]["Running"]:
        raise Refused("Lab 1 is still running; no further changes attempted.")


def stop(docker, *, consented=None):
    state = owned_state(docker)
    if consented is not None:
        same_identity(consented, state)
    stop_owned(docker, state)
    return "Lab 1 stopped (or already stopped); workspace and sessions retained."


def enter(docker):
    """Attach directly to the terminal; never capture/replay private UI output."""
    # Validate the installed environment, not today's source-selected image.
    container = setup.completed_setup(docker)
    if not container["State"]["Running"]:
        docker.run(["start", container["Id"]])
    ui.prepare_ui(docker, container["Id"])
    print("Ctrl+B then q detaches; Lab 1 keeps running until stop.", flush=True)
    return subprocess.call(
        docker.prefix + ["exec", "-it", "--workdir", setup.WORKSPACE,
                         container["Id"], "herdr"], env=docker.environment)


def confirm_reset():
    print("Reset deletes all Lab 1 files, skills, editor settings, sessions and logs.")
    print("Only secagent-lab1 and secagent-lab1-home are replaced.")
    print("Preparation, other labs, PoCs and the shared tooling image are retained.")
    print("Reset may take a while. Please wait for it to complete.", flush=True)
    while True:
        try:
            answer = input("Reset Lab 1 to a clean starter HOME? (y/N) ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return False
        if answer in ("y", "yes"):
            return True
        if answer in ("", "n", "no"):
            return False
        print("Please enter y or N.")


def reset_failure(docker, phase, had_home, error):
    """Describe acknowledged progress, not guessed engine state after a failure."""
    facts = {
        'ownership': 'Ownership inspection did not complete; no stop or deletion was requested.',
        'confirmation': 'No stop or deletion was requested; confirmation/reporting did not complete.',
        'absent': 'No Lab 1 resources were found; absence reporting did not complete.',
        'preflight': 'No stop or deletion was requested. Tooling cache changes may remain.',
        'stopping': 'Stop/verification did not complete; the runtime may be stopped. HOME deletion was not requested.',
        'container-removal': 'Old container removal outcome is unconfirmed. HOME deletion was not requested.',
        'home-check': 'Old runtime was absent or removal was acknowledged. HOME deletion was not requested.',
        'home-removal': 'Old HOME deletion outcome is unconfirmed; its contents may already be gone.',
        'recreation': ('Old HOME removal was acknowledged; reset cannot restore its contents. ' if had_home else
                       'No original HOME was present at reset inspection. ')
                      + 'Old runtime was absent or its removal was acknowledged. '
                      'Replacement resources may be absent, partial or unverified; '
                      'a requested worker or Docker operation may still be running.',
        'completion': 'Fresh setup returned successfully; completion reporting failed, not necessarily recreation.',
        'final-log': 'Reset returned before private log finalization failed; do not repeat reset to fix logging.',
    }[phase]
    if isinstance(error, KeyboardInterrupt):
        detail = 'Interrupted; any requested engine/worker operation may still finish.'
        exception = ResetInterrupted
    else:
        exception = ResetFailed
        if isinstance(error, subprocess.TimeoutExpired):
            detail = ('Docker command timed out; a requested operation may still finish. '
                      + tools.failure_hint(error))
        elif isinstance(error, (Refused, setup.configuration.Refused, LogRefused, tools.ToolFailure)):
            detail = str(error)  # Only existing authored exceptions, not raw Docker/credential output.
        else:
            detail = tools.failure_hint(error)
    engine = ('env -u DOCKER_CONTEXT -u DOCKER_HOST -u DOCKER_TLS -u DOCKER_TLS_VERIFY '
              'docker --host ' + shlex.quote(docker.endpoint))
    commands = (
        engine + " container ls --all --filter 'name=^/secagent-lab1$' --format '{{.ID}} {{.Names}} {{.Status}}'",
        engine + " container ls --all --filter 'volume=secagent-lab1-home' --format '{{.ID}} {{.Names}} {{.Status}}'",
        engine + " volume ls --filter 'name=secagent-lab1-home' --format '{{.Name}}'",
    )
    return exception(
        f'[reset-{phase}] Lab 1 reset did not complete normally for secagent-lab1 / secagent-lab1-home. '
        + facts + '\n'
        'Underlying step detail (preservation statements refer only to that check, '
        'not earlier reset changes):\n' + detail + '\n'
        'No automatic retry, cleanup or rollback. Preserve remaining resources. '
        'Use only the engine-pinned inspection commands below, not any unpinned Docker '
        'command in the step detail. These commands do not read HOME contents:\n'
        + '\n'.join(commands) + '\n'
        'Check exact names; empty listings do not prove a timed-out operation has settled. '
        'Do not rerun setup/reset until outstanding operations and ownership are understood. '
        'Follow the Reset failure recovery section in labs/lab1/README.md.'
    )


def reset(docker, confirm=confirm_reset, *, diagnostic=None, tool_output=None):
    """Preflight before deletion; keep only in-memory phase context on failure."""
    report = diagnostic or (lambda message: None)
    phase, had_home = 'ownership', None
    try:
        report('Lab 1 reset started')
        report('Checking reset resource ownership')
        before = owned_state(docker)
        had_home = before[1] is not None
        if before == (None, None):
            phase = 'absent'
            print('Lab 1 is absent; use ./lab.sh lab1 setup.')
            report('Lab 1 reset completed')
            return 0
        phase = 'confirmation'
        if not confirm():
            report('Lab 1 reset cancelled')
            return 3
        phase = 'preflight'
        setup.require_platform(docker)
        setup.configuration.source_snapshot()
        setup.initializer_source()
        print('Reset preflight: preparing tools.\n'
              'Public tooling details are in the reported private log. No Lab 1 files deleted yet.', flush=True)
        report('Reset tooling preflight started; deletion has not started')
        options = {'build': True}
        if diagnostic is not None:
            options['diagnostic'] = diagnostic
        if tool_output is not None:
            options['tool_output'] = tool_output
        with contextlib.redirect_stdout(io.StringIO()):
            image = tools.tools_image(docker, **options)
        print('Reset preflight: checking the preparation key offline; private output is not logged.', flush=True)
        report('Reset private credential preflight; output excluded')
        setup.check_preparation_credential(docker, image)
        same_identity(before, owned_state(docker))
        print('Reset preflight passed. Replacing only Lab 1 container and HOME.', flush=True)
        report('Reset deletion phase starting')
        phase = 'stopping'
        # Confirmed discard must not depend on possibly broken UI settings.
        stop_owned(docker, before, discard=True)
        same_identity(before, owned_state(docker))
        if before[0] is not None:
            phase = 'container-removal'
            docker.run(['rm', before[0]['Id']])
        phase = 'home-check'
        remaining = owned_state(docker)
        same_identity((None, before[1]), remaining)
        if had_home:
            phase = 'home-removal'
            docker.run(['volume', 'rm', setup.VOLUME])
        phase = 'recreation'
        report('Reset starter setup starting')
        message = setup.setup(docker, diagnostic=diagnostic, tool_output=tool_output)
        phase = 'completion'
        print(message)
        report('Lab 1 reset completed')
        return 0
    except (Exception, KeyboardInterrupt) as error:  # noqa: BLE001 - Preserve phase; redact raw failures.
        raise reset_failure(docker, phase, had_home, error) from None


def logged_reset(docker, path, verbose):
    """A secondary log failure must not replace the primary reset outcome."""
    failure, status = None, None
    try:
        with Log(path, sys.stderr if verbose else None) as log:
            try:
                status = reset(docker, diagnostic=log.event, tool_output=log.output)
            except (ResetFailed, ResetInterrupted) as error:
                failure = error
                try:
                    label = 'interrupted' if isinstance(error, ResetInterrupted) else 'failed'
                    log.event('Lab 1 reset ' + label + '; no automatic retry\n' + str(error))
                except (Exception, KeyboardInterrupt):  # noqa: BLE001 - Report secondary logging loss, retain primary.
                    print('Could not record the reset failure in the private log; '
                          'the original reset outcome follows.', file=sys.stderr)
                raise
        return status
    except (Exception, KeyboardInterrupt) as error:
        # Log close can also mask the primary failure.
        if failure is not None:
            raise failure from None
        if status is not None:
            raise reset_failure(docker, 'final-log', None, error) from None
        raise


def main(args=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("action", choices=("enter", "stop", "reset"))
    parser.add_argument("--endpoint", required=True)
    parser.add_argument('-v', '--verbose', action='store_true')
    options = parser.parse_args(args)
    if options.action in ("enter", "reset") and not (
            sys.stdin.isatty() and sys.stdout.isatty() and sys.stderr.isatty()):
        parser.error("An interactive terminal is required; no changes made")
    try:
        progress(f"Lab 1 {options.action}: validating selected resources; no automatic repair.", verbose=options.verbose)
        docker = tools.Docker(options.endpoint)
        if options.action == "enter":
            return enter(docker)
        if options.action == "reset":
            path = setup.default_log_path()
            print(f"[INFO] Private tooling log: {str(path)!r}", file=sys.stderr, flush=True)
            return logged_reset(docker, path, options.verbose)
        print(stop(docker))
        return 0
    except ResetInterrupted as error:
        print(str(error), file=sys.stderr)
        return 130
    except KeyboardInterrupt:
        print('Interrupted; Lab 1 state may be partial. No automatic retry or cleanup. '
              'Save needed work and inspect any private tooling log path reported above before continuing.', file=sys.stderr)
        return 130
    except (Refused, ui.UIRefused, LogRefused, tools.ToolFailure) as error:
        print(str(error), file=sys.stderr)
    except Exception as error:  # noqa: BLE001 - Final privacy boundary for unexpected failures.
        # Raw transport/UI/credential errors may contain private data.
        print("Lab 1 command failed; existing/partial state retained. No automatic repair. "
              + tools.failure_hint(error), file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())

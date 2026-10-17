"""Lab 2 entry and preserving stop for setup-created runs; no host run ledger.

Callers must run lifecycle operations sequentially with setup/preparation and
other labs. Entry uses the installed runtime, never today's rebuilt tag or
starter/configuration.
No credential refresh, model prompt, migration, reset or automatic recovery.
"""

import argparse
import json
import subprocess
import sys
import time
from http.client import HTTPConnection
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lab2_profile as profile
import lab2_resources as resources
import lab2_state as state
import lab2_ui as ui
import lab_tools as tools
from lab_log import progress

Refused = state.Refused

# Fixed loopback inside each service guest; no environment proxies or redirects.
HEALTH = '''import sys
from http.client import HTTPConnection
connection=HTTPConnection('127.0.0.1',int(sys.argv[1]),timeout=2)
try:
 connection.request('GET','/health',headers={'Host':'127.0.0.1:'+sys.argv[2]})
 response=connection.getresponse()
 body=response.read(513)
 if response.status!=200 or len(body)>512: raise RuntimeError('Service unavailable')
 sys.stdout.buffer.write(body)
finally:
 connection.close()
'''


def recheck(docker, plan, expected, *, running=False):
    """Revalidate ownership and stable lifecycle state before each effect."""
    state.require_idle(docker, plan.run)
    data = state.guard(docker, plan, expected, complete=True, require_stopped=False)
    if running and any(data[role]["State"]["Running"] is not True for role in resources.CONTAINERS):
        raise Refused("Lab 2 services are not all running; partial state retained, no automatic retry.")
    return data


def service_identity(body, service):
    if len(body) > 512:
        raise ValueError("Service reply exceeds its bound")
    reply = json.loads(body)
    if (not isinstance(reply, dict) or reply != {"service": service, "schema": 1}
            or type(reply["schema"]) is not int):
        raise ValueError("Service identity differs")


def browser_health(port):
    """Probe only the installed loopback port; never follow redirects/proxies."""
    deadline = time.monotonic() + 20
    while True:
        connection = HTTPConnection("127.0.0.1", port, timeout=2)
        try:
            connection.request("GET", "/health")
            response = connection.getresponse()
            if response.status != 200:
                raise ValueError("Browser service unavailable")
            service_identity(response.read(513), "after-lunch-recharge-poc")
            return
        except (OSError, ValueError):
            if time.monotonic() >= deadline:
                raise Refused("Browser readiness incomplete; state retained, no UI launch.") from None
            time.sleep(0.2)
        finally:
            connection.close()


def health(docker, plan, expected):
    for role, port in (("app", 8080), ("collector", 8081), ("gateway", 8080)):
        service = "workshop-diagnostics" if role == "collector" else "after-lunch-recharge-poc"
        deadline = time.monotonic() + 10
        while True:
            recheck(docker, plan, expected, running=True)
            try:
                body = docker.run(["exec", expected[role], "python3", "-I", "-B", "-c", HEALTH,
                                   str(port), str(plan.app_port)], timeout=5)
                service_identity(body, service)
                break
            except (RuntimeError, OSError, ValueError, subprocess.SubprocessError):
                if time.monotonic() >= deadline:
                    raise Refused(f"Lab 2 {role} readiness incomplete; state retained, no UI launch.") from None
                time.sleep(0.2)
    recheck(docker, plan, expected, running=True)
    browser_health(plan.app_port)


def protected_entry_check(docker, container_id, run_id):
    """Use installed guest checks before exposing the manual protected command."""
    profile.validate_run(2, run_id)
    code = ("import sys; sys.path.insert(0, '/opt/secagent/lab2'); "
            "import lab2_launch as launch; launch.preflight(2, sys.argv[1]); "
            "launch.protected_files()")
    try:
        docker.run(["exec", container_id, "python3", "-I", "-B", "-c", code, run_id])
    except Exception:  # noqa: BLE001 - Guest diagnostics can include private configuration.
        raise Refused("Protected guest entry validation failed; no UI launch or fallback. "
                      "Services may remain running; preserve saved state.") from None


def enter(docker, run, *, verbose=False):
    profile.validate_run(run, "0" * 32)
    state.require_idle(docker, run)
    progress("Inspecting installed run and validating recorded image.", verbose=verbose)
    installed = state.existing(docker, run, require_stopped=False)
    if installed is None:
        raise Refused(f"Lab 2 Run {run} setup is required before entry; nothing created.")
    plan, expected = installed
    for role in resources.CONTAINERS:
        data = recheck(docker, plan, expected)
        if not data[role]["State"]["Running"]:
            progress(f"Starting verified {role} container.", verbose=verbose)
            docker.run(["start", expected[role]])
            after = recheck(docker, plan, expected)
            if after[role]["State"]["Running"] is not True:
                raise Refused(f"Lab 2 {role} start is unconfirmed; partial state retained, no retry.")
    progress("Checking service identities and browser readiness.", verbose=verbose)
    health(docker, plan, expected)
    recheck(docker, plan, expected, running=True)
    if run == 2:
        protected_entry_check(docker, expected["agent"], plan.run_id)
    recheck(docker, plan, expected, running=True)
    progress("Restoring starter UI layout and attaching to the installed session.", verbose=verbose)
    ui.prepare_ui(docker, expected["agent"], run, plan.run_id, plan.app_port)
    if run == 2:
        print("Tab 1 protected launch: " + profile.launch_command(run, plan.run_id))
    print("Ctrl+B then q detaches without stopping services. Save editor work before stop.", flush=True)
    recheck(docker, plan, expected, running=True)
    return subprocess.call(
        docker.prefix + ["exec", "-it", "--workdir", profile.PROJECT, expected["agent"], "herdr"],
        env=docker.environment)


def stop(docker, run, *, verbose=False, consented=None):
    """Finish Herdr first, then stop exact owned containers; retain every volume."""
    profile.validate_run(run, "0" * 32)
    state.require_idle(docker, run)
    progress("Inspecting installed run for preserving STOP; no image upgrade.", verbose=verbose)
    installed = state.existing(docker, run, require_stopped=False, validate_image=False)
    if consented is not None and installed != consented:
        raise Refused("Lab 2 identities changed after removal consent; nothing stopped.")
    if installed is None:
        return f"Lab 2 Run {run} has no resources; nothing stopped or removed."
    plan, expected = installed
    data = recheck(docker, plan, expected)
    if data["agent"]["State"]["Running"]:
        print("Save editor work before stop; unsaved buffers may be lost. Saved data is retained.", flush=True)
        session = ui.Session(docker, expected["agent"])
        status = session.status()
        if type(status.get("running")) is not bool:
            raise Refused("Herdr state is unknown; no forced UI stop.")
        if status["running"]:
            if status.get("compatible") is not True or status.get("version") != "0.9.3":
                raise Refused("Matching Herdr 0.9.3 required; no forced UI stop.")
            recheck(docker, plan, expected)
            progress("Stopping verified Herdr session.", verbose=verbose)
            docker.run(["exec", expected["agent"], "herdr", "server", "stop"])
            if session.status().get("running") is not False:
                raise Refused("Herdr stop is unconfirmed; no container stop attempted.")
    for role in reversed(resources.CONTAINERS):
        data = recheck(docker, plan, expected)
        if data[role]["State"]["Running"]:
            progress(f"Stopping verified {role} container.", verbose=verbose)
            docker.run(["stop", "--time", "10", expected[role]])
            after = recheck(docker, plan, expected)
            state.stopped(after[role], plan.name(role))
    after = recheck(docker, plan, expected)
    for role in resources.CONTAINERS:
        state.stopped(after[role], plan.name(role))
    return f"Lab 2 Run {run} stopped (or already stopped); saved work, configuration, credentials and histories retained."


def main(args=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("action", choices=("enter", "stop"))
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--run", required=True, type=int, choices=(1, 2))
    parser.add_argument("-v", "--verbose", action="store_true")
    options = parser.parse_args(args)
    if options.action == "enter" and not all(stream.isatty() for stream in (sys.stdin, sys.stdout, sys.stderr)):
        parser.error("An interactive terminal is required; no changes made")
    try:
        docker = tools.Docker(options.endpoint)
        if options.action == "enter":
            return enter(docker, options.run, verbose=options.verbose)
        print(stop(docker, options.run, verbose=options.verbose))
        return 0
    except KeyboardInterrupt:
        print("Lab 2 command interrupted; requested operations may still finish. Partial state retained; "
              "no automatic retry, rollback or cleanup.", file=sys.stderr)
        return 130
    except (Refused, ui.Refused, tools.ToolFailure) as error:
        print(f"Lab 2 {options.action} did not complete; partial state retained, no automatic retry or cleanup. "
              + str(error), file=sys.stderr)
    except Exception:  # noqa: BLE001 - Final privacy boundary for Docker/guest/UI failures.
        print(f"Lab 2 {options.action} did not complete; operation outcomes may be uncertain and services may "
              "remain running. Partial state retained; no automatic retry, rollback or cleanup. "
              "Private diagnostics excluded.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())

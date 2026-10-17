"""Participant Lab 3 selection/diagnostics and observation-only attachment."""

import argparse
import math
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config_deploy
import config_files
import lab3_guards as guards
import lab3_pipeline as pipeline
import lab3_resources as resources
import lab3_setup as setup
import lab3_ui as ui
import lab_tools as tools
from lab1_setup import SetupRefused, resolve_endpoint
from lab3_state import Refused, State, selected_directory
from lab_log import Log, LogRefused, default_log_path, next_action, progress


def eligible(state):
    record = state.data["resources"]
    expires = record.get("expires")
    if (state.data["phase"] not in ("ready", "running", "inspect", "checking")
            or record["stage"] != "ready" or state.data.get("ui_closed")
            or type(expires) not in (int, float) or not math.isfinite(expires)
            or time.time() >= expires - 120):
        raise Refused("No active Lab 3 observation window; no restart or task replay. "
                      "Use ./lab.sh lab3 run-pipeline only for a fresh stopped preparation; "
                      "after a consumed attempt use STOP and review reset.")


def enter(docker, directory):
    state = State(directory)
    with state.lock("ui.lock"):
        resources.engine_guard(docker, state.data["resources"])
        eligible(state)
        guards.prepared_guard(docker, state.data["resources"])
        ident = state.data["resources"]["containers"]["ui"]["id"]
        print("[INFO] Save Editor work before STOP; detaching does not stop the pipeline.")
        ui.prepare_ui(docker, ident)
        current = State(directory)
        eligible(current)
        resources.engine_guard(docker, current.data["resources"])
        if ui_guard_id(docker, current) != ident:
            raise Refused("Operator identity changed during entry; no attachment. Preserve the session.")
    return subprocess.call(docker.prefix + ["exec", "-it", "-e", "TERM=xterm-256color",
        "--workdir", ui.WORKSPACE, ident, "herdr"], env=docker.environment)


def ui_guard_id(docker, state):
    obj = guards.ui_guard(docker, state.data["resources"])
    if obj["State"]["Running"] is not True:
        raise Refused("Operator UI stopped during entry; no automatic restart. Use the Controller's STOP.")
    return obj["Id"]


def main(args=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("action", choices=("setup", "run-pipeline", "enter", "stop", "reset"))
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--engine-socket")
    options = parser.parse_args(args)
    if options.engine_socket is not None and options.action != "setup":
        parser.error("--engine-socket is selected at setup, not activation")
    if options.action in ("run-pipeline", "enter", "reset") and not all(
            stream.isatty() for stream in (sys.stdin, sys.stdout, sys.stderr)):
        parser.error("Interactive terminal required; no changes")
    os.umask(0o077)
    try:
        with pipeline.interruption_signals():
            progress(f"Lab 3 {options.action}: selecting recorded state and engine.", verbose=options.verbose)
            directory = selected_directory()
            with Log(default_log_path(), sys.stderr if options.verbose else None) as log:
                docker = tools.Docker(resolve_endpoint(log))
                if options.action == "setup":
                    log.event("Lab 3 stopped setup started; no provider enrollment/model task")
                    state, result = setup.setup(docker, directory, engine_socket=options.engine_socket,
                        diagnostic=log.event, tool_output=log.output)
                    log.event("Lab 3 stopped setup completed; runtime activation not checked")
                    print("[PASS] " + result)
                    print("[INFO] Stopped; recorded image/Pi configuration retained. Activation not checked.")
                    progress("Repeat setup does not update image-installed files. Gateway/policy/provider "
                             "application and active configuration were not checked.", verbose=options.verbose)
                    next_step = "run-pipeline" if state.data["phase"] == "prepared" else "reset"
                    next_action("./lab.sh lab3 " + next_step)
                    if next_step == "reset":
                        print("[WARN] Reset deletes this attempt\'s saved work and evidence; default No.")
                    print("[INFO] START is always explicit; no task was submitted.")
                    return 0
            if not os.path.lexists(directory):
                if options.action == "stop":
                    print("[INFO] No selected Lab 3 control state; no stop performed. Unknown resources are not adopted.")
                    return 0
                raise Refused("No selected Lab 3 environment. Use ./lab.sh lab3 setup; "
                              "do not change state roots to bypass existing evidence.")
            if options.action == "enter":
                progress("Validating observation window and operator identity before attachment.", verbose=options.verbose)
                return enter(docker, directory)
            if options.action == "run-pipeline":
                pipeline.run_pipeline(docker, directory, verbose=options.verbose)
                return 0
            if options.action == "reset":
                from lab3_dispose import reset
                print(reset(docker, directory, verbose=options.verbose))
                return 0
            progress("Verifying owned STOP and provider settlement; retaining evidence.", verbose=options.verbose)
            pipeline.stop(docker, directory)
            print("[STOPPED] Recorded owned resources stopped; evidence retained. "
                  "No upstream account key revocation or cloud-request cancellation is implied.")
            return 0
    except BlockingIOError:
        print("[FAIL] Lab 3 is busy. Use the live Controller\'s STOP, or wait for entry to finish.", file=sys.stderr)
        next_action("After the Controller exits: ./lab.sh lab3 stop", stream=sys.stderr)
    except (Refused, config_deploy.Refused, config_files.Refused, ui.Refused,
            SetupRefused, setup.software.Refused, LogRefused) as error:
        print("[FAIL] " + str(error), file=sys.stderr)
    except (EOFError, KeyboardInterrupt):
        print("[FAIL] Interrupted/cancelled; no success claimed. Keep state and partial resources. "
              "After the Controller exits use ./lab.sh lab3 stop; do not retry an uncertain creation.", file=sys.stderr)
    except Exception:  # noqa: BLE001 - Never publish private native/configuration payloads.
        print("[FAIL] Lab 3 operation failed; the underlying cause cannot safely be distinguished. "
              "Preserve state, partial resources and private evidence. Check the last setup stage in the "
              "private lab-log.txt, or the selected control phase/pending operation. After the Controller "
              "exits use ./lab.sh lab3 stop; do not reset or retry to bypass uncertainty.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

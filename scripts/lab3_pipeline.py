"""Lab 3 activation/START/CHECK/STOP; no setup, image selection or task replay.

Only recorded images and installed public configuration are used. A consumed
attempt cannot be resumed by entry or a second Controller. No rehearsal imports.
"""

import contextlib
import os
import select
import signal
import sys
import termios
import time

import lab3_guards as guards
import lab3_resources as resources
from lab3_controller import Controller
from lab3_native import FAILURES, Native
from lab3_state import Refused, State
from lab_log import progress


def ask(prompt, seconds):
    print(prompt, flush=True)
    if seconds <= 0 or not select.select([sys.stdin], [], [], seconds)[0]:
        raise TimeoutError("Observation window ended")
    line = os.read(sys.stdin.fileno(), 4096)
    if not line:
        raise EOFError("Terminal detached")
    return line.decode("utf-8", errors="replace").strip()


def flush_input():
    if sys.stdin.isatty():
        termios.tcflush(sys.stdin.fileno(), termios.TCIFLUSH)


@contextlib.contextmanager
def interruption_signals():
    previous, delivered = {}, False

    def interrupt(signum, frame):
        nonlocal delivered
        if not delivered:
            delivered = True
            raise KeyboardInterrupt

    try:
        for signum in (signal.SIGHUP, signal.SIGTERM):
            previous[signum] = signal.signal(signum, interrupt)
        yield
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)


def interact(controller, *, read_action=ask):
    record = controller.state.data["resources"]
    port = record["viewer_port"]
    print(f"Preview: http://127.0.0.1:{port}/protected/preview.html")
    print(f"Live:    http://127.0.0.1:{port}/protected/live.html")
    print("In a separate terminal: ./lab.sh lab3 enter; select sandbox:", record["sandbox"])
    print("The Editor walkthrough explains the two paths. Compare baseline revision/time before START.")
    inputs = controller.native.task_inputs()
    for title, content in inputs.items():
        print(f"[{title}]\n{content}")
    note = ("Before STOP: save Editor work and detach the observation UI (Ctrl+B, then q). "
            "Detaching does not stop services; type STOP here afterward.")
    while True:
        action = read_action("Type START after baseline/TUI inspection, or STOP.\n" + note, controller.time_left())
        if action == "STOP":
            return
        if action == "START":
            flush_input()
            controller.start()
            flush_input()
            break
    print("[INSPECT] Agent task completed. Model access removed. Refresh Preview and Live.")
    if controller.state.data.get("fallback_available"):
        print("No publication attempt observed in captured native events. CHECK is optional scripted evidence, not agent behavior.")
    else:
        print("Identify the denied publication request's method, path, policy and outcome in native logs.")
    print("Should a preview helper publish? Do not widen policy to silence a denial.")
    while True:
        offer = controller.state.data.get("fallback_available")
        prompt = note + "\nType STOP when finished." + (" CHECK runs one labelled scripted probe." if offer else "")
        action = read_action(prompt, controller.time_left())
        if action == "STOP":
            return
        if action == "CHECK" and offer:
            controller.boundary_check()
            flush_input()


def run_pipeline(docker, directory, *, read_action=ask, verbose=False):
    """Activate one selected prepared environment, never plan or reseed one.

    The first activation consumes its finite window before any start request.
    Re-entry/repeat calls cannot extend it or replay a consumed pipeline/START.
    Private state placement is provisional; participant selection is not wired.
    """
    progress("Validating fresh stopped preparation; START remains explicit.", verbose=verbose)
    state = State(directory)
    try:
        with state.lock(), interruption_signals():
            record = state.data["resources"]
            resources.engine_guard(docker, record)
            if (state.data["phase"] != "prepared" or record["stage"] != "prepared"
                    or record.get("expires") is not None or record.get("pending")
                    or state.data.get("operators_pending") or state.data.get("enrollment_pending")
                    or state.data.get("provider_conflict")):
                raise Refused("Selected environment is not a fresh stopped preparation; no restart, replacement or replay")
            native = Native(docker, state)
            # A refusal here must not stop an already-running selected resource.
            guards.prepared_guard(native, record, active=False)
            record["expires"] = time.time() + 1800
            state.phase("starting")  # Persist the consumed window before start.
            controller = Controller(state, native)
            stage = "provider-free activation"
            primary_failure = False
            try:
                with native.window(controller.total_left(), stop_all=True):
                    progress("Activating provider-free runtime.", verbose=verbose)
                    resources.activate(native, record, state.save)
                    state.phase("new")
                    stage = "pre-START validation"
                    progress("Checking pre-START readiness.", verbose=verbose)
                    controller.prepare()
                    stage = "Controller interaction"
                    interact(controller, read_action=read_action)
            except BaseException as error:
                if (isinstance(error, TimeoutError) and stage == "Controller interaction"
                        and state.data["outcome"] in ("not-started", "completed", "completed-with-scripted-check")):
                    print("[INFO] Observation window ended; no retry. Verifying STOP.")
                else:
                    primary_failure = True
                    outcome = state.data["outcome"]
                    if outcome not in ("completed", "completed-with-scripted-check", "failed"):
                        outcome = "interrupted-or-failed"
                    state.change(failure_stage=state.data.get("failure_stage", stage),
                        failure_kind=state.data.get("failure_kind", (
                            "timeout" if isinstance(error, TimeoutError) else
                            "interrupted" if isinstance(error, (KeyboardInterrupt, EOFError)) else "operation failed")),
                        outcome=outcome)
                    raise
            finally:
                # activate rechecks immediately before consuming its mutations.
                # If it refused that check, preserve the environment unchanged.
                if record["stage"] != "prepared":
                    try:
                        controller.stop()
                    except FAILURES:
                        if not primary_failure:
                            raise
                        print("[FAIL] STOP settlement remains unconfirmed; the original failure follows. "
                              "Keep state/evidence and use explicit ./lab.sh lab3 stop after the Controller exits.",
                              file=sys.stderr)
    except Refused:
        raise
    except (*FAILURES, EOFError, KeyboardInterrupt):
        failed_at = state.data.get("failure_stage")
        if failed_at not in ("provider-free activation", "pre-START validation", "Controller interaction",
                             "provider enrollment/readiness", "agent execution", "provider revocation",
                             "website validation", "native event inspection", "execution shutdown"):
            failed_at = "activation/STOP validation"
        raise Refused("Lab 3 pipeline failed/interrupted at " + failed_at + ". State and private evidence retained; "
                      "inspect the recorded phase and use explicit STOP recovery after the controller exits. "
                      "Do not resubmit START or create another attempt to bypass unresolved cleanup.") from None
    print("[STOPPED] Owned lab resources stopped; private evidence retained. "
          "Local STOP does not cancel requests already accepted upstream.")
    return state


def stop(docker, directory, *, consented=None):
    """Recover STOP without requiring a valid/unexpired model-execution window."""
    state = State(directory)
    with state.lock():
        if consented is not None:
            state.check_directory()
            state = State(directory)
            if (state.root_identity != consented["root_identity"]
                    or state.data != consented["state"]):
                raise resources.Refused("Lab 3 control identity changed after removal consent; nothing stopped.")
        record = state.data["resources"]
        resources.engine_guard(docker, record)
        native = Native(docker, state)
        if state.data["phase"] == "prepared" and record["stage"] == "prepared":
            guards.prepared_guard(native, record, active=False)
            return state  # Already stopped; do not consume a fresh preparation.
        try:
            if record.get("pending") in ("sandbox", "native-storage"):
                native.stop(settle_create=True)
            else:
                native.stop()
        except BaseException:
            state.phase("cleanup-needed")
            raise
        record["stage"] = "stopped"
        state.phase("stopped")
    return state

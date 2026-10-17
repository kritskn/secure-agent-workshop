"""Confirmed selected-run Lab 2 replacement; no archives, host ledger or implicit stop.

Preflight current inputs and the preparation key before deletion. Hold the same
per-run reservation through deletion/recreation; uncertain outcomes block reuse.
The other run, preparation, images and host logs are never reset here.
"""

import argparse
import contextlib
import io
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lab2_resources as resources
import lab2_setup as setup
import lab2_state as state
import lab_tools as tools


def engine_identity(docker):
    identity = docker.run(["info", "--format", "{{.ID}}"]).strip()
    if not identity:
        raise state.Refused("Selected engine identity is unavailable; no reset.")
    return identity


def recheck(docker, plan, expected, engine, reservation=None):
    """Validate exactly the remaining old generation before each destructive effect."""
    if reservation is not None:
        reservation()
    if engine_identity(docker) != engine:
        raise state.Refused("Selected engine changed; preserve resources without another reset attempt.")
    state.require_idle(docker, plan.run, allow_reservation=reservation is not None)
    if state.inventory(docker, plan.run) != set(expected):
        raise state.Refused("Selected run resource set changed; preserve remaining resources without adoption.")
    data = state.guard(docker, plan, expected, complete=True)
    for role in expected:
        if plan.roles()[role] == "network":
            refs = set(docker.run(["container", "ls", "--all", "--no-trunc", "--quiet",
                                   "--filter", "network=" + plan.name(role)]).splitlines())
            allowed = {expected[container] for container in resources.CONTAINERS
                       if container in expected and role in plan.networks(container)}
            if refs - allowed:
                raise state.Refused(f"Network {plan.name(role)!r} has unrelated references; preserve it.")
    return data


def show_reset_plan(plan, expected, stream):
    print(f"Reset Lab 2 Run {plan.run} only; browser port {plan.app_port} is retained.", file=stream)
    for role, kind in plan.roles().items():
        print(f"  delete {kind}: {plan.name(role)!r} ({expected[role]})", file=stream)
    print("This deletes the selected run's saved project edits, HOME/configuration, credentials, "
          "histories/logs, orders and receipts. No archive or rollback.", file=stream)
    print("The other run, preparation, Lab 1, images/cache, host logs and source remain. "
          "Fresh storage receives current starter/configuration inputs and the selected preparation key. "
          "This cannot undo prior key exposure, revoke upstream keys or cancel submitted requests.", file=stream)


def reset(docker, run, *, confirm=None, stream=None, verbose=False):
    """One default-No decision; preflight failures precede any participant deletion."""
    setup.profile.validate_run(run, "0" * 32)
    stream = sys.stdout if stream is None else stream
    phase = "inspection"
    deletion_started = False
    try:
        setup.progress("Inspecting engine, selected-run identity and stopped state.", verbose=verbose, stream=stream)
        engine = engine_identity(docker)
        state.require_idle(docker, run)
        installed = state.existing(docker, run, validate_image=False)
        if installed is None:
            return f"Lab 2 Run {run} is absent; nothing reset. Use ./lab.sh lab2 setup --run {run}."
        old, expected = installed
        recheck(docker, old, expected, engine)
        show_reset_plan(old, expected, stream)
        phase = "confirmation"
        accepted = confirm() if confirm is not None else input("Discard and recreate this Lab 2 run? (y/N) ").strip().lower() in ("y", "yes")
        if accepted is not True:
            return f"Lab 2 Run {run} reset cancelled; nothing deleted."
        recheck(docker, old, expected, engine)
        phase = "replacement preflight"
        print("Preparing current public images; downloads may occur. No lab data deleted yet.", file=stream, flush=True)
        with contextlib.redirect_stdout(io.StringIO()):
            setup.progress("Preparing shared tooling image.", verbose=verbose, stream=stream)
            tools.tools_image(docker, build=True)
            setup.progress("Preparing replacement Lab 2 image.", verbose=verbose, stream=stream)
            image, _ = setup.software.image(docker, build=True)
        plan = resources.Plan(run, uuid.uuid4().hex, image, old.app_port)
        with setup.reserve(docker, run, image) as reservation:
            def creation_check():
                reservation()
                if engine_identity(docker) != engine:
                    raise state.Refused("Selected engine changed; preserve this run and its reservation.")
                state.require_idle(docker, run, allow_reservation=True)

            setup.progress("Reservation held; checking fresh storage and selected preparation key.",
                           verbose=verbose, stream=stream)
            source = setup.fresh_preflight(docker, plan, creation_check, stream)
            recheck(docker, old, expected, engine, reservation)
            print("Preflight passed. Deleting only the confirmed stopped run; no rollback is possible.",
                  file=stream, flush=True)
            remaining = dict(expected)
            try:
                for kind in ("container", "network", "volume"):
                    roles = reversed(resources.CONTAINERS) if kind == "container" else tuple(plan.roles())
                    for role in roles:
                        if plan.roles()[role] != kind:
                            continue
                        phase = f"{kind} removal ({old.name(role)})"
                        recheck(docker, old, remaining, engine, reservation)
                        target = old.name(role) if kind == "volume" else remaining[role]
                        deletion_started = True
                        docker.run([kind, "rm", target], timeout=None)
                        del remaining[role]
                        recheck(docker, old, remaining, engine, reservation)
                        print(f"Removed {kind}: {old.name(role)!r}", file=stream, flush=True)
                phase = "recreation"
                creation_check()
                setup.progress("Recreating selected run under the same reservation.", verbose=verbose, stream=stream)
                message = setup.create_fresh(docker, plan, source, creation_check, stream)
            except (Exception, KeyboardInterrupt) as error:  # noqa: BLE001 - Preserve reservation after every uncertain deletion/recreation outcome.
                reason = str(error) if isinstance(error, (state.Refused, setup.Uncertain)) else "Private diagnostics excluded."
                raise setup.Uncertain(f"Lab 2 Run {run} reset stopped during {phase}. "
                                      "Deletion may be partial and replacement may be incomplete; remaining data is preserved. "
                                      "Do not retry setup/reset, remove the reservation or force deletion. "
                                      "Inspect selected-run identities and workers before an explicitly agreed recovery. "
                                      + reason) from None
            phase = "reservation release"
        return (f"Lab 2 Run {run} reset completed; fresh generation {plan.run_id}, browser port {plan.app_port}. "
                + message + " Other runs and preparation were not changed.")
    except (state.Refused, setup.Uncertain, EOFError, KeyboardInterrupt):
        raise
    except Exception:  # noqa: BLE001 - Never relay Docker, build or credential diagnostics.
        status = "Deletion may have begun; preserve remaining resources." if deletion_started else "No participant data was deleted by this reset."
        raise state.Refused(f"Lab 2 Run {run} reset failed or was interrupted during {phase}. {status} "
                            "Inspect the selected run and any reservation/workers; no automatic retry or recovery. "
                            "Private diagnostics excluded.") from None


def main(args=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--run", required=True, choices=(1, 2), type=int)
    parser.add_argument("-v", "--verbose", action="store_true")
    options = parser.parse_args(args)
    if not all(stream.isatty() for stream in (sys.stdin, sys.stdout, sys.stderr)):
        parser.error("Reset requires an interactive terminal; nothing reset")
    try:
        print(reset(tools.Docker(options.endpoint), options.run, verbose=options.verbose))
        return 0
    except (EOFError, KeyboardInterrupt):
        print("Reset cancelled/interrupted; inspect printed progress and preserve remaining resources.", file=sys.stderr)
        return 130
    except state.NotStopped as error:
        if options.verbose:
            print(str(error) + setup.inspection_hint(options.run), file=sys.stderr)
        return 3  # lab2.sh renders the stopped-state next action without redirecting consent I/O.
    except (state.Refused, setup.Uncertain) as error:
        print(str(error) + setup.inspection_hint(options.run, verbose=options.verbose), file=sys.stderr)
    except Exception:  # noqa: BLE001 - Final privacy boundary.
        print("Lab 2 reset refused or incomplete; inspect selected-run status and any reservation. "
              "Preserve remaining resources; private diagnostics excluded, no automatic retry.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())

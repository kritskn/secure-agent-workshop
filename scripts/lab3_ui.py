"""Observation-only Lab 3 operator UI; the pipeline remains separate.

Before calling prepare_ui, the entry controller must validate the exact running
container/image, socket-free mounts, selected gateway, attempt eligibility and
expiry. This module does not establish those facts or attach the terminal.
It only prepares Herdr, OpenShell's native TUI and Fresh. It never provisions,
enrolls, submits a task, reads screens/history or resets an existing session.
Import is inert; participant entry wiring remains a separate integration slice.
"""

import json
import subprocess
import time

import lab1_ui as shared

WORKSPACE = "/home/lab-user/workshop/lab3"
COMMANDS = ("cd -- " + WORKSPACE + " && openshell term",
            "cd -- " + WORKSPACE + " && fresh --no-upgrade-check .")
APPS = ("openshell", "fresh")
LABELS = ("OpenShell", "Editor")
Refused = shared.UIRefused


def require_ui_cpus(docker):
    """Retain the reference's two-CPU prerequisite on the selected engine."""
    try:
        count = json.loads(docker.run(["info", "--format", "{{json .NCPU}}"], timeout=5))
    except (RuntimeError, OSError, ValueError, TypeError, subprocess.SubprocessError):
        raise Refused("Cannot verify Lab 3 engine CPU count; no UI startup. "
                      "Check docker info on the selected engine before retrying.") from None
    if type(count) is not int or count < 2:
        raise Refused("Lab 3 OpenShell UI requires an engine reporting at least 2 CPUs; "
                      "no UI startup. Check the selected engine's CPU allocation.")


class Session(shared.Session):
    def api(self, *arguments):
        output = self.docker.run(["exec", "--workdir", WORKSPACE,
                                  self.container_id, "herdr", *arguments])
        if arguments[:2] == ("pane", "run"):
            return {}
        return json.loads(output)["result"]


def states(session, panes):
    return [shared.process_state(session.process_info(pane), app)
            for pane, app in zip(panes, APPS)]


def prepare_session(session, cold):
    """Initialize empty UI or reuse live apps; refuse conflicts without repair."""
    empty = not session.api("workspace", "list")["workspaces"]
    if empty:
        session.api("workspace", "create", "--cwd", WORKSPACE,
                    "--label", "Lab 3", "--no-focus")
        cold = True
    workspace_id, panes = shared.layout(session)
    if empty:
        for pane in panes:
            shared.wait_shell(session, pane)
    current = states(session, panes)
    if not cold:
        if len(panes) != 2 or current != ["app", "app"]:
            raise Refused("Lab 3 UI is partial/conflicting; existing work preserved. "
                          "Inspect the existing operator session; no automatic relaunch.")
        return {"mode": "reattach", "apps_started": 0}
    if any(state != "shell" for state in current):
        raise Refused("Cold Lab 3 layout contains non-shell processes; existing work preserved. "
                      "Inspect the operator session before retrying; no automatic relaunch.")
    if len(panes) == 1:
        session.api("tab", "create", "--workspace", workspace_id,
                    "--cwd", WORKSPACE, "--label", "Editor", "--no-focus")
        _, panes = shared.layout(session)
        shared.wait_shell(session, panes[1])
    for pane, command, label in zip(panes, COMMANDS, LABELS):
        session.api("tab", "rename", pane["tab_id"], label)
        session.api("pane", "run", pane["pane_id"], command)
    deadline = time.monotonic() + 15
    while states(session, panes) != ["app", "app"]:
        if time.monotonic() >= deadline:
            raise Refused("Lab 3 UI startup incomplete; processes/layout retained, no retry. "
                          "Inspect the operator session before another entry attempt.")
        time.sleep(0.2)
    return {"mode": "started", "apps_started": 2}


def prepare_ui(docker, container_id):
    """Prepare views only in a caller-validated running operator container.

    The caller must also protect private transport errors and recheck attempt
    eligibility before terminal attachment. Failure may leave partial UI startup;
    do not retry automatically or claim that the attempt/provider was stopped.
    """
    require_ui_cpus(docker)
    session = Session(docker, container_id)
    status = session.status()
    cold = not status["running"]
    if cold:
        docker.run(["exec", "--detach", "--workdir", WORKSPACE,
                    container_id, "herdr", "server"])
        deadline = time.monotonic() + 5
        while not session.status()["running"]:
            if time.monotonic() >= deadline:
                raise Refused("Herdr startup incomplete; existing state retained. "
                              "Inspect the operator session; no automatic retry.")
            time.sleep(0.1)
        status = session.status()
    if not status.get("compatible") or status.get("version") != "0.9.3":
        raise Refused("Matching Herdr 0.9.3 server required; existing state retained. "
                      "Check operator tooling; no automatic upgrade or reset.")
    return prepare_session(session, cold)

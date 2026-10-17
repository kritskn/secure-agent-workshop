"""Two-tab Lab 1 UI, shared by production and author launchers.

The caller validates the container before using this module. Never reads screen
contents, credentials or conversation history; never resumes an old Pi session.
"""

import json
import time

WORKSPACE = "/home/lab-user/workshop/lab1"
COMMANDS = ("cd -- /home/lab-user/workshop/lab1 && pi",
            "cd -- /home/lab-user/workshop/lab1 && fresh --no-upgrade-check .")


class UIRefused(RuntimeError):
    """Only authored, public layout/status diagnostics may be displayed."""


class Session:
    """One explicit guest/container session; no implicit focused-pane mutations."""

    def __init__(self, docker, container_id):
        self.docker = docker
        self.container_id = container_id

    def api(self, *arguments):
        output = self.docker.run(["exec", "--workdir", WORKSPACE,
                                  self.container_id, "herdr", *arguments])
        # v0.9.3 pane run acknowledges in plain text, unlike metadata commands.
        if arguments[:2] == ("pane", "run"):
            return {}
        return json.loads(output)["result"]

    def status(self):
        return json.loads(self.docker.run(["exec", self.container_id,
                                            "herdr", "status", "--json"]))["server"]

    def process_info(self, pane):
        return self.api("pane", "process-info", "--pane", pane["pane_id"])["process_info"]


def process_state(info, expected):
    """Only process metadata, not terminal screens, command text or chat history."""
    processes = info.get("foreground_processes", [])
    if len(processes) == 1:
        process = processes[0]
        if process.get("name") == expected:
            return "app"
        if (process.get("pid") == info.get("shell_pid")
                and process.get("name") == "bash"):
            return "shell"
    return "conflict"


def layout(session):
    workspaces = session.api("workspace", "list")["workspaces"]
    if len(workspaces) != 1:
        raise UIRefused("Expected one existing workspace; preserve custom layout")
    workspace_id = workspaces[0]["workspace_id"]
    tabs = sorted(session.api("tab", "list", "--workspace", workspace_id)["tabs"],
                  key=lambda item: item["number"])
    panes = session.api("pane", "list", "--workspace", workspace_id)["panes"]
    if len(tabs) not in (1, 2) or len(panes) != len(tabs):
        raise UIRefused("Expected one pane per tab; preserve custom layout")
    ordered = []
    for tab in tabs:
        matches = [pane for pane in panes if pane["tab_id"] == tab["tab_id"]]
        if len(matches) != 1 or tab.get("pane_count") != 1:
            raise UIRefused("Conflicting tab topology; preserved")
        ordered.append(matches[0])
    return workspace_id, ordered


def wait_shell(session, pane):
    deadline = time.monotonic() + 5
    while process_state(session.process_info(pane), "fresh") != "shell":
        if time.monotonic() >= deadline:
            raise UIRefused("New shell not ready; partial layout retained")
        time.sleep(0.1)


def prepare_session(session, cold):
    """Initialize an empty server; otherwise validate before any pane commands."""
    empty = not session.api("workspace", "list")["workspaces"]
    if empty:
        session.api("workspace", "create", "--cwd", WORKSPACE,
                    "--label", "Lab 1", "--no-focus")
        cold = True
    workspace_id, panes = layout(session)
    if empty:
        for pane in panes:
            wait_shell(session, pane)
    states = [process_state(session.process_info(pane), expected)
              for pane, expected in zip(panes, ("pi", "fresh"))]
    if not cold:
        if len(panes) != 2 or states != ["app", "app"]:
            raise UIRefused("Running session is partial/conflicting; keep existing work")
        return {"mode": "reattach", "apps_started": 0}
    if any(state != "shell" for state in states):
        raise UIRefused("Cold restored layout is not plain Bash shells; preserved")
    if len(panes) == 1:
        session.api("tab", "create", "--workspace", workspace_id,
                    "--cwd", WORKSPACE, "--label", "Editor", "--no-focus")
        _, panes = layout(session)
        wait_shell(session, panes[1])
    for pane, command, label in zip(panes, COMMANDS, ("Agent", "Editor")):
        session.api("tab", "rename", pane["tab_id"], label)
        session.api("pane", "run", pane["pane_id"], command)
    deadline = time.monotonic() + 15
    while True:
        if all(process_state(session.process_info(pane), expected) == "app"
               for pane, expected in zip(panes, ("pi", "fresh"))):
            return {"mode": "started", "apps_started": 2}
        if time.monotonic() >= deadline:
            raise UIRefused("UI startup incomplete; processes/layout retained, no retry")
        time.sleep(0.2)


def prepare_ui(docker, container_id):
    """Start/attach UI in an already running, caller-validated container."""
    session = Session(docker, container_id)
    status = session.status()
    cold = not status["running"]
    if cold:
        docker.run(["exec", "--detach", "--workdir", WORKSPACE,
                    container_id, "herdr", "server"])
        deadline = time.monotonic() + 5
        while not session.status()["running"]:
            if time.monotonic() >= deadline:
                raise UIRefused("Herdr startup incomplete; existing state retained")
            time.sleep(0.1)
        status = session.status()
    if not status.get("compatible") or status.get("version") != "0.9.3":
        raise UIRefused("Matching Herdr 0.9.3 server required; no upgrades/resets")
    return prepare_session(session, cold)

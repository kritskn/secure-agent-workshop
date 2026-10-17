"""Three-tab Lab 2 UI; caller validates the running isolated guest first.

Only Herdr and kernel process metadata are read. No screens/history,
resume, model prompts, reset,
policy bypass or automatic protected Pi. Unknown/partial live layouts refuse.
Interactive nono foreground metadata remains a native qualification gate.
"""

import json
import shlex
import time

import lab1_ui as shared
import lab2_profile as profile

Refused = shared.UIRefused
launch_command = profile.launch_command

# Linux nono supervises Pi on a separate PTY/process group. Read only kernel
# names/IDs/parent groups, never argv, environment, screens or private files.
SUPERVISOR_METADATA = '''import json,sys
from pathlib import Path
parent,shell,group=map(int,sys.argv[1:])
def stat(path):
 raw=path.read_text()
 left,separator,right=raw.rpartition(')')
 if not separator or '(' not in left: raise RuntimeError('Invalid process metadata')
 fields=right.split()
 return {'name':left.split('(',1)[1],'pid':int(path.parent.name),
         'ppid':int(fields[1]),'pgid':int(fields[2])}
actual=stat(Path('/proc')/str(parent)/'stat')
if actual != {'name':'nono','pid':parent,'ppid':shell,'pgid':group}:
 raise RuntimeError('Supervisor changed')
children=[]
for path in Path('/proc').iterdir():
 if not path.name.isdigit(): continue
 try: child=stat(path/'stat')
 except FileNotFoundError: continue
 if child['ppid']==parent:
  children.append({key:child[key] for key in ('name','pid','ppid')})
print(json.dumps(children))
'''


def nono_foreground(info):
    processes = info.get("foreground_processes", [])
    if len(processes) != 1 or processes[0].get("name") != "nono":
        return None
    parent = processes[0]
    ids = (parent.get("pid"), info.get("shell_pid"), info.get("foreground_process_group_id"))
    if (all(type(pid) is int and pid > 0 for pid in ids)
            and ids[0] != ids[1] and ids[0] == ids[2]):
        return parent
    return None


class Session(shared.Session):
    def api(self, *arguments):
        output = self.docker.run(["exec", "--workdir", profile.PROJECT,
                                  self.container_id, "herdr", *arguments])
        if arguments[:2] == ("pane", "run"):
            return {}
        return json.loads(output)["result"]

    def process_info(self, pane):
        info = super().process_info(pane)
        parent = nono_foreground(info)
        if parent is not None:
            try:
                children = self.docker.run(["exec", self.container_id, "python3", "-I", "-B", "-c",
                    SUPERVISOR_METADATA, str(parent["pid"]), str(info["shell_pid"]),
                    str(info["foreground_process_group_id"])])
                info["supervisor_children"] = json.loads(children)
            except Exception:  # noqa: BLE001 - Process/transport diagnostics must stay private.
                raise Refused("Supervisor metadata unavailable; existing UI preserved") from None
        return info


def browser_box(port):
    if type(port) is not int or not 1024 <= port <= 65535:
        raise ValueError("Validated browser port required")
    border = "   +" + "-" * 35 + "+"
    return "\n".join((border, "   |    " + "Open in your browser:".ljust(31) + "|",
                      "   |    " + f"http://127.0.0.1:{port}".ljust(31) + "|", border))


def screen_banner(text):
    """Print literal public text after clearing visible command echo, not history."""
    lines = text.splitlines()
    # Clear once, then repeat only the data/newline format for each argument.
    # Separate printf keeps the generated Bash format line within 80 columns.
    # Double-quote a trailing literal backslash to avoid ShellCheck's SC1003
    # ambiguity at a single-quote boundary; this remains printf data only.
    arguments = [shlex.quote(line[:-1]) + '"\\\\"' if line.endswith("\\")
                 else shlex.quote(line) for line in lines]
    return "printf '\\033[H\\033[2J'\nprintf '%s\\n' \\\n" + " \\\n".join(
        "  " + argument for argument in arguments)


def protected_banner(run_id):
    profile.validate_run(2, run_id)
    lines = ("Configure protected Pi first:",
             "1. Editor tab -> Sandbox card.",
             "2. Remove whole-HOME grant; finish the rule exercise.",
             "3. Save policy; reproduce the browser bug.",
             "4. Return to Agent and run the Pi command below.",
             "5. Finish repair/review; exit Pi, then inspect audit.")
    width = max(len(line) for line in lines)
    border = "   +" + "-" * (width + 8) + "+"
    box = "\n".join((border, *("   |    " + line.ljust(width) + "    |"
                                    for line in lines), border))
    # Keep the complete runnable command outside the border for easy copying.
    return (box + "\n\nIn Agent — protected Pi:\n```\n"
            + launch_command(2, run_id) + "\n```")


def commands(run, run_id, app_port=18080):
    profile.validate_run(run, run_id)
    project = "cd -- " + profile.PROJECT
    first = project + " && \\\n  " + launch_command(run, run_id)
    if run == 2:
        # Public, constructed inputs; filtering happens when the learner runs
        # nono. Narrowing the starter must exclude supervisor state before launch.
        environment = profile.environment(run_id) | {"HOME": profile.HOME, "TMPDIR": "/tmp"}
        exports = "\n".join("export " + key + "=" + shlex.quote(value)
                            for key, value in environment.items())
        first = project + " || exit\n" + exports + "\n" + screen_banner(protected_banner(run_id))
    # A directory-only launch opens the explorer and preserves Fresh's restore.
    # Create-only init.ts seeds cards/policy; participants open the guide manually.
    second = project + " && \\\n  fresh --no-upgrade-check ."
    shell = (browser_box(app_port) + "\n\nEditor: select Lab 2, open README.md in Explorer.\n"
             "Run 2: configure policy before reproducing the bug.\n"
             "Use this Shell for tests and redeploy after repair.")
    return first, second, project + " || exit\n" + screen_banner(shell)


def layout(session):
    workspaces = session.api("workspace", "list")["workspaces"]
    if len(workspaces) != 1:
        raise Refused("Expected one Lab 2 workspace; custom layout preserved")
    workspace_id = workspaces[0]["workspace_id"]
    tabs = sorted(session.api("tab", "list", "--workspace", workspace_id)["tabs"],
                  key=lambda tab: tab["number"])
    panes = session.api("pane", "list", "--workspace", workspace_id)["panes"]
    if len(tabs) not in (1, 3) or len(panes) != len(tabs):
        raise Refused("Expected three single-pane tabs; partial layout preserved")
    ordered = []
    for tab in tabs:
        matches = [pane for pane in panes if pane["tab_id"] == tab["tab_id"]]
        if len(matches) != 1 or tab.get("pane_count") != 1:
            raise Refused("Conflicting Lab 2 panes; preserved")
        ordered.append(matches[0])
    return workspace_id, ordered


def first_state(info, run):
    if shared.process_state(info, "pi") in ("app", "shell"):
        state = shared.process_state(info, "pi")
        if run == 2 and state == "app":
            # A lone plain Pi cannot establish that the protected launcher was
            # used. Refuse rather than infer sandbox status from a process name.
            return "conflict"
        return state
    processes = info.get("foreground_processes", [])
    if (run == 2 and len(processes) == 2
            and {process.get("name") for process in processes} == {"nono", "pi"}
            and all(type(process.get("pid")) is int and process["pid"] > 0 for process in processes)
            and len({process["pid"] for process in processes}) == 2):
        return "protected-metadata"
    parent = nono_foreground(info) if run == 2 else None
    children = info.get("supervisor_children", [])
    if parent is not None and isinstance(children, list) and len(children) == 1:
        child = children[0]
        if (isinstance(child, dict) and child.get("name") == "pi"
                and type(child.get("pid")) is int and child["pid"] > 0
                and type(child.get("ppid")) is int and child["ppid"] == parent["pid"]
                and child["pid"] not in (parent["pid"], info["shell_pid"])):
            # UI topology recognition only, not proof of policy or enforcement.
            return "protected-metadata"
    return "conflict"


def states(session, panes, run):
    if len(panes) != 3:
        return []
    return [first_state(session.process_info(panes[0]), run),
            shared.process_state(session.process_info(panes[1]), "fresh"),
            shared.process_state(session.process_info(panes[2]), "not-an-app")]


def prepare_session(session, cold, run, run_id, app_port=18080):
    profile.validate_run(run, run_id)
    empty = not session.api("workspace", "list")["workspaces"]
    if empty:
        session.api("workspace", "create", "--cwd", profile.PROJECT,
                    "--label", "Lab 2", "--no-focus")
        cold = True
    workspace_id, panes = layout(session)
    if not empty and len(panes) != 3:
        raise Refused("Existing Lab 2 layout is partial; preserved without repair")
    if not cold:
        current = states(session, panes, run)
        expected_first = ("app",) if run == 1 else ("shell", "protected-metadata")
        if len(current) != 3 or current[0] not in expected_first or current[1:] != ["app", "shell"]:
            raise Refused("Live Lab 2 session differs; no relaunch or layout repair")
        return {"mode": "reattach", "apps_started": 0}
    for pane in panes:
        if empty:
            shared.wait_shell(session, pane)
        elif shared.process_state(session.process_info(pane), "not-an-app") != "shell":
            raise Refused("Cold restored layout is not plain Bash; preserved")
    if len(panes) == 1:
        for label in ("Editor", "Shell"):
            session.api("tab", "create", "--workspace", workspace_id,
                        "--cwd", profile.PROJECT, "--label", label, "--no-focus")
        _, panes = layout(session)
        for pane in panes[1:]:
            shared.wait_shell(session, pane)
    labels = ("Agent", "Editor", "Shell")
    for pane, command, label in zip(panes, commands(run, run_id, app_port), labels):
        session.api("tab", "rename", pane["tab_id"], label)
        session.api("pane", "run", pane["pane_id"], command)
    deadline = time.monotonic() + 15
    expected = ["app" if run == 1 else "shell", "app", "shell"]
    while states(session, panes, run) != expected:
        if time.monotonic() >= deadline:
            raise Refused("Lab 2 startup incomplete; partial state retained, no retry")
        time.sleep(0.2)
    return {"mode": "started", "apps_started": 2 if run == 1 else 1}


def prepare_ui(docker, container_id, run, run_id, app_port=18080):
    profile.validate_run(run, run_id)
    session = Session(docker, container_id)
    status = session.status()
    cold = not status["running"]
    if cold:
        docker.run(["exec", "--detach", "--workdir", profile.PROJECT, container_id, "herdr", "server"])
        deadline = time.monotonic() + 5
        while not session.status()["running"]:
            if time.monotonic() >= deadline:
                raise Refused("Herdr startup incomplete; state retained")
            time.sleep(0.1)
        status = session.status()
    if not status.get("compatible") or status.get("version") != "0.9.3":
        raise Refused("Matching Herdr 0.9.3 required; no upgrades or resets")
    result = prepare_session(session, cold, run, run_id, app_port)
    if result["mode"] == "started":
        print(browser_box(app_port), flush=True)
    return result

"""Lab 2 runtime paths, launch commands and environment; no source emitters.

Pi state is separate from Herdr HOME/control sockets. The supervisor credential
is outside HOME. Learners must remove the starter's whole-HOME grant before any
profiled launch to exclude policy, supervisor state and unrelated diagnostics.
These are candidate Pi/proxy settings, not native Pi qualification.
"""

import re

HOME = "/home/lab-user"
PROJECT = HOME + "/workshop/lab2"
AGENT_HOME = HOME + "/agent-state"
POLICY = HOME + "/policy/nono.json"
GUIDE = PROJECT + "/README.md"
LAUNCH = "/opt/secagent/lab2/lab2_launch.py"
CONTROLS = "/opt/secagent/lab2/lab2_controls.py"
FLAG_NAME = "WORKSHOP_PROTECT_ME"
FLAG_VALUE = "protect_me_from_the_brain"
DEMO_FLAG = HOME + "/.local/share/line-dev-conf/flag.txt"
SECRET = "/run/lab2-secrets/ollama-key"
PROXY_PORT = 18082
CREDENTIAL_ROUTE = "ollama_api_key"
PROXY_BASE = f"http://127.0.0.1:{PROXY_PORT}/{CREDENTIAL_ROUTE}/v1"
PATH = "/opt/secagent/runtime/bin:/usr/local/bin:/usr/bin:/bin"


def validate_run(run, run_id):
    if (type(run) is not int or run not in (1, 2) or not isinstance(run_id, str)
            or not re.fullmatch(r"[a-f0-9]{32}", run_id)):
        raise ValueError("Explicit Lab 2 run and run identity required")


def launch_command(run, run_id):
    validate_run(run, run_id)
    if run == 2:
        command = protected_command()
        return " ".join(command[:4]) + " \\\n  " + " ".join(command[4:])
    return f"python3 -I -B {LAUNCH} \\\n  --run {run} --run-id {run_id}"


def control_command(run, run_id):
    validate_run(run, run_id)
    return f"python3 -I -B {CONTROLS} \\\n  --run {run} --run-id {run_id}"


def environment(run_id):
    """Entire public Pi/child environment; never copy os.environ/host values.

    The protected launcher separates supervisor HOME/TMPDIR from child paths;
    they are outside child grants only after the learner narrows the starter.
    Policy set_vars keeps the separate child HOME/TMPDIR. Broad launcher adds
    the selected key. Protected launcher supplies
    no upstream key; nono injects a session/phantom OLLAMA_API_KEY into the child.
    TERM is deliberate, not inherited terminal/private configuration.
    The synthetic flag reaches the supervisor as an inherited input to nono's
    filter, not a policy set_vars entry that would defeat the learner's deny.
    """
    validate_run(2, run_id)
    return {"PATH": PATH, "HOME": AGENT_HOME, "PI_CODING_AGENT_DIR": AGENT_HOME + "/.pi/agent",
            "TMPDIR": AGENT_HOME + "/tmp", "LANG": "C", "LC_ALL": "C", "TERM": "xterm-256color",
            "SHELL": "/bin/bash", "EDITOR": "fresh", "VISUAL": "fresh",
            "PYTHONDONTWRITEBYTECODE": "1", "WORKSHOP_RUN_ID": run_id,
            FLAG_NAME: FLAG_VALUE,
            # Only the local reverse-proxy origin bypasses HTTP proxy routing;
            # direct sockets remain restricted by nono. App/collector do NOT.
            "NO_PROXY": "127.0.0.1,localhost"}


def protected_command():
    """Fixed proxy port aligns models.json with pinned SandboxArgs.proxy_port."""
    return ["nono", "run", "--profile", POLICY, "--proxy-port", str(PROXY_PORT), "--", "pi"]

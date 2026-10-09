"""Shared guest prerequisites plus an explicit live Pi/provider/log probe.

check_lab.sh streams trusted validators and configuration as tar archives on
stdin. Load them in memory, never extract or run installer entry points. The
privileged invocation inspects tooling/runtime without repair or startup.

After prerequisites pass, the unprivileged `pi` invocation uses setup's exact
operator/profile/auth validators, then one explicit model turn and fresh log
verification. It reads the saved guest key locally, leaves a private activity
log and uses provider quota (possibly billable). No credential content, raw Pi
output or log bodies are printed or transported to the host. The prompt uses
no participant files/tools and the temporary working directory is removed.

The separate `container` entry is offline-only: read-only private profile/auth
validation and sealed Node/npm/Pi version probes, with no installer or model call.
Its host adapter enforces network-none and a read-only preparation HOME mount.
The explicit `container-live` entry first runs those prerequisites, then one
existing live probe under a private umask. Its adapter enables networking and
private scratch/HOME writes; cancellation is not rollback or remote-stop proof.
"""

import io
import json
import os
from pathlib import Path
import platform
import pwd
import re
import stat
import subprocess
import sys
import tarfile
import tempfile
import types
import uuid


class LiveCheckError(RuntimeError):
    """A live turn or its log failed after all prerequisite/profile/catalog guards."""


PROFILE_MODULES = {"scripts/prepare_guest.py": "prepare_guest",
                   "scripts/setup_guest_pi.py": "setup_guest_pi",
                   "scripts/setup_guest_auth.py": "setup_guest_auth"}
PROFILE_TEMPLATES = ("agents/pi/settings.json", "agents/pi/models.json",
                     "agents/pi/extensions/observer.ts", "scripts/runtime_config.json")


def load_validators(stream):
    """Load trusted validators/config in memory, never installer entry points."""
    modules = []
    with tarfile.open(fileobj=io.BytesIO(stream.read())) as archive:
        for name in ("prepare_guest", "prepare_guest_docker", "setup_guest_pi"):
            source = archive.extractfile(name + ".py")
            if source is None:
                raise RuntimeError(f"Missing validator source: {name}")
            module = types.ModuleType(name)
            sys.modules[name] = module
            exec(compile(source.read(), name + ".py", "exec"), module.__dict__)
            modules.append(module)
        source = archive.extractfile("runtime_config.json")
        if source is None:
            raise RuntimeError("Missing runtime configuration")
        config = modules.pop().load_runtime_config(source.read())
    return (*modules, config)


def load_profile_controllers(stream):
    """Load the unprivileged profile/auth validators and template bytes in memory.

    The archive comes from the trusted local repository, so the exact-member
    manifest check is correctness/defense-in-depth, not an exploit boundary:
    exactly one nonempty regular member per expected name, nothing else, all
    validated before any source executes.
    """
    expected = dict(PROFILE_MODULES, **{name: name for name in PROFILE_TEMPLATES})
    members = {}
    payload = stream.read(16 * 1024 * 1024 + 1)
    if len(payload) > 16 * 1024 * 1024:
        raise RuntimeError("Checker archive exceeds its public-input limit")
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:") as archive:
        for member in archive.getmembers():
            if member.name not in expected:
                raise RuntimeError(f"Unexpected checker archive member: {member.name}")
            if member.name in members:
                raise RuntimeError(f"Duplicate checker archive member: {member.name}")
            if not member.isfile() or not 0 < member.size <= 2 * 1024 * 1024:
                raise RuntimeError(
                    f"Missing, empty or non-regular checker member: {member.name}")
            members[member.name] = archive.extractfile(member).read()
    if set(members) != set(expected):
        raise RuntimeError("Checker archive is missing expected sources")
    controllers = {}
    for name, alias in PROFILE_MODULES.items():
        module = types.ModuleType(alias)
        sys.modules[alias] = module
        try:
            exec(compile(members[name], name + ".py", "exec"), module.__dict__)
        except SyntaxError as error:
            raise RuntimeError(f"Corrupt checker source {name}: {error}") from None
        controllers[name] = module
    templates = {name: members[name] for name in PROFILE_TEMPLATES}
    return controllers, templates


def check(guest, docker, config):
    architecture = guest.check_guest()
    # These version/info commands need no personal HOME/config. /proc/self
    # exists but cannot acquire configuration files, even when running as root.
    environment = {
        "HOME": "/proc/self", "DOCKER_CONFIG": "/proc/self",
        "PATH": f"{guest.RUNTIME / 'bin'}:/usr/sbin:/usr/bin:/sbin:/bin",
        "LC_ALL": "C", "PI_OFFLINE": "1", "PI_TELEMETRY": "0",
    }
    for name in docker.CONFLICTS:
        if docker.package_version(name, environment) is not None:
            raise RuntimeError(f"Conflicting {name}; review without automatic migration")
    for name, expected in docker.PACKAGES.items():
        actual = docker.package_version(name, environment)
        if actual != expected:
            raise RuntimeError(f"{name}: expected {expected}, found {actual or 'not installed'}")
    docker.verify_docker(environment)
    print("[PASS] Pinned Docker/Compose and active rootful guest Engine.", flush=True)

    for name in ("ca-certificates", "git"):
        if docker.package_version(name, environment) is None:
            raise RuntimeError(f"Missing guest package: {name}")
    guest.require_root_owned(guest.INSTALL_ROOT)
    guest.require_root_owned(guest.RUNTIME)
    guest.verify_runtime_manifest(guest.RUNTIME, architecture, config["pi"])
    guest.verify_runtime(guest.RUNTIME, environment, Path("/"), config["pi"])
    print("[PASS] Pinned, root-owned Node/npm/pi runtime and required guest packages.", flush=True)


def check_pi(pi, auth, templates, *, container=False):
    """Unprivileged read-only checks using setup's profile compatibility rules."""
    if platform.system() != "Linux" or (not container and platform.node() != "lima-secagent-lab"):
        raise RuntimeError(
            "Run ./lab.sh check from the host; guest Pi checks run only inside secagent-lab")
    if os.geteuid() == 0:
        raise RuntimeError(
            "Guest Pi checks must run as the ordinary guest operator, not sudo/root")
    # Container mode keeps and validates the fixed HOME; legacy Lima resolves it
    # from passwd. Neither mode creates or completes a missing profile.
    pi.load_runtime_config(templates["scripts/runtime_config.json"])
    expected_settings = pi.render_settings(templates["agents/pi/settings.json"])
    uid = os.geteuid()
    home = Path(pwd.getpwuid(uid).pw_dir)
    if not home.is_absolute():
        raise ValueError(f"Guest home must be absolute: {home}")
    if container:
        auth.container_credential_path()
        pi.validate_container_home(home, uid, os.getegid())
    else:
        os.environ["HOME"] = str(home)
    profile = home / ".pi/agent"

    # Setup's reuse helpers allow absence; check requires the installed state.
    # directory() and matching_file() raise on unsafe/incompatible resources,
    # exactly as setup would refuse to create or replace them. The operator home
    # and session storage use setup's home=True writability rule, not stricter
    # privacy rules that a normal home directory cannot satisfy.
    if not pi.directory(home, uid, home=True):
        raise RuntimeError(f"Guest Pi resource is missing: {home}; run ./lab.sh setup")
    for path in (home / ".pi", profile, profile / "extensions", home / "pi-log"):
        if not pi.directory(path, uid):
            raise RuntimeError(f"Guest Pi resource is missing: {path}; run ./lab.sh setup")
    for path, expected in ((profile / "settings.json", expected_settings),
                           (profile / "models.json", templates["agents/pi/models.json"]),
                           (profile / "extensions/observer.ts",
                            templates["agents/pi/extensions/observer.ts"])):
        if not pi.matching_file(path, expected, uid):
            raise RuntimeError(f"Guest Pi resource is missing: {path}; "
                               "run ./lab.sh setup")

    # Same inventory as setup, including Pi's runtime-created private catalog cache.
    extras = {item.name for item in profile.iterdir()} - {
        "settings.json", "models.json", "extensions", "auth.json", "sessions", "models-store.json"}
    if extras:
        raise RuntimeError("Existing Pi profile has unexpected resources; preserve "
                           f"them and review before any change: {sorted(extras)}")
    extras = {item.name for item in (profile / "extensions").iterdir()} - {"observer.ts"}
    if extras:
        raise RuntimeError("Existing Pi extensions have unexpected resources; preserve "
                           f"them and review before any change: {sorted(extras)}")

    # Session storage appears with the first Pi run: absence is expected and
    # accepted, but a present (or symlinked) directory must still be private,
    # operator-owned and real; directory() raises on anything unsafe.
    pi.directory(profile / "sessions", uid, home=True)
    pi.validate_models_store(profile, uid)

    # credential_path()/credential_exists() run against the real operator HOME
    # and apply setup's strict private-file rules. The credential is read and
    # parsed only inside the guest; it is never printed or sent to the host.
    credential = auth.credential_path()
    if container:
        auth.check_container_catalog(credential)
    if not auth.credential_exists(credential):
        raise RuntimeError("Guest Pi credential is missing; "
                           "run ./lab.sh setup to enter it interactively")
    print("[PASS] Guest Pi profile, observer extension, log directory and inventory "
          "are compatible with workshop requirements.", flush=True)
    print("[PASS] Guest Pi saved Ollama Cloud credential configuration is present with "
          "the strict expected structure; its contents are never printed or sent "
          "to the host.")
    print("[INFO] This verifies configured files, not observer execution, log "
          "writability, token validity or lab readiness.", flush=True)
    return home, json.loads(expected_settings)["defaultModel"]


def check_container(controllers, templates):
    """Read-only common Pi readiness, never provisioning or a provider request."""
    runtime = controllers["scripts/prepare_guest.py"]
    pi = controllers["scripts/setup_guest_pi.py"]
    auth = controllers["scripts/setup_guest_auth.py"]
    check_pi(pi, auth, templates, container=True)
    config = pi.load_runtime_config(templates["scripts/runtime_config.json"])
    architecture = platform.machine()
    if architecture not in runtime.NODE_IMAGES:
        raise RuntimeError("Unsupported runtime architecture")
    runtime.require_root_owned(runtime.INSTALL_ROOT)
    runtime.require_root_owned(runtime.RUNTIME)
    runtime.verify_runtime_manifest(runtime.RUNTIME, architecture, config["pi"])
    # Version probes have no participant HOME/config or inherited credentials.
    # The host additionally enforces network-none and a read-only HOME mount.
    environment = {
        "HOME": "/proc/self", "PATH": f"{runtime.RUNTIME / 'bin'}:/usr/bin:/bin",
        "LC_ALL": "C", "PI_OFFLINE": "1", "PI_TELEMETRY": "0",
        # npm rejects loading one path as both user and global configuration.
        "npm_config_userconfig": "/dev/null",
        "npm_config_globalconfig": "/proc/self/secagent-global-npmrc",
        "npm_config_cache": "/proc/self", "npm_config_update_notifier": "false",
    }
    runtime.verify_runtime(runtime.RUNTIME, environment, Path("/tmp"), config["pi"])
    print("[PASS] Offline Node/npm/Pi versions and private profile checked.", flush=True)


def main_container():
    """Trusted public bundle on stdin; never return private data or raw errors."""
    try:
        controllers, templates = load_profile_controllers(sys.stdin.buffer)
        check_container(controllers, templates)
    except (OSError, RuntimeError, ValueError, KeyError,
            subprocess.SubprocessError, tarfile.TarError):
        print("[FAIL] Offline preparation check failed; existing state preserved.", file=sys.stderr)
        return 1
    return 0


def main_container_live():
    """One explicit container request after offline guards; never prompt/retry."""
    previous_umask = os.umask(0o077)
    try:
        controllers, templates = load_profile_controllers(sys.stdin.buffer)
        check_container(controllers, templates)
        try:
            check_live(controllers["scripts/prepare_guest.py"].RUNTIME,
                       controllers["scripts/setup_guest_pi.py"],
                       controllers["scripts/setup_guest_auth.py"], templates, container=True)
        except LiveCheckError:
            print("[FAIL] Live request/log verification failed; no automatic retry.", file=sys.stderr)
            return 3
    except (OSError, RuntimeError, ValueError, KeyError,
            subprocess.SubprocessError, tarfile.TarError):
        print("[FAIL] Live check prerequisite/transport failed; state preserved.", file=sys.stderr)
        return 1
    finally:
        os.umask(previous_umask)
    return 0


def json_records(text, context):
    """Strict LF-framed objects; never echo potentially private malformed data."""
    try:
        if not text.endswith("\n"):
            raise ValueError("Incomplete record")
        records = [json.loads(line) for line in text.split("\n")[:-1]]
        if not records or any(not isinstance(record, dict)
                              or not isinstance(record.get("type"), str)
                              for record in records):
            raise ValueError("Expected objects")
    except (ValueError, TypeError):
        raise RuntimeError(f"Cannot verify {context}: invalid or incomplete JSONL") from None
    return records


def verify_activity_log(directory, before, session_id, model, prompt):
    """Read only this run's fresh, private observer file, never previous logs."""
    failure = (
        "Pi responded, but its fresh activity log is missing or incomplete; "
        "check ~/pi-log permissions, free space and the observer extension."
    )
    try:
        created = [path for path in directory.iterdir() if path.name not in before]
        if len(created) != 1:
            raise ValueError("Expected one fresh log")
        path = created[0]
        info = path.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or path.suffix != ".jsonl"
                or str(uuid.UUID(path.stem)) != path.stem):
            raise ValueError("Unsafe log")
        records = json_records(path.read_text(encoding="utf-8"), "activity log")
        expected = ["session_start", "request_prepared", "http_response",
                    "assistant_finished", "session_shutdown"]
        lifecycle = ["session_start", "agent_start", "turn_start", "request_prepared",
                     "http_response", "assistant_finished", "turn_end", "agent_end",
                     "agent_settled", "session_shutdown"]
        types = [record["type"] for record in records]
        if any(kind not in lifecycle for kind in types):
            raise ValueError("Unexpected activity in tool-free probe")
        positions = [lifecycle.index(kind) for kind in types]
        evidence = [record for record in records if record["type"] in expected]
        if (positions != sorted(set(positions))
                or [record["type"] for record in evidence] != expected):
            raise ValueError("Incomplete or out-of-order lifecycle")
        # Added agent/turn events are not extra requests. Correlate their scope
        # and the required milestones without renumbering the original records.
        if any(kind not in expected for kind in types):
            scopes = {
                "session_start": (None, None, None), "agent_start": (1, None, None),
                "turn_start": (1, 0, None), "request_prepared": (1, 0, 1),
                "http_response": (1, 0, 1), "assistant_finished": (1, 0, 1),
                "turn_end": (1, 0, 1), "agent_end": (1, None, None),
                "agent_settled": (1, None, None), "session_shutdown": (None, None, None),
            }
            for record in records:
                actual = tuple(record.get(key) for key in ("runId", "turnIndex", "requestId"))
                desired = scopes[record["type"]]
                if any(type(a) is not type(b) or a != b for a, b in zip(actual, desired)):
                    raise ValueError("Wrong agent/turn/request scope")
                if record["type"] == "turn_end" and record.get("outcome") != "completed":
                    raise ValueError("Turn did not complete")
        for sequence, record in enumerate(records, 1):
            if (record.get("schema") != 1 or record.get("sequence") != sequence
                    or record.get("sessionId") != session_id
                    or record.get("observerId") != path.stem):
                raise ValueError("Wrong run")
        start, request, response, finish, shutdown = evidence
        payload = request.get("payload")
        if (start.get("provider") != "ollama" or start.get("model") != model
                or start.get("activeTools") != [] or not isinstance(payload, dict)
                or payload.get("model") != model or payload.get("tools") not in (None, [])
                or payload.get("reasoning_effort") != "medium"
                or prompt not in json.dumps(payload.get("messages"), ensure_ascii=False)
                or any(record.get("requestId") != 1 for record in (request, response, finish))
                or type(response.get("status")) is not int
                or not 200 <= response["status"] < 300
                or finish.get("stopReason") != "stop"
                or shutdown.get("unfinishedToolCallIds") != []):
            raise ValueError("Missing request/response/completion evidence")
    except (OSError, ValueError, RuntimeError):
        raise RuntimeError(failure) from None
    return path


def check_live(runtime, pi, auth, templates, *, container=False):
    """One explicit guest model turn plus observer proof; caller verifies runtime.

    Reuse setup's operator/profile/auth guards first. Run only the installed
    observer in an empty disposable workdir with no tools or project context.
    Keep credentials, raw CLI output and log bodies inside the guest. Fixed
    profile settings disable retries/compaction/cache warming; no settings are
    changed here. PI_OFFLINE disables automatic catalog/update networking, not
    this explicitly requested provider call. JSON mode can exit zero on a model
    error, so require an authoritative completed reply AND agent_settled.
    Probe only the configured default, never the alternative as a fallback.
    The fresh request log must show thinking enabled (medium maps to on).
    """
    home, model = check_pi(pi, auth, templates, container=container)
    profile = home / ".pi/agent"
    environment = {
        "HOME": str(home), "PI_CODING_AGENT_DIR": str(profile),
        "PATH": f"{runtime / 'bin'}:/usr/bin:/bin", "LC_ALL": "C.UTF-8",
        "PI_OFFLINE": "1", "PI_SKIP_VERSION_CHECK": "1", "PI_TELEMETRY": "0",
        "NODE_DISABLE_COMPILE_CACHE": "1", "TERM": "dumb", "NO_COLOR": "1",
    }
    options = [str(runtime / "bin/pi"), "--no-tools", "--no-session",
               "--no-approve", "--no-context-files", "--no-skills",
               "--no-prompt-templates", "--no-themes", "--no-extensions",
               "--system-prompt", "You are checking workshop provider connectivity."]
    directory = home / "pi-log"
    before = {path.name for path in directory.iterdir()}
    prompt = f"Reply briefly with OK. Preparation check {uuid.uuid4()}. Do not use tools."
    with tempfile.TemporaryDirectory(prefix="secagent-live-check-") as work:
        def run(arguments, timeout):
            try:
                # communicate() drains both pipes continuously. Never forward
                # stderr/errorMessage: provider diagnostics may contain secrets.
                return subprocess.run(arguments, env=environment, cwd=work,
                                      stdin=subprocess.DEVNULL, capture_output=True,
                                      text=True, encoding="utf-8", errors="replace",
                                      timeout=timeout)
            except subprocess.TimeoutExpired:
                raise RuntimeError("Pi live check timed out; check connectivity and provider availability.") from None

        # Pi permits fuzzy --model matches/custom fallback IDs. Its offline
        # table starts with provider and exact ID: refuse missing exact rows
        # BEFORE any model request, rather than probe a different/paid model.
        catalogue = run([*options, "--list-models", model], 30)
        if catalogue.returncode or not any(
                line.split()[:2] == ["ollama", model]
                for line in catalogue.stdout.split("\n")):
            raise RuntimeError("Configured Ollama Cloud model is absent from the installed Pi catalog; "
                               "review agents/pi/settings.json and agents/pi/models.json. "
                               "No model request was sent.")
        try:
            result = run([*options, "--mode", "json", "--provider", "ollama",
                          "--model", "ollama/" + model, "--thinking", "medium",
                          "--extension", str(profile / "extensions/observer.ts"),
                          "--", prompt], 45)
            return verify_live_result(result, directory, before, model, prompt)
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
            raise LiveCheckError(str(error)) from None


def classify_provider_error(message):
    """Classify known SDK text formats without exposing text or proving delivery."""
    if not isinstance(message, str):
        return "unclassified SDK error"
    # Pi's OpenAI error formatter uses '<status> <body>' or '<status>: <body>'.
    # Only the leading ASCII error status is retained, never a body/header value.
    status = re.match(r"([45][0-9]{2})[ :]", message)
    if status:
        return f"reported HTTP status {status.group(1)}"
    for signature, category in (
            ("Connection error.", "SDK connection error"),
            ("Request timed out.", "SDK timeout"),
            ("Stream ended without finish_reason", "SDK incomplete stream"),
            ("Provider returned an error stop reason", "SDK error finish reason")):
        if message == signature or message.startswith(signature + "\n"):
            return category
    # These SDK messages contain variable provider/model/finish-reason suffixes.
    # Recognize only their fixed prefix; never retain that suffix.
    if message.startswith("No API key for "):
        return "SDK credential unavailable"
    if message.startswith("Provider finish_reason: "):
        return "SDK finish-reason error"
    return "unclassified SDK error"


def verify_live_result(result, directory, before, model, prompt):
    """Require a completed exact-model response and fresh correlated log evidence."""
    events = json_records(result.stdout, "Pi event stream")
    replies = [(index, event["message"]) for index, event in enumerate(events)
               if event.get("type") == "message_end"
               and isinstance(event.get("message"), dict)
               and event["message"].get("role") == "assistant"]
    settled = [index for index, event in enumerate(events) if event.get("type") == "agent_settled"]
    failure = ("Ollama Cloud request did not complete successfully; check connectivity, "
               "your API key/account, configured model availability and quota. "
               "Raw provider diagnostics are not displayed.")
    def fail(category):
        # Only fixed labels, counts and the local process status leave the guest.
        # Never interpolate provider fields, stderr, errorMessage or reply text.
        raise RuntimeError(f"{failure} Failure category: {category}.")

    if result.returncode:
        fail(f"Pi exit status {result.returncode}")
    if (events[0].get("type") != "session"
            or not isinstance(events[0].get("id"), str) or not events[0]["id"]):
        fail("missing session header")
    if len(replies) != 1:
        fail(f"assistant completions={len(replies)}")
    if len(settled) != 1:
        fail(f"settled events={len(settled)}")
    if settled[0] <= replies[0][0]:
        fail("settled before assistant completion")
    if any(event["type"].startswith("tool_execution_") for event in events):
        fail("unexpected tool execution")
    reply = replies[0][1]
    reason = reply.get("stopReason")
    if reason == "error":
        category = classify_provider_error(reply.get("errorMessage"))
        fail(f"assistant stop reason=error. SDK category: {category}")
    if reason != "stop":
        # A provider-controlled string (or malformed value) is never echoed.
        known = reason if isinstance(reason, str) and reason in (
            "aborted", "length", "toolUse") else "unrecognized"
        fail(f"assistant stop reason={known}")
    if reply.get("provider") != "ollama":
        fail("reply provider mismatch")
    if reply.get("model") != model:
        fail("reply model mismatch")
    content = reply.get("content")
    if not isinstance(content, list):
        fail("invalid assistant content")
    if any(isinstance(block, dict) and block.get("type") == "toolCall" for block in content):
        fail("unexpected assistant tool call")
    if not any(isinstance(block, dict) and block.get("type") == "text"
               and isinstance(block.get("text"), str) and block["text"].strip()
               for block in content):
        fail("no nonempty assistant text")
    path = verify_activity_log(directory, before, events[0]["id"], model, prompt)
    print("[PASS] Live Ollama Cloud response and fresh activity log verified.", flush=True)
    return path


def check_report(error, context):
    print(f"[FAIL] {context}: {error}", file=sys.stderr)
    if isinstance(error, subprocess.CalledProcessError) and error.stderr:
        print(error.stderr.strip(), file=sys.stderr)


TOOLING_GUIDANCE = (
    "For missing tools, run ./lab.sh setup from the macOS host.\n"
    "For incompatible OS/configuration/versions or cloud-init errors,\n"
    "review the reported problem first; setup will not migrate/replace them.\n"
    "Inspect cloud-init with: limactl shell secagent-lab -- "
    "cloud-init status --long\n"
    "Inspect Docker with: limactl shell secagent-lab -- "
    "sudo -n -k systemctl status docker --no-pager"
)

PI_GUIDANCE = (
    "For missing tools or resources, run ./lab.sh setup from the macOS host.\n"
    "For changed, unexpected or unsafe Pi profile, logs or auth files, review\n"
    "the reported problem first; setup preserves them and never repairs,\n"
    "replaces or re-enters credentials without the participant explicitly\n"
    "running setup. No credential content is transported or printed by checks."
)


def main():
    guest = None
    try:
        guest, docker, config = load_validators(sys.stdin.buffer)
        check(guest, docker, config)
    except (OSError, RuntimeError, ValueError, KeyError,
            subprocess.SubprocessError, tarfile.TarError) as error:
        check_report(error, "Guest prerequisite check")
        # A known runtime mismatch already supplies its complete recovery path.
        if guest is None or not isinstance(error, guest.RuntimeMismatchError):
            print(TOOLING_GUIDANCE, file=sys.stderr)
        return 1
    return 0


def main_pi():
    """Unprivileged entry: profile/auth validators and templates stream on stdin."""
    try:
        controllers, templates = load_profile_controllers(sys.stdin.buffer)
        check_live(controllers["scripts/prepare_guest.py"].RUNTIME,
                   controllers["scripts/setup_guest_pi.py"],
                   controllers["scripts/setup_guest_auth.py"], templates)
    except (OSError, RuntimeError, ValueError, KeyError,
            subprocess.SubprocessError, tarfile.TarError) as error:
        print(f"[FAIL] Guest Pi live check: {error}", file=sys.stderr)
        print(PI_GUIDANCE, file=sys.stderr)
        return 3 if isinstance(error, LiveCheckError) else 1
    return 0


if __name__ == "__main__":
    if sys.argv[1:] == ["container-live"]:
        sys.exit(main_container_live())
    if sys.argv[1:] == ["container"]:
        sys.exit(main_container())
    if sys.argv[1:] == ["pi"]:
        sys.exit(main_pi())
    if sys.argv[1:]:
        print("Usage: python3 -I -B check_guest.py [pi|container|container-live]", file=sys.stderr)
        sys.exit(2)
    sys.exit(main())

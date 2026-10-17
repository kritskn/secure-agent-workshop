"""Lab 3 native effects, bounded private evidence, revocation and verified STOP.

No discovery, credential access or execution on import. The participant caller
must first select/lock one private attempt. A thread watchdog cannot survive host
controller death; local cutoff/provider absence do not prove cloud cancellation.
"""

import contextlib
import http.client
import json
import os
import re
import select
import subprocess
import threading
import time
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener

import lab3_enroll as enrollment
import lab3_evidence as evidence
import lab3_guards as guards
import lab3_resources as resources
import lab_tools as tools
from lab_credential import PREPARATION_VOLUME, validate_volume

FAILURES = (RuntimeError, OSError, ValueError, TypeError, LookupError, subprocess.SubprocessError)


class Native:
    def __init__(self, docker, state, *, clock=time.monotonic):
        self.docker, self.state, self.clock = docker, state, clock
        self.record = state.data["resources"]
        if self.record["endpoint"] != docker.endpoint:
            raise ValueError("Selected engine differs; preserve this attempt")
        self.http = build_opener(ProxyHandler({}))
        self.stop_lock = state.mutex
        self.stop_requested = threading.Event()
        self.stopped = False

    def run(self, args, **options):
        try:
            return self.docker.run(args, **options)
        except FAILURES:
            raise RuntimeError("Lab 3 native operation failed; private output withheld, no automatic retry") from None

    def inspect(self, role, *, absence=False):
        return resources.inspect_owned(self, self.record, role, absence=absence)

    def operator(self, args, *, enrollment=False, source=None):
        if not self.inspect("gateway")["State"]["Running"]:
            raise RuntimeError("Gateway is stopped; preserve attempt and use explicit STOP recovery")
        return resources.operator(self.record, args, enrollment=enrollment, source=source)

    def begin_operator(self, command, *, cleanup=False):
        with self.stop_lock:
            if self.stop_requested.is_set() and not cleanup:
                raise RuntimeError("STOP requested; no new operator enrollment, activation or task")
            name = command[command.index("--name") + 1]
            self.state.data.setdefault("operators_pending", {})[name] = True
            self.state.save()

    def finish_operator(self, command):
        with self.stop_lock:
            name = command[command.index("--name") + 1]
            self.state.data["operators_pending"].pop(name)
            self.state.save()

    def start_container(self, role):
        with self.stop_lock:
            if self.stop_requested.is_set():
                raise RuntimeError("STOP requested; selected resources will not be restarted")
            obj = self.inspect(role)
            if obj["State"]["Running"] or obj["State"].get("Status") not in ("created", "exited"):
                raise ValueError("Selected resource is not stopped; no implicit restart")
            self.run(["start", obj["Id"]], timeout=15)

    def cli(self, *args, timeout=40, cleanup=False):
        command = self.operator(args)
        self.begin_operator(command, cleanup=cleanup)
        output = self.run(command, timeout=timeout)
        self.finish_operator(command)
        return output

    def gateway_ready(self):
        """Acknowledge a finished negative query, not a lost operator outcome."""
        source = ("import subprocess\n"
                  "try:\n"
                  " result = subprocess.run(['/usr/local/bin/openshell', 'sandbox', 'list'], "
                  "stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)\n"
                  " ready = result.returncode == 0\n"
                  "except subprocess.TimeoutExpired:\n"
                  " ready = False  # subprocess.run has killed and waited for this read-only query.\n"
                  "print('READY' if ready else 'NOT_READY')\n")
        command = self.operator([], source=source)
        self.begin_operator(command)
        acknowledgement = self.run(command, timeout=5).strip()
        if acknowledgement not in ("READY", "NOT_READY"):
            raise RuntimeError("Gateway readiness acknowledgement missing; preserve pending operator and use STOP")
        self.finish_operator(command)
        return acknowledgement == "READY"

    def observation(self):
        obj = self.inspect("workload")
        source = tools.source_bytes("scripts/lab3_observation.py").decode()
        output = self.run(["exec", "--user", "1000:1000", "--workdir", "/", obj["Id"],
                           "python3", "-I", "-B", "-c", source], timeout=5)
        return json.loads(output)

    def task_inputs(self):
        """Read the actual installed public task/facts and walkthrough policy."""
        workload = self.inspect("workload")
        code = ("import json;from pathlib import Path;out={};"
                "\nfor title,name in [('PREPARED TASK','job.txt'),('SUPPLIER FACTS','supplier.txt')]:"
                "\n data=(Path('/http')/name).read_bytes()"
                "\n if len(data)>65536:raise ValueError('Public task bound exceeded')"
                "\n out[title]=data.decode()"
                "\nprint(json.dumps(out))")
        result = json.loads(self.run(["exec", "--user", "1000:1000", workload["Id"],
                                     "python3", "-I", "-B", "-c", code], timeout=5))
        operator_ui = self.inspect("ui")
        code = ("from pathlib import Path;p=Path('/home/lab-user/workshop/lab3/openshell/policy.yaml');"
                "data=p.read_bytes();"
                "\nif len(data)>65536:raise ValueError('Public policy bound exceeded')"
                "\nprint(data.decode(),end='')")
        result["POLICY WALKTHROUGH — NOT AN ENFORCEMENT RECEIPT"] = self.run(
            ["exec", "--user", "1000:1000", operator_ui["Id"], "python3", "-I", "-B", "-c", code], timeout=5)
        result["PREPARED TASK"] = result["PREPARED TASK"].replace("@SERVICE_IP@", self.record["service_ip"])
        return result

    def pages(self, label):
        result = {}
        for stage in ("preview", "live"):
            with self.http.open(f"http://127.0.0.1:{self.record['viewer_port']}/protected/{stage}.html", timeout=2) as response:
                data = response.read(131073)
                if response.status != 200 or len(data) > 131072:
                    raise ValueError("Unexpected site response; preserve captured evidence")
            self.state.write(label + "-" + stage + ".html", data)
            result[stage] = data
        return result

    def native_logs(self, name):
        logs = self.cli("logs", self.record["sandbox"], "-n", "1000", timeout=10, cleanup=True)
        self.state.write(name, logs.encode())
        return evidence.publication_events(logs, self.record["service_ip"])

    def require_provider_free(self, *, timeout=40, cleanup=False):
        if self.state.data.get("operators_pending"):
            raise RuntimeError("Unacknowledged operator call remains; no enrollment or fresh startup")
        if self.cli("provider", "list", "--names", timeout=timeout, cleanup=cleanup).strip():
            self.state.change(provider_conflict=True)
            raise ValueError("Unexpected provider preserved; no adoption, enrollment or cleanup claim")

    def prepare(self):
        if self.record.get("pending") or self.record["stage"] != "ready":
            raise ValueError("Resource preparation incomplete; no START")
        architecture = tools.engine_architecture(self.docker)
        ids = [self.record["images"]["cli"]["id"]]
        ids.extend(value["image"] for value in self.record["containers"].values())
        for image_id in dict.fromkeys(ids):
            obj = resources.one(self.run(["image", "inspect", image_id]))
            if obj["Id"] != image_id or obj["Os"] != "linux" or obj["Architecture"] != architecture:
                raise ValueError("Recorded image differs from selected Linux engine; no task")
        guards.prepared_guard(self, self.record)
        for role in (*resources.OWNED, "workload", "supervisor"):
            if not self.inspect(role)["State"]["Running"]:
                raise ValueError("Prepared resources must be running; no implicit restart")
        workload = self.inspect("workload")
        if any(m.get("Name") in (self.record["name"] + "-state", self.record["name"] + "-site", PREPARATION_VOLUME)
               or m["Destination"] == "/var/run/docker.sock" for m in workload["Mounts"]):
            raise ValueError("Workload has an unexpected trusted mount")
        self.require_provider_free()
        if not self.observation()["fresh"]:
            raise ValueError("Existing workload state; no adoption/replay")
        status = json.loads(self.cli("sandbox", "get", self.record["sandbox"], "--output", "json"))
        if status["phase"] != "Ready":
            raise ValueError("Provider-free sandbox is not ready")
        source = 'import os;print("ABSENT" if "LAB3_OLLAMA_API_KEY" not in os.environ else "PRESENT")'
        output = self.cli("sandbox", "exec", "--name", self.record["sandbox"], "--timeout", "10",
                          "--no-login-shell", "--", "python3", "-B", "-c", source, timeout=15)
        if output.strip() != "ABSENT":
            raise ValueError("Provider-free process boundary required")
        end = self.clock() + 15
        while True:
            try:
                pages = self.pages("before")
                break
            except (URLError, TimeoutError, ConnectionResetError, http.client.RemoteDisconnected):
                if self.clock() >= end:
                    raise RuntimeError("Viewer HTTP readiness deadline exceeded") from None
                time.sleep(0.25)
        # No comparison against today's editable source/image tag. Fresh resource
        # identity and actual before/after observations establish this attempt.
        if self.native_logs("baseline-native.log")["attempted"]:
            raise ValueError("Existing publication attempt; fresh baseline not established")
        return pages

    def enroll_attach(self):
        self.require_provider_free(timeout=10)
        meta = resources.one(self.run(["volume", "inspect", PREPARATION_VOLUME], timeout=10))
        validate_volume(meta, PREPARATION_VOLUME, "preparation-home")
        payload = "import types\nmodules=[]\n"
        for name in ("setup_guest_auth", "lab_credential", "lab2_credentials", "lab3_enroll"):
            source = tools.source_bytes("scripts/" + name + ".py").decode()
            payload += (f"m=types.ModuleType({name!r});m.__file__={'/opt/secagent/' + name + '.py'!r}\n"
                        f"exec(compile({source!r},{name!r},'exec'),m.__dict__)\nmodules.append(m)\n")
        payload += "raise SystemExit(modules[3].enroll(*modules[:3]))\n"
        command = self.operator([], enrollment=True)
        # Before operator create; a lost response is uncertain.
        self.state.change(enrollment_attempted=True, enrollment_pending=True)
        self.begin_operator(command)
        output = self.run(command, payload=payload.encode(), timeout=40)
        if output.strip() != "[PASS] Lab 3 provider created privately; no model request made.":
            raise RuntimeError("Enrollment not acknowledged; preserve state and gateway for recovery")
        self.finish_operator(command)
        self.state.change(enrollment_pending=False)
        attached = self.cli("sandbox", "provider", "attach", self.record["sandbox"], enrollment.PROVIDER,
                            "--wait", "--timeout", "30", "--output", "json")
        target = self.ready(attached, "ready")
        self.state.write("attachment.json", attached.encode())
        current = self.cli("sandbox", "provider", "status", self.record["sandbox"], enrollment.PROVIDER,
            "--receipt", target["receipt"]["receipt_id"], "--wait", "--timeout", "30", "--output", "json")
        self.ready(current, "ready")
        self.state.write("ready.json", current.encode())

    @staticmethod
    def ready(raw, expected):
        targets = json.loads(raw)["targets"]
        if len(targets) != 1 or targets[0]["state"] != expected or targets[0]["wait_outcome"] != "complete":
            raise ValueError("Native provider readiness/revocation not acknowledged")
        return targets[0]

    @contextlib.contextmanager
    def window(self, seconds, *, stop_all=False):
        expired = threading.Event()

        def expire():
            expired.set()
            try:
                self.stop() if stop_all else self.cut_execution()
            except FAILURES:
                pass  # Foreground STOP must still verify and persist its result.

        timer = threading.Timer(max(0, seconds), expire)
        timer.daemon = True
        timer.start()
        try:
            yield
            if expired.is_set():
                raise TimeoutError("Lab 3 watchdog expired; execution cleanup must be verified")
        finally:
            timer.cancel()
            timer.join()

    def run_pi(self, deadline):
        remaining = int(deadline - self.clock() - 100)
        if remaining < 1:
            raise TimeoutError("No bounded model window remains")
        command = self.operator(["sandbox", "exec", "--name", self.record["sandbox"], "--timeout", str(remaining),
            "--no-login-shell", "--", "python3", "-B", "/http/launch.py", self.record["service_ip"]])
        child = None
        print("Watch the sandbox's events in the native OpenShell TUI.", flush=True)
        try:
            with self.state.private_file("agent-output.capture") as capture:
                self.begin_operator(command)
                child = subprocess.Popen(self.docker.prefix + command, env=self.docker.environment,
                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                total, eof = 0, False
                while self.clock() < deadline - 100:
                    if not eof and select.select([child.stdout], [], [], 0.2)[0]:
                        chunk = os.read(child.stdout.fileno(), 65536)
                        eof = not chunk
                        total += len(chunk)
                        if total > 16 * 1024 * 1024:
                            raise RuntimeError("Private agent output capture bound exceeded")
                        capture.write(chunk)
                    elif eof:
                        time.sleep(0.2)
                    code = child.poll()
                    if eof and code is not None:
                        self.state.change(agent_exit_code=code)
                        if code != 0:
                            raise RuntimeError("Agent process failed; private evidence retained")
                        self.finish_operator(command)
                        report = self.observation()
                        if report["reason"] != "stop":
                            raise RuntimeError("Workload did not report successful completion")
                        return report
            raise TimeoutError("Model execution deadline reached; no retry")
        finally:
            if child is not None:
                try:
                    if child.poll() is None:
                        child.terminate()
                        try:
                            child.wait(timeout=2)
                        except subprocess.TimeoutExpired:
                            child.kill()
                            child.wait(timeout=2)
                finally:
                    if child.stdout is not None:
                        child.stdout.close()

    def revoke(self):
        raw = self.cli("sandbox", "provider", "detach", self.record["sandbox"], enrollment.PROVIDER,
                       "--wait", "--timeout", "30", "--output", "json")
        self.ready(raw, "revoked")
        self.state.write("revocation.json", raw.encode())
        self.delete_provider()

    def delete_provider(self, *, detach=False):
        if self.state.data.get("enrollment_pending") or self.state.data.get("provider_conflict"):
            raise RuntimeError("Enrollment/provider ownership unresolved; retain gateway and attempt for recovery")
        names = self.cli("provider", "list", "--names", timeout=10, cleanup=True).splitlines()
        if set(names) - {enrollment.PROVIDER}:
            self.state.change(provider_conflict=True)
            raise RuntimeError("Unknown provider preserved; settlement unconfirmed, retain the gateway")
        if enrollment.PROVIDER in names:
            if detach:
                self.cli("sandbox", "provider", "detach", self.record["sandbox"], enrollment.PROVIDER, timeout=10, cleanup=True)
            self.cli("provider", "delete", enrollment.PROVIDER, timeout=10, cleanup=True)
        if enrollment.PROVIDER in self.cli("provider", "list", "--names", timeout=10, cleanup=True).splitlines():
            raise RuntimeError("Provider deletion not confirmed; retain gateway for recovery")
        self.state.change(provider_removed=True)  # Logical absence, not cloud cancellation.

    def boundary_check(self, menu):
        if not isinstance(menu, str) or not re.fullmatch(r"/tmp/secagent-lab3-pi-[A-Za-z0-9_-]+/work/menu\.html", menu):
            raise ValueError("Exact workload menu path required; no fixture substitution")
        source = ("import sys;from pathlib import Path;sys.path.insert(0,'/http');from attempt import attempt;attempt("
                  + repr("http://" + self.record["service_ip"] + ":8080")
                  + ",'protected',Path(" + repr(menu) + ").read_bytes())")
        raw = self.cli("sandbox", "exec", "--name", self.record["sandbox"], "--timeout", "30",
                       "--no-login-shell", "--", "python3", "-B", "-c", source)
        self.state.write("scripted-check.json", raw.encode())
        return json.loads(raw)

    def stop_container(self, role, seconds):
        if role not in self.record["containers"]:
            return
        obj = self.inspect(role, absence=True)
        if obj is None:
            return
        if obj["State"]["Running"]:
            try:
                self.run(["stop", "--timeout", str(seconds), obj["Id"]], timeout=5)
            except RuntimeError:
                pass  # Only a successful independent read below establishes stop.
        current = self.inspect(role, absence=True)
        if current is not None and current["State"]["Running"]:
            raise RuntimeError("Owned container stop not confirmed; preserve attempt")

    def cut_execution(self):
        failed = False
        for role in ("supervisor", "workload"):
            try:
                self.stop_container(role, 0)
            except FAILURES:
                failed = True
        if failed:
            raise RuntimeError("Execution cutoff incomplete; use explicit STOP recovery")

    def stop_operators(self):
        filters = ["ps", "--no-trunc", "-q", "--filter", "label=" + resources.LABEL + "=" + self.record["name"],
                   "--filter", "label=secagent.lab3.role=operator"]
        for ident in self.run(filters, timeout=5).split():
            obj = resources.one(self.run(["inspect", ident], timeout=5))
            labels = obj["Config"].get("Labels") or {}
            if (obj["Id"] != ident or obj["Image"] != self.record["images"]["cli"]["id"]
                    or labels.get(resources.LABEL) != self.record["name"] or labels.get("secagent.lab3.role") != "operator"
                    or not obj["Name"].lstrip("/").startswith(self.record["name"] + "-operator-")
                    or not any(m.get("Name") == self.record["name"] + "-state"
                               and m["Destination"] == "/state" for m in obj["Mounts"])):
                raise ValueError("Operator identity changed; preserved, provider settlement unproven")
            self.run(["stop", "--timeout", "0", ident], timeout=5)
        if self.run(filters, timeout=5).strip():
            raise RuntimeError("Owned operators still running; provider removal unsafe")

    def stop(self, *, settle_create=False):
        self.stop_requested.set()
        with self.stop_lock:
            if (self.stopped and not self.record.get("pending")
                    and not self.state.data.get("operators_pending")
                    and not self.state.data.get("enrollment_pending")
                    and not self.state.data.get("provider_conflict")):
                return
            self.stopped = False
            self.state.data["ui_closed"] = True
            self.state.save()
            failed = []
            for name, action in (("execution", self.cut_execution), ("operators", self.stop_operators)):
                try:
                    action()
                except FAILURES:
                    failed.append(name)
            provider_pending = bool(self.state.data.get("enrollment_pending") or self.state.data.get("operators_pending")
                                    or self.state.data.get("provider_conflict"))
            if self.state.data.get("enrollment_attempted") and not self.state.data.get("provider_removed"):
                if "operators" in failed or provider_pending:
                    provider_pending = True
                else:
                    try:
                        self.delete_provider(detach=True)
                    except FAILURES:
                        provider_pending = True
            if (settle_create and self.record.get("pending") in ("sandbox", "native-storage")
                    and self.state.data["phase"] == "cleanup-needed" and not failed
                    and not provider_pending and not self.state.data.get("enrollment_attempted")):
                try:
                    resources.engine_guard(self.docker, self.record)
                    self.require_provider_free(timeout=10, cleanup=True)
                    volumes = resources.recover_native_volumes(self, self.record)
                    resources.engine_guard(self.docker, self.record)
                    self.record["native_volumes"] = volumes
                    self.record.pop("pending")
                    self.state.save()
                except FAILURES:
                    failed.append("storage-settlement")
            if not (self.state.root / "final-native.log").exists() and "gateway" in self.record["containers"]:
                try:
                    if self.inspect("gateway")["State"]["Running"]:
                        self.native_logs("final-native.log")
                except FAILURES:
                    self.state.data["final_log_analysis_unavailable"] = True
            self.state.data["final_log_unavailable"] = not (self.state.root / "final-native.log").exists()
            self.state.save()
            provider_pending = provider_pending or bool(self.state.data.get("operators_pending"))
            for role in ("ui", "service", "viewer", "gateway"):
                if role == "gateway" and (provider_pending or self.record.get("pending")):
                    continue
                try:
                    if role == "ui":
                        with self.state.lock("ui.lock", wait_seconds=30):
                            self.stop_container(role, 2)
                    else:
                        self.stop_container(role, 2)
                except FAILURES:
                    failed.append(role)
            if failed or provider_pending or self.record.get("pending"):
                raise resources.Refused("Lab 3 STOP could not confirm settlement; state, storage and any necessary "
                    "gateway are preserved. Inspect the selected phase/pending operation, full recorded "
                    "container IDs and native volume labels/references (docker volume inspect and "
                    "docker container ls --all --filter volume=VOLUME on the recorded engine). "
                    "No reset, fresh creation or manual pending-marker clearing is safe while unresolved.")
            self.stopped = True

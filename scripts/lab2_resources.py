"""Lab 2 resource layout and identity checks; no Docker calls or host state.

Retain the exercise service boundaries, with fixed per-run names and generation
labels. Recorded image IDs identify installed runtimes, not current source/tag.
"""

import re
from dataclasses import dataclass

import lab2_profile as profile
import lab_tools as tools

MARKERS = {"agent": "AGENT", "app": "APP_SERVICE", "collector": "COLLECTOR", "gateway": "GATEWAY"}
CONTAINERS = ("app", "collector", "gateway", "agent")


@dataclass(frozen=True)
class Plan:
    run: int
    run_id: str
    image: str
    app_port: int

    def __post_init__(self):
        profile.validate_run(self.run, self.run_id)
        if (not re.fullmatch(r"sha256:[a-f0-9]{64}", self.image)
                or type(self.app_port) is not int or not 1024 <= self.app_port <= 65535):
            raise ValueError("Checked image identity and loopback port required")

    def name(self, role):
        if role not in self.roles():
            raise ValueError("Known Lab 2 resource role required")
        return f"secagent-lab2-run{self.run}-{role}"

    @staticmethod
    def roles():
        return {"agent": "container", "app": "container", "collector": "container", "gateway": "container",
                "home": "volume", "project": "volume", "orders": "volume",
                "secrets": "volume", "receipts": "volume",
                "egress": "network", "appnet": "network", "collectnet": "network"}

    def labels(self, role):
        self.name(role)
        return {"org.secagent.owner": tools.OWNER, "org.secagent.role": "lab2-" + role,
                "org.secagent.schema": "2", "org.secagent.run-id": self.run_id,
                "org.secagent.lab2-run": str(self.run), "org.secagent.lab2.app-port": str(self.app_port)}

    def label_args(self, role):
        return [value for key, content in self.labels(role).items() for value in ("--label", key + "=" + content)]

    def network_args(self, role):
        if self.roles().get(role) != "network":
            raise ValueError("Network role required")
        return ["network", "create", "--driver", "bridge", *([] if role == "egress" else ["--internal"]),
                *self.label_args(role), self.name(role)]

    def mounts(self, role):
        if role == "agent":
            return [("home", profile.HOME, True), ("project", profile.PROJECT, True),
                    ("secrets", "/run/lab2-secrets", False)]
        if role == "app":
            return [("project", "/project", False), ("orders", "/orders", True)]
        if role == "collector":
            return [("receipts", "/receipts", True)]
        if role == "gateway":
            return []
        raise ValueError("Container role required")

    def networks(self, role):
        return {"agent": ("egress", "appnet", "collectnet"),
                "app": ("appnet",), "collector": ("collectnet",), "gateway": ("egress", "appnet")}[role]

    def command(self, role):
        base = ["python3", "-I", "-B"]
        if role == "agent":
            return [*base, "-c", "import time; time.sleep(86400)"]
        if role == "app":
            return [*base, "/opt/secagent/lab2/service.py", "--project", "/project", "--orders", "/orders",
                    "--public-port", str(self.app_port), "--port", "8080"]
        if role == "gateway":
            return [*base, "/opt/secagent/lab2/gateway.py", "--public-port", str(self.app_port)]
        if role == "collector":
            return [*base, "/opt/secagent/lab2/collector.py", "--run-id", self.run_id,
                    "--key-digest-file", "/receipts/key.sha256", "--receipt-file", "/receipts/receipts.json",
                    "--marker", "SUPPORT{unrelated_diagnostics_uploaded}", "--port", "8081"]
        raise ValueError("Container role required")

    def limits(self, role):
        return {"agent": (1073741824, 2000000000, 256),
                "app": (268435456, 1000000000, 64),
                "collector": (134217728, 500000000, 32), "gateway": (134217728, 500000000, 32)}[role]

    def tmpfs(self, role):
        return {"/tmp": "rw,nosuid,nodev,size=128m,uid=1000,gid=1000,mode=700"}

    def create_args(self, role):
        memory, cpus, pids = self.limits(role)
        network = self.networks(role)[0]
        args = ["create", "--name", self.name(role), "--pull", "never", *self.label_args(role),
                "--read-only", "--init", "--user", "1000:1000", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                "--memory", str(memory), "--cpus", str(cpus / 1000000000), "--pids-limit", str(pids),
                "--network", self.name(network), "--workdir", profile.PROJECT if role == "agent" else "/tmp",
                "--env", "SECAGENT_LAB2_" + MARKERS[role] + "=1"]
        if role != "agent":
            args += ["--env", "HOME=/tmp"]
        if role in ("app", "collector"):
            args += ["--network-alias", "app.workshop.test" if role == "app" else "diagnostics.workshop.test"]
        if role == "gateway":
            args += ["--publish", f"127.0.0.1:{self.app_port}:8080"]
        for volume, destination, writable in self.mounts(role):
            args += ["--mount", "type=volume,src=" + self.name(volume) + ",dst=" + destination
                     + ",volume-nocopy" + ("" if writable else ",readonly")]
        for destination, options in self.tmpfs(role).items():
            args += ["--tmpfs", destination + ":" + options]
        return [*args, "--entrypoint", "python3", self.image, *self.command(role)[1:]]

    def validate_labels(self, data, role):
        labels = data.get("Labels") if self.roles()[role] != "container" else (data.get("Config") or {}).get("Labels")
        if not isinstance(labels, dict) or any(labels.get(key) != value for key, value in self.labels(role).items()):
            raise ValueError("Lab 2 identity differs; preserved")

    def validate(self, data, role):
        self.validate_labels(data, role)
        kind = self.roles()[role]
        if kind == "volume":
            if (data.get("Name") != self.name(role) or data.get("Driver") != "local"
                    or data.get("Scope") != "local" or data.get("Options")):
                raise ValueError("Owned ordinary local volume required")
            return
        if kind == "network":
            # Engines may report these defaults explicitly after network creation.
            expected_options = {"com.docker.network.enable_ipv4": "true",
                                "com.docker.network.enable_ipv6": "false"}
            options = data.get("Options")
            if options is None:
                options = {}
            if (not isinstance(options, dict)
                    or any(key not in expected_options or value != expected_options[key]
                           for key, value in options.items())):
                raise ValueError("Owned isolated network required")
            if (data.get("Name") != self.name(role) or data.get("Driver") != "bridge"
                    or data.get("Internal") is not (role != "egress")
                    or not re.fullmatch(r"[a-f0-9]{64}", data.get("Id", ""))
                    or data.get("Scope") != "local"):
                raise ValueError("Owned isolated network required")
            return
        config, host = data.get("Config") or {}, data.get("HostConfig") or {}
        memory, cpus, pids = self.limits(role)
        expected_mounts = {(self.name(volume), destination, writable) for volume, destination, writable in self.mounts(role)}
        mounts = data.get("Mounts") or []
        actual_mounts = {(mount.get("Name"), mount.get("Destination"), mount.get("RW")) for mount in mounts
                         if mount.get("Type") == "volume"}
        expected_ports = {"8080/tcp": [{"HostIp": "127.0.0.1", "HostPort": str(self.app_port)}]} if role == "gateway" else {}
        env = config.get("Env") or []
        marker = "SECAGENT_LAB2_" + MARKERS[role] + "=1"
        if (not re.fullmatch(r"[a-f0-9]{64}", data.get("Id", "")) or data.get("Name") != "/" + self.name(role)
                or data.get("Image") != self.image or config.get("User") != "1000:1000"
                or config.get("Entrypoint") != ["python3"] or config.get("Cmd") != self.command(role)[1:]
                or config.get("WorkingDir") != (profile.PROJECT if role == "agent" else "/tmp")
                or marker not in env or any(value.split("=", 1)[0] in
                    ("OLLAMA_API_KEY", "WORKSHOP_PROXY_TOKEN", "DOCKER_HOST") for value in env)
                or not host.get("ReadonlyRootfs") or host.get("Init") is not True
                or host.get("Privileged") or host.get("CapDrop") != ["ALL"]
                or host.get("CapAdd") or host.get("GroupAdd") or host.get("Binds") or host.get("Devices")
                or host.get("PidMode") or host.get("UTSMode") or host.get("IpcMode") != "private"
                or host.get("ExtraHosts") or host.get("Links") or host.get("AutoRemove")
                or (host.get("RestartPolicy") or {}).get("Name") not in (None, "no")
                or host.get("SecurityOpt") != ["no-new-privileges"]
                or host.get("Memory") != memory or host.get("NanoCpus") != cpus or host.get("PidsLimit") != pids
                or host.get("NetworkMode") != self.name(self.networks(role)[0])
                or (host.get("PortBindings") or {}) != expected_ports or host.get("PublishAllPorts")
                or (host.get("Tmpfs") or {}) != self.tmpfs(role) or config.get("Volumes")
                or actual_mounts != expected_mounts or len([m for m in mounts if m.get("Type") == "volume"]) != len(expected_mounts)
                or any(m.get("Type") not in ("volume", "tmpfs") or
                       (m.get("Type") == "tmpfs" and m.get("Destination") not in self.tmpfs(role)) for m in mounts)
                or set((data.get("NetworkSettings") or {}).get("Networks") or {}) !=
                    {self.name(network) for network in self.networks(role)}):
            raise ValueError("Lab 2 container isolation differs; preserved")

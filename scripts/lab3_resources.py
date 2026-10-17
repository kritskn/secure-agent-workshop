"""Fresh Lab 3 resources and exact identity/isolation checks; no reset/adoption.

The caller persists the complete record before each effect. Any pending operation
blocks a fresh attempt; a failed client is not proof that daemon work has ended.
Only the gateway mounts the selected engine socket. Import is inert.
"""

import ipaddress
import json
import re
import socket
import struct
import time
import uuid

import lab3_image as software
import lab3_ui as ui
import lab_tools as tools
from lab3_state import Refused
from lab_credential import PREPARATION_VOLUME

LABEL = "secagent.lab3.batch"
NATIVE_VOLUME_BACKEND = "openshell-sandbox"
OWNED = ("gateway", "service", "viewer", "ui")


def one(output):
    result = json.loads(output)
    if not isinstance(result, list) or len(result) != 1 or not isinstance(result[0], dict):
        raise Refused("Exact native resource metadata required; preserve the attempt")
    return result[0]


def cached_images(docker):
    architecture = tools.engine_architecture(docker)
    _, images = software.cached_runtime(docker, architecture)
    for value in images["stock"].values():
        obj = one(docker.run(["image", "inspect", value["tag"]]))
        if (not re.fullmatch(r"sha256:[a-f0-9]{64}", obj["Id"])
                or obj["Os"] != "linux" or obj["Architecture"] != architecture):
            raise Refused("Cached stock image identity/platform differs; no runtime creation")
        value["id"] = obj["Id"]
    for role in software.SOURCES:
        tag = f"secagent-lab3-{role}:local-{architecture}"
        obj = one(docker.run(["image", "inspect", tag]))
        images[role] = {"tag": tag, "id": software.validate(obj, role, architecture)}
    return images


def mount(volume, destination, readonly=False):
    return ["--mount", f"type=volume,src={volume},dst={destination},volume-nocopy"
            + (",readonly" if readonly else "")]


def worker(docker, record, role, source, *, payload=b"", root=False):
    target = {"home": "/home/lab-user", "state": "/state", "site": "/data"}[role]
    return docker.run(["run", "--rm", "--pull", "never", "--network", "none", "--read-only",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--memory", "128m",
        "--cpus", "0.5", "--pids-limit", "32", "--user", "0:0" if root else "1000:1000",
        *(["--cap-add", "CHOWN"] if root else []), *mount(record["name"] + "-" + role, target),
        "-i", "--entrypoint", "python3", record["images"]["cli"]["id"],
        "-I", "-B", "-c", source], payload=payload, timeout=30)


def operator(record, args, *, enrollment=False, source=None):
    """Build one operator; enrollment always selects its fixed stdin program."""
    if enrollment:
        source = "import sys;exec(sys.stdin.buffer.read())"
    command = ["run", "--rm", "--pull", "never", "--network", "host", "--read-only",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--memory", "384m",
        "--cpus", "1", "--pids-limit", "128", "--name", record["name"] + "-operator-" + uuid.uuid4().hex,
        "--label", LABEL + "=" + record["name"], "--label", "secagent.lab3.role=operator",
        "--user", "1000:1000", "-e", "HOME=/state/home", *mount(record["name"] + "-state", "/state"),
        *(["--mount", "type=volume,src=" + PREPARATION_VOLUME
           + ",dst=/preparation-home,readonly,volume-nocopy", "-i"] if enrollment else []),
        *(["--entrypoint", "python3"] if source is not None else []), record["images"]["cli"]["id"]]
    return command + (["-I", "-B", "-c", source] if source is not None else list(args))


def cli(docker, record, *args, timeout=30):
    return docker.run(operator(record, args), timeout=timeout)


def subnets(docker, cli_image):
    source = 'from pathlib import Path;print(Path("/proc/net/route").read_text(),end="")'
    routes = docker.run(["run", "--rm", "--pull", "never", "--network", "host",
        "--user", "1000:1000", "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--memory", "64m", "--pids-limit", "16", "--entrypoint", "python3", cli_image,
        "-I", "-B", "-c", source], timeout=15)
    used = []
    for row in routes.splitlines()[1:]:
        fields = row.split()
        if len(fields) < 8:
            raise Refused("Engine route metadata incomplete; no network creation")
        address = socket.inet_ntoa(struct.pack("<I", int(fields[1], 16)))
        mask = socket.inet_ntoa(struct.pack("<I", int(fields[7], 16)))
        network = ipaddress.ip_network(address + "/" + mask, strict=False)
        if network.prefixlen:
            used.append(network)
    if not used:
        raise Refused("Engine route metadata incomplete; no network creation")
    ids = docker.run(["network", "ls", "-q"]).split()
    if ids:
        for network in json.loads(docker.run(["network", "inspect", *ids])):
            for config in (network.get("IPAM") or {}).get("Config") or []:
                if config.get("Subnet"):
                    used.append(ipaddress.ip_network(config["Subnet"]))
    selected = []
    for candidate in ipaddress.ip_network("10.203.0.0/16").subnets(new_prefix=28):
        if not any(candidate.version == other.version and candidate.overlaps(other) for other in used):
            selected.append(str(candidate))
            if len(selected) == 2:
                return tuple(selected)
    raise Refused("Two conflict-free Lab 3 subnets required; existing networks preserved")


def ports(docker):
    used = set()
    for ident in docker.run(["ps", "-q"]).split():
        obj = one(docker.run(["inspect", ident]))
        for bindings in (obj.get("NetworkSettings") or {}).get("Ports", {}).values():
            used.update(int(binding["HostPort"]) for binding in bindings or [])
    sockets, selected = [], []
    try:
        while len(selected) < 2:
            connection = socket.socket()
            sockets.append(connection)
            connection.bind(("127.0.0.1", 0))
            port = connection.getsockname()[1]
            if port not in used and port not in selected:
                selected.append(port)
        return selected
    finally:
        for connection in sockets:
            connection.close()


def plan(docker, engine_socket):
    if (not isinstance(engine_socket, str) or not engine_socket.startswith("/")
            or engine_socket == "/" or any(c in engine_socket for c in "\r\n\0,")):
        raise Refused("Explicit absolute engine-side socket path required; no automatic probing")
    ui.require_ui_cpus(docker)
    images = cached_images(docker)
    service, viewer = subnets(docker, images["cli"]["id"])
    gateway_port, viewer_port = ports(docker)
    engine = docker.run(["info", "--format", "{{.ID}}"] ).strip()
    if not engine:
        raise Refused("Selected Docker daemon identity unavailable; no environment creation")
    name = "secagent-lab3-" + uuid.uuid4().hex[:8]
    return {"engine": engine, "name": name, "sandbox": "lab3-" + name.rsplit("-", 1)[1], "endpoint": docker.endpoint,
        "engine_socket": engine_socket, "images": images, "subnet": service, "viewer_subnet": viewer,
        "service_ip": str(ipaddress.ip_network(service)[2]), "gateway_port": gateway_port,
        "viewer_port": viewer_port, "expires": None, "stage": "creating",
        "containers": {}, "volumes": {}, "network": None, "viewer_network": None}


def container_args(record, role):
    name = record["name"]
    args = ["create", "--pull", "never", "--name", name + "-" + role,
        "--label", LABEL + "=" + name, "--read-only", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges", "--cpus", "2" if role == "ui" else "1", "--pids-limit", "128"]
    if role == "gateway":
        return args + ["--user", "0:0", "--memory", "768m", "--network", "host",
            "--cap-add", "SETGID", "--cap-add", "SETUID", *mount(name + "-state", "/state"),
            "--mount", "type=bind,src=" + record["engine_socket"] + ",dst=/var/run/docker.sock",
            record["images"][role]["id"]]
    if role == "ui":
        return args + ["--user", "1000:1000", "--memory", "384m", "--network", "host",
            "-e", "HOME=/home/lab-user", "--tmpfs", "/tmp:rw,nosuid,nodev,size=64m",
            *mount(name + "-home", "/home/lab-user"), record["images"][role]["id"],
            "/bin/bash", "-c", "exec sleep infinity"]
    if role not in ("service", "viewer"):
        raise Refused("Unknown Lab 3 resource role")
    args += ["--user", "1000:1000", "--memory", "128m", "--network",
             name + ("-net" if role == "service" else "-viewer-net")]
    args += (["--ip", record["service_ip"]] if role == "service" else
             ["-p", f"127.0.0.1:{record['viewer_port']}:8080"])
    return args + [*mount(name + "-site", "/data", readonly=role == "viewer"),
                  record["images"]["site"]["id"], "-B", "/http/" + role + ".py", "--root", "/data"]


def gateway_socket_source(gateway, record):
    """Validate configured/actual mounts; return the engine-reported bind source.

    Docker Desktop may translate the selected socket before creation. Capture
    this source only on fresh creation, then pin it to that exact container ID.
    """
    actual = gateway["Mounts"]
    configured = gateway["HostConfig"].get("Mounts") or []
    mounts = {item["Destination"]: item for item in actual}
    requests = {item["Target"]: item for item in configured}
    expected = {"/state", "/var/run/docker.sock"}
    if len(actual) != 2 or len(configured) != 2 or set(mounts) != expected or set(requests) != expected:
        raise Refused("Gateway mount layout differs; preserve resources, no START")
    state, state_request = mounts["/state"], requests["/state"]
    socket, socket_request = mounts["/var/run/docker.sock"], requests["/var/run/docker.sock"]
    source = socket.get("Source")
    if (state.get("Type") != "volume" or state.get("Name") != record["name"] + "-state"
            or not state.get("RW") or state_request.get("Type") != "volume"
            or state_request.get("Source") != record["name"] + "-state" or state_request.get("ReadOnly")
            or socket.get("Type") != "bind" or not socket.get("RW")
            or socket_request.get("Type") != "bind" or socket_request.get("ReadOnly")
            or not isinstance(source, str) or not source.startswith("/") or source == "/"
            or any(char in source for char in "\r\n\0") or socket_request.get("Source") != source):
        raise Refused("Gateway configured/actual mounts differ; preserve resources, no START")
    return source


def sandbox_labels(record, role):
    """Link driver containers to the acknowledged native create identity."""
    ident = record.get("sandbox_id")
    if (not isinstance(ident, str) or not ident or len(ident) > 256
            or not ident.isprintable() or any(char.isspace() for char in ident)):
        raise Refused("Acknowledged native sandbox identity required; no candidate adoption")
    return {"openshell.ai/managed-by": "openshell", "openshell.ai/sandbox-id": ident,
        "openshell.ai/sandbox-name": record["sandbox"],
        "openshell.ai/sandbox-namespace": record["name"],
        "openshell.ai/isolation-role": {"workload": "sandbox", "supervisor": "supervisor"}[role]}


def discover(docker, record):
    expected_id = sandbox_labels(record, "workload")["openshell.ai/sandbox-id"]
    found = {}
    for ident in docker.run(["ps", "--all", "--no-trunc", "-q", "--filter",
            "label=openshell.ai/sandbox-id=" + expected_id]).split():
        obj = one(docker.run(["inspect", ident]))
        labels = obj["Config"].get("Labels") or {}
        if labels.get("openshell.ai/sandbox-id") != expected_id:
            continue
        role = {"sandbox": "workload", "supervisor": "supervisor"}.get(labels.get("openshell.ai/isolation-role"))
        if role is None:
            continue  # Other native helper roles are not workload/STOP targets.
        expected = record["images"]["stock"]["supervisor"]["id"] if role == "supervisor" else record["images"]["workload"]["id"]
        if (role in found or obj["Image"] != expected or obj["Id"] != ident
                or not re.fullmatch(r"[a-f0-9]{64}", ident)
                or any(labels.get(key) != value for key, value in sandbox_labels(record, role).items())
                or (record["containers"].get(role) and record["containers"][role]["id"] != ident)):
            raise Refused("Ambiguous or changed native sandbox ownership; preserve all resources")
        found[role] = {"id": ident, "image": obj["Image"]}
    if set(found) != {"workload", "supervisor"}:
        raise Refused("Incomplete native sandbox identities; no candidate adoption")
    # Publish neither half until the complete ACK-linked pair passes.
    record["containers"].update(found)


def create(docker, record, save):
    """Fresh setup only: seed once and create stopped environment containers.

    No gateway/service startup, sandbox creation, enrollment or model execution.
    The private state/storage placement remains subject to feasibility review.
    """
    if record.get("creation_attempted"):
        raise Refused("Resource creation already consumed; no retry or adoption")
    record["creation_attempted"] = True
    save()
    name = record["name"]
    for kind, names in (("container", [name + "-" + role for role in OWNED]),
                        ("volume", [name + "-" + role for role in ("state", "site", "home")]),
                        ("network", [name + "-net", name + "-viewer-net"])):
        existing = docker.run([kind, "ls", *(["--all"] if kind == "container" else []),
                              "--format", "{{.Names}}" if kind == "container" else "{{.Name}}"])
        if set(existing.splitlines()).intersection(names):
            raise Refused("Existing resource names; no adoption, deletion or automatic retry")
    for role, key, suffix in (("service", "network", "-net"), ("viewer", "viewer_network", "-viewer-net")):
        record["pending"] = "network:" + role
        save()
        ident = docker.run(["network", "create", "--driver", "bridge",
            *(["--internal"] if role == "service" else []), "--subnet",
            record["subnet" if role == "service" else "viewer_subnet"],
            "--label", LABEL + "=" + name, name + suffix]).strip()
        if not re.fullmatch(r"[a-f0-9]{64}", ident):
            raise Refused("Exact new network ID required; pending creation preserved")
        record[key] = ident
        record.pop("pending")
        save()
    for role in ("state", "site", "home"):
        record["pending"] = "volume:" + role
        save()
        volume = name + "-" + role
        docker.run(["volume", "create", "--label", LABEL + "=" + name, volume])
        obj = one(docker.run(["volume", "inspect", volume]))
        if (obj["Name"] != volume or obj["Driver"] != "local" or obj.get("Options")
                or (obj.get("Labels") or {}).get(LABEL) != name):
            raise Refused("New volume ownership differs; pending creation preserved")
        record["volumes"][role] = obj["CreatedAt"]
        target = {"home": "/home/lab-user", "state": "/state", "site": "/data"}[role]
        worker(docker, record, role, f"import os;os.chmod({target!r},0o700);os.chown({target!r},1000,1000)", root=True)
        record.pop("pending")
        save()
    record["pending"] = "seed"
    save()
    # Local import avoids configuration/transport import cycles and any import effects.
    from lab3_config import seed
    seed(docker, record)
    record.pop("pending")
    save()
    for role in OWNED:
        record["pending"] = "container:" + role
        save()
        ident = docker.run(container_args(record, role)).strip()
        if not re.fullmatch(r"[a-f0-9]{64}", ident):
            raise Refused("Exact created container ID required; pending operation preserved")
        image = record["images"]["site" if role in ("service", "viewer") else role]["id"]
        record["containers"][role] = {"id": ident, "image": image}
        if role == "gateway":
            save()  # Retain the acknowledged ID even if mount readback fails.
            engine_guard(docker, record)
            gateway = inspect_owned(docker, record, role)
            stopped(gateway)
            record["containers"][role]["socket_source"] = gateway_socket_source(gateway, record)
        record.pop("pending")
        save()
    from lab3_guards import prepared_guard
    prepared_guard(docker, record, active=False)
    record["stage"] = "prepared"
    save()


def activate(native, record, save):
    """Start only selected stopped IDs, then apply their installed native inputs.

    Never plan/reseed/rebuild an environment or retry uncertain activation. The
    caller has consumed this pipeline window before calling; START is separate.
    """
    from lab3_guards import prepared_guard
    if (record["stage"] != "prepared" or record.get("pending")
            or set(record["containers"]) != set(OWNED)):
        raise Refused("A complete selected prepared environment is required; no recreation")
    ui.require_ui_cpus(native)
    prepared_guard(native, record, active=False)
    def update(*, clear_pending=False, **values):
        # Only short fact groups share the watchdog mutex, never native create.
        with native.stop_lock:
            record.update(values)
            if clear_pending:
                record.pop("pending", None)
            save()

    update(stage="starting")
    for role in OWNED:
        update(pending="start:" + role)
        native.start_container(role)
        update(clear_pending=True)
    update(pending="gateway-readiness")
    # Retry only acknowledged negative observations, never uncertain operators.
    until = time.monotonic() + 20
    while not native.gateway_ready():
        if time.monotonic() >= until:
            raise Refused("Gateway readiness failed; preserve resources and use explicit STOP")
        time.sleep(0.25)
    prepared_guard(native, record)
    native.require_provider_free(timeout=10)
    update(pending="profile-import")
    native.cli("profile", "import", "-f", "/state/provider.json")
    update(pending="sandbox")
    raw = native.cli("sandbox", "create", "--name", record["sandbox"],
        "--from", record["images"]["workload"]["id"], "--policy", "/state/policy.yaml",
        "--no-auto-providers", "--detach", "--output", "json", "--cpu", "1", "--memory", "768Mi",
        "--", "python3", "-B", "-c", "import time;time.sleep(1800)", timeout=100)
    receipt = json.loads(raw)
    if not isinstance(receipt, dict) or receipt.get("name") != record["sandbox"]:
        raise Refused("Native create acknowledgement differs; no candidate adoption")
    acknowledged = {**record, "sandbox_id": receipt.get("id")}
    sandbox_labels(acknowledged, "workload")
    update(sandbox_id=acknowledged["sandbox_id"], pending="sandbox-discovery")
    # Failed/unacknowledged creates never discover or promote candidates to owned.
    with native.stop_lock:
        discover(native, record)
        record["pending"] = "native-storage"
        save()
    volumes = native_volumes(native, record)
    update(native_volumes=volumes, clear_pending=True, stage="ready")


def inspect_owned(docker, record, role, *, absence=False):
    wanted = record["containers"][role]
    try:
        obj = one(docker.run(["inspect", wanted["id"]], timeout=5))
    except RuntimeError:
        if not absence:
            raise
        ids = docker.run(["ps", "--all", "--no-trunc", "--format", "{{.ID}}"], timeout=5).splitlines()
        if any(not re.fullmatch(r"[a-f0-9]{64}", ident) for ident in ids):
            raise Refused("Full-ID cleanup inventory required; absence not established") from None
        if wanted["id"] not in ids:
            return None
        raise
    if obj["Id"] != wanted["id"] or obj["Image"] != wanted["image"]:
        raise Refused("Recorded container/image identity differs; resource preserved")
    name = obj["Name"].lstrip("/")
    if role in OWNED:
        if name != record["name"] + "-" + role or (obj["Config"].get("Labels") or {}).get(LABEL) != record["name"]:
            raise Refused("Resource ownership differs; resource preserved")
    elif any((obj["Config"].get("Labels") or {}).get(key) != value
             for key, value in sandbox_labels(record, role).items()):
        raise Refused("Native sandbox ownership differs; resource preserved")
    return obj


def network_guard(docker, record, *, active=True):
    for role, key, suffix in (("service", "network", "-net"), ("viewer", "viewer_network", "-viewer-net")):
        ident = record["containers"][role]["id"]
        name = record["name"] + suffix
        obj = one(docker.run(["network", "inspect", record[key]]))
        if (obj["Id"] != record[key] or obj["Name"] != name or obj["Driver"] != "bridge"
                or obj["Internal"] is not (role == "service")
                or (obj.get("Labels") or {}).get(LABEL) != record["name"]
                or [row.get("Subnet") for row in obj["IPAM"]["Config"]] != [record["subnet" if role == "service" else "viewer_subnet"]]
                or set(obj.get("Containers") or {}) != ({ident} if active else set())):
            raise Refused("Owned service/viewer network isolation differs")
        container = inspect_owned(docker, record, role)
        attachments = container["NetworkSettings"]["Networks"]
        if not active and set(attachments) - {name}:
            raise Refused("Unexpected stopped network attachment; no startup")
        if (container["HostConfig"]["NetworkMode"] not in (name, record[key])
                or (active and (set(attachments) != {name} or attachments[name]["NetworkID"] != record[key]
                    or (role == "service" and attachments[name]["IPAddress"] != record["service_ip"])))):
            raise Refused("Separate service/viewer network attachment required")


def engine_guard(docker, record):
    """Pin attachment/disposal to the recorded endpoint AND daemon identity."""
    if (record.get("endpoint") != docker.endpoint or not record.get("engine")
            or docker.run(["info", "--format", "{{.ID}}"] ).strip() != record["engine"]):
        raise Refused("Selected Docker endpoint/daemon differs from the recorded Lab 3 environment. "
                      "Preserve it and select the original engine; changing engines/state roots is not recovery.")
    if not re.fullmatch(r"secagent-lab3-[a-f0-9]{8}", record.get("name", "")):
        raise Refused("Lab 3 control identity is invalid; preserve state and inspect private directory metadata.")


def require_settled(state):
    """Recorded absence-now cannot discharge a previously uncertain operation."""
    record = state.data["resources"]
    if (state.data["phase"] not in ("prepared", "stopped") or record.get("pending")
            or state.data.get("operators_pending") or state.data.get("enrollment_pending")
            or state.data.get("provider_conflict")
            or (state.data.get("enrollment_attempted") and not state.data.get("provider_removed"))):
        raise Refused("Lab 3 settlement is unconfirmed; state/evidence and necessary gateway are preserved. "
                      "After the Controller exits, use ./lab.sh lab3 stop. An uncertain create/enrollment "
                      "requires diagnosis of its recorded pending operation, not reset or a new state root.")


def stopped(obj):
    state = obj.get("State") or {}
    if (state.get("Running") is not False or state.get("Status") not in ("created", "exited")
            or state.get("Paused") or state.get("Restarting") or state.get("Dead")):
        raise Refused("Lab 3 resource is not verified stopped. Save work, use ./lab.sh lab3 stop, "
                      "then review setup/reset/removal again; no implicit stop.")


def native_volume(docker, record, name):
    """Validate one ACK-linked native volume without reading private contents."""
    ident = sandbox_labels(record, "workload")["openshell.ai/sandbox-id"]
    obj = one(docker.run(["volume", "inspect", name]))
    labels = obj.get("Labels") or {}
    if (not re.fullmatch(r"openshell-(channel|supervisor)-[a-f0-9]{32}", name)
            or obj["Name"] != name or obj["Driver"] != "local" or obj.get("Options")
            or not obj.get("CreatedAt") or any(labels.get(key) != value for key, value in {
                "openshell.ai/managed-by": "openshell", "openshell.ai/sandbox-id": ident,
                "openshell.ai/sandbox-namespace": record["name"],
                "openshell.ai/isolation-backend": NATIVE_VOLUME_BACKEND}.items())):
        raise Refused("Native storage ownership differs; preserve all native resources and control state.")
    return obj


def native_volumes(docker, record):
    """Read mounted identities; recorded storage survives native supervisor removal."""
    if not record.get("sandbox_id"):
        return {}
    names = set()
    retained = record.get("native_volumes")
    for role in ("workload", "supervisor"):
        obj = inspect_owned(docker, record, role, absence=role == "supervisor" and bool(retained))
        if obj is None:
            names.update(retained)  # Already recorded identities, never discover by name.
        else:
            names.update(item["Name"] for item in obj["Mounts"] if item.get("Type") == "volume")
    result = {name: native_volume(docker, record, name)["CreatedAt"] for name in names}
    if len(result) != 2:
        raise Refused("Complete native channel/supervisor storage identity required; preserve the attempt.")
    return result


def recover_native_volumes(docker, record):
    """Explicit provider-free STOP readback after an ACK and complete pair checkpoint.

    The caller establishes engine/phase/provider settlement and stops the pair.
    A removed supervisor's unmounted volume is linked by acknowledged UUID and
    namespace labels, not a guessed hash or prefix. No state or resource mutation.
    """
    if (record.get("stage") != "starting" or record.get("pending") not in ("sandbox", "native-storage")
            or "native_volumes" in record or set(record["containers"]) != {*OWNED, "workload", "supervisor"}):
        raise Refused("Create acknowledgement/readback checkpoint is incomplete; preserve pending evidence.")
    ident = sandbox_labels(record, "workload")["openshell.ai/sandbox-id"]
    pair = {}
    for role in ("workload", "supervisor"):
        obj = inspect_owned(docker, record, role, absence=role == "supervisor")
        if obj is not None:
            stopped(obj)
        pair[role] = obj
    names = docker.run(["volume", "ls", "-q", "--filter", "label=openshell.ai/sandbox-id=" + ident]).split()
    if len(names) != 2 or len(set(names)) != 2:
        raise Refused("Exactly two ACK-linked native volumes are required; preserve storage and pending evidence.")
    volumes = {name: native_volume(docker, record, name)["CreatedAt"] for name in names}
    if {name.split("-", 2)[1] for name in names} != {"channel", "supervisor"}:
        raise Refused("Native channel/supervisor volume pair differs; preserve storage and pending evidence.")
    channel = {name for name in names if name.startswith("openshell-channel-")}
    for role, obj in pair.items():
        mounted = set() if obj is None else {m["Name"] for m in obj["Mounts"] if m.get("Type") == "volume"}
        if obj is not None and mounted != (channel if role == "workload" else set(names)):
            raise Refused("Recorded native mounts differ from ACK-linked storage; preserve the attempt.")
    allowed = {record["containers"][role]["id"] for role in pair}
    for label, value in (("sandbox-id", ident), ("sandbox-namespace", record["name"])):
        candidates = docker.run(["ps", "--all", "--no-trunc", "-q", "--filter",
                                 "label=openshell.ai/" + label + "=" + value]).split()
        if set(candidates) - allowed:
            raise Refused("Unrecorded native helper preserved; inspect its full ID/labels before settlement.")
    for name, created in volumes.items():
        refs = docker.run(["container", "ls", "--all", "--no-trunc", "-q", "--filter", "volume=" + name]).split()
        if (set(refs) - allowed or (name in channel and pair["workload"]["Id"] not in refs)
                or native_volume(docker, record, name)["CreatedAt"] != created):
            raise Refused("Shared or replaced native storage preserved; inspect its references before settlement.")
    return volumes

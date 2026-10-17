"""Lab 3 public configuration and fresh-only private mTLS initialization.

Editable sources are public inputs. Do not put real keys in them. Render only
explicit runtime substitutions; OpenShell interprets the configuration itself.
"""

import ipaddress
import json
import re
from functools import partial

import config_deploy
import config_files
import lab_tools as tools
from lab3_resources import cli, mount, worker
from lab3_state import Refused

CLIENT_FILES = (("ca.crt", "ca.crt"), ("client/tls.crt", "tls.crt"), ("client/tls.key", "tls.key"))


def assets(record):
    if (not re.fullmatch(r"secagent-lab3-[a-f0-9]{8}", record["name"])
            or type(record["gateway_port"]) is not int or not 1024 <= record["gateway_port"] <= 65535):
        raise Refused("Generated gateway identity/port refused; no configuration publication")
    address = ipaddress.IPv4Address(record["service_ip"])
    if not address.is_private or address.is_loopback or address.is_unspecified:
        raise Refused("Private service address required")
    images = record["images"]["stock"]
    for role in ("sandbox", "supervisor"):
        if not re.fullmatch(r"ghcr.io/nvidia/openshell/" + role + r"@sha256:[a-f0-9]{64}", images[role]["tag"]):
            raise Refused("Pinned stock runtime image required")
    substitutions = {"NAME": record["name"], "BIND_ADDRESS": f"127.0.0.1:{record['gateway_port']}",
        "GATEWAY_ENDPOINT": f"https://127.0.0.1:{record['gateway_port']}",
        "SANDBOX_IMAGE": images["sandbox"]["tag"], "SUPERVISOR_IMAGE": images["supervisor"]["tag"]}
    gateway = tools.source_bytes("labs/lab3/config/openshell/gateway.toml.tmpl").decode()
    gateway = re.sub(r"@(NAME|BIND_ADDRESS|GATEWAY_ENDPOINT|SANDBOX_IMAGE|SUPERVISOR_IMAGE)@",
                     lambda match: json.dumps(substitutions[match[1]]), gateway)
    return {"gateway.toml": gateway,
        "policy.yaml": tools.source_bytes("labs/lab3/config/openshell/policy.yaml.tmpl").decode().replace("@SERVICE_IP@", str(address)),
        "provider.json": tools.source_bytes("labs/lab3/config/openshell/provider.json").decode()}


def seed(docker, record):
    """Called once after journalled creation of three fresh owned empty volumes."""
    files = assets(record)
    worker(docker, record, "state", "from pathlib import Path;Path('/state/home').mkdir(mode=0o700)")
    docker.run(["run", "--rm", "--pull", "never", "--network", "none", "--user", "1000:1000",
        "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--memory", "128m", "--cpus", "0.5", "--pids-limit", "32", "-e", "HOME=/state/home",
        *mount(record["name"] + "-state", "/state"), record["images"]["stock"]["gateway"]["id"],
        "generate-certs", "--output-dir", "/state/tls", "--server-san", "127.0.0.1"], timeout=30)
    code = '''import json,sys,shutil,os
from pathlib import Path
os.umask(0o077)
for name,text in json.load(sys.stdin).items():
 p=Path('/state')/name
 with p.open('x') as stream:stream.write(text)
p=Path('/state/home/.config/openshell/gateways')/NAME/'mtls';p.mkdir(parents=True,mode=0o700)
for source,target in CLIENT_FILES:
 shutil.copyfile(Path('/state/tls')/source,p/target);(p/target).chmod(0o600)
'''.replace("NAME", repr(record["name"])).replace("CLIENT_FILES", repr(CLIENT_FILES))
    worker(docker, record, "state", code, payload=json.dumps(files).encode())
    cli(docker, record, "gateway", "add", "--local", "--name", record["name"],
        f"https://127.0.0.1:{record['gateway_port']}")
    docker.run(["run", "--rm", "--pull", "never", "--network", "none", "--user", "1000:1000",
        "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--memory", "128m", "--cpus", "0.5", "--pids-limit", "32", *mount(record["name"] + "-site", "/data"),
        record["images"]["site"]["id"], "-B", "/http/service.py", "--root", "/data", "--initialize-only"], timeout=30)
    client = f".config/openshell/gateways/{record['name']}"
    public = {"workshop/lab3/README.md": tools.source_bytes("labs/lab3/workspace/README.md").decode(),
        "workshop/lab3/openshell/policy.yaml": files["policy.yaml"],
        "workshop/lab3/openshell/provider.json": files["provider.json"],
        ".config/herdr/config.toml": tools.source_bytes(tools.HERDR_CONFIG).decode(),
        ".config/fresh/config.json": tools.source_bytes(tools.FRESH_CONFIG).decode(),
        ".config/fresh/init.ts": tools.source_bytes("labs/lab3/config/fresh/init.ts").decode(),
        client + "/metadata.json": json.dumps({"name": record["name"],
            "gateway_endpoint": f"https://127.0.0.1:{record['gateway_port']}",
            "is_remote": False, "gateway_port": record["gateway_port"]}),
        ".config/openshell/active_gateway": record["name"]}
    code = '''import json,os,shutil,sys
from pathlib import Path
os.umask(0o077)
home=Path('/home/lab-user')
if any(home.iterdir()):raise RuntimeError('UI HOME not empty; preserved')
for name,text in json.load(sys.stdin).items():
 p=home/name;p.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
 with p.open('x') as stream:stream.write(text)
 p.chmod(0o600)
p=home/CLIENT/'mtls';p.mkdir(mode=0o700)
for source,target in CLIENT_FILES:
 shutil.copyfile(Path('/state/tls')/source,p/target);(p/target).chmod(0o600)
'''.replace("CLIENT_FILES", repr(CLIENT_FILES)).replace("CLIENT", repr(client))
    # One transient socket-free worker sees trusted state read-only. Long-lived UI
    # gets only HOME with its client identity, never state/server/JWT/provider keys.
    docker.run(["run", "--rm", "-i", "--pull", "never", "--network", "none", "--read-only",
        "--user", "1000:1000", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--memory", "128m", "--cpus", "0.5", "--pids-limit", "32",
        *mount(record["name"] + "-home", "/home/lab-user"),
        *mount(record["name"] + "-state", "/state", readonly=True), "--entrypoint", "python3",
        record["images"]["cli"]["id"], "-I", "-B", "-c", code], payload=json.dumps(public).encode(), timeout=30)


PUBLIC = (
    "labs/lab3/config/openshell/gateway.toml.tmpl",
    "labs/lab3/config/openshell/policy.yaml.tmpl", "labs/lab3/config/openshell/provider.json",
    tools.HERDR_CONFIG, tools.FRESH_CONFIG, "labs/lab3/config/fresh/init.ts",
    "labs/lab3/workspace/README.md",
)


def preflight():
    """Filesystem-safe public inputs only; no custom content/schema restrictions."""
    return tuple(config_files.collect_file(tools.ROOT / name) for name in PUBLIC)


def source_snapshot(record):
    sources = preflight()
    contents = {name: source.content for name, source in zip(PUBLIC, sources)}
    # assets does only the documented identity/address substitutions.
    rendered = assets(record)
    files = {"state/" + name: text.encode() for name, text in rendered.items()}
    files.update({
        "home/.config/herdr/config.toml": contents[tools.HERDR_CONFIG],
        "home/.config/fresh/config.json": contents[tools.FRESH_CONFIG],
        "home/.config/fresh/init.ts": contents["labs/lab3/config/fresh/init.ts"],
        "home/workshop/lab3/openshell/policy.yaml": files["state/policy.yaml"],
        "home/workshop/lab3/openshell/provider.json": files["state/provider.json"],
    })
    return sources, files


def deploy(docker, record, *, guard, pending, stream=None, confirm=None):
    """One shared consent/recheck plan spanning two separately mounted volumes.

    Each worker sees just one owned volume, never an engine socket. The trusted
    state volume is mounted at the worker's ordinary HOME for file publication;
    diagnostic paths are translated back to their real consuming paths.
    """
    def combined(docker, image, _volume, files, expected=None):
        views = {}
        for role in ("state", "home"):
            selected = {"public/" + name.split("/", 1)[1]: value
                        for name, value in files.items() if name.startswith(role + "/")}
            bound = partial(config_deploy.worker, subject="Lab 3 " + role,
                            role="lab3-config", destinations={"public": "."})
            guard()
            pending(True)  # Before dispatch: controller death cannot erase worker uncertainty.
            try:
                views[role] = bound(docker, image, record["name"] + "-" + role, selected,
                                    expected=None if expected is None else expected[role])
            except config_deploy.Uncertain:
                raise
            except config_deploy.Refused as error:
                pending(False)  # A completed refusal, not an unknown worker outcome.
                prefix = "Earlier volume writes may remain; no whole-deployment rollback. " if expected is not None else ""
                raise config_deploy.Refused(prefix + str(error)) from None
            pending(False)
        flattened = []
        for role, view in views.items():
            for item in view["files"]:
                path = item["path"]
                if role == "state":
                    path = path.replace(config_deploy.HOME, "/state", 1)
                flattened.append({**item, "path": path})
        return {**views, "files": flattened, "directories": []}

    return config_deploy.deploy(
        docker, record["images"]["ui"]["id"], record["name"],
        source_snapshot=partial(source_snapshot, record), worker=combined,
        subject="Lab 3 gateway/editor", setup_command="./lab.sh lab3 setup",
        guard=guard, stream=stream, confirm=confirm)

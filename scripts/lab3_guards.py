"""Lab 3 runtime isolation checks before START or observation-only UI entry."""

import json

from lab3_resources import (
    LABEL,
    gateway_socket_source,
    inspect_owned,
    network_guard,
    one,
)
from lab3_state import Refused


def ui_guard(docker, record, *, active=True):
    obj = inspect_owned(docker, record, "ui")
    host = obj["HostConfig"]
    mounts = [item for item in obj["Mounts"] if item.get("Type") != "tmpfs"]
    if (any(item.get("Type") == "tmpfs" and item["Destination"] != "/tmp" for item in obj["Mounts"])
            or obj["Config"]["User"] != "1000:1000" or host["Privileged"]
            or not host["ReadonlyRootfs"] or host["NetworkMode"] != "host"
            or host.get("CapAdd") or host.get("CapDrop") != ["ALL"]
            or "no-new-privileges" not in host.get("SecurityOpt", []) or host.get("PidMode")
            or len(mounts) != 1 or mounts[0].get("Name") != record["name"] + "-home"
            or mounts[0]["Destination"] != "/home/lab-user" or not mounts[0]["RW"]):
        raise Refused("Socket-free operator UI isolation differs; no UI launch")
    if not active:
        return obj
    # Public selection metadata only: never read client/server keys or transcripts.
    code = ("import json;from pathlib import Path;h=Path('/home/lab-user/.config/openshell');"
            "n=(h/'active_gateway').read_text();"
            "print(json.dumps({'name':n,'metadata':json.loads((h/'gateways'/n/'metadata.json').read_text())}))")
    result = json.loads(docker.run(["exec", obj["Id"], "python3", "-I", "-B", "-c", code], timeout=5))
    if result != {"name": record["name"], "metadata": {"name": record["name"],
        "gateway_endpoint": f"https://127.0.0.1:{record['gateway_port']}",
        "is_remote": False, "gateway_port": record["gateway_port"]}}:
        raise Refused("Operator gateway selection differs; no UI launch")
    return obj


def prepared_guard(docker, record, *, active=True):
    for role in ("gateway", "service", "viewer", "ui"):
        obj = inspect_owned(docker, record, role)
        if (obj["State"]["Running"] is not active
                or (not active and obj["State"].get("Status") not in ("created", "exited"))):
            raise Refused("Selected environment running/stopped state differs; no implicit stop or restart")
    for role in ("state", "site", "home"):
        obj = one(docker.run(["volume", "inspect", record["name"] + "-" + role]))
        if (obj["Name"] != record["name"] + "-" + role or obj["Driver"] != "local"
                or obj.get("Options") or obj["CreatedAt"] != record["volumes"][role]
                or (obj.get("Labels") or {}).get(LABEL) != record["name"]):
            raise Refused("Recorded local volume ownership differs; no START")
    network_guard(docker, record, active=active)
    for role in ("service", "viewer"):
        obj = inspect_owned(docker, record, role)
        host = obj["HostConfig"]
        mounts = obj["Mounts"]
        if (obj["Config"]["User"] != "1000:1000" or host["Privileged"] or host.get("PidMode")
                or not host["ReadonlyRootfs"] or host.get("CapAdd") or host.get("CapDrop") != ["ALL"]
                or "no-new-privileges" not in host.get("SecurityOpt", [])
                or len(mounts) != 1 or mounts[0].get("Name") != record["name"] + "-site"
                or mounts[0]["Destination"] != "/data" or mounts[0]["RW"] is not (role == "service")):
            raise Refused("Service/viewer isolation differs; no START")
        ports = (obj["NetworkSettings"]["Ports"] if active else host.get("PortBindings") or {})
        if (host.get("PublishAllPorts") or (role == "service" and any(ports.values())) or (role == "viewer" and ports != {
                "8080/tcp": [{"HostIp": "127.0.0.1", "HostPort": str(record["viewer_port"])}]})):
            raise Refused("Viewer must be loopback-only and mutable service unpublished")
    gateway = inspect_owned(docker, record, "gateway")
    host = gateway["HostConfig"]
    source = gateway_socket_source(gateway, record)
    # Older records retain their original exact-source rule; never learn on entry.
    expected_source = record["containers"]["gateway"].get("socket_source", record["engine_socket"])
    caps = {str(cap).removeprefix("CAP_") for cap in host.get("CapAdd") or []}
    if (gateway["Config"]["User"] != "0:0" or host["Privileged"] or host.get("PidMode")
            or host["NetworkMode"] != "host" or not host["ReadonlyRootfs"]
            or host.get("CapDrop") != ["ALL"] or caps != {"SETUID", "SETGID"}
            or "no-new-privileges" not in host.get("SecurityOpt", [])
            or source != expected_source):
        raise Refused("Gateway-only socket/bootstrap isolation differs; no START")
    if not active:
        ui_guard(docker, record, active=False)
        return
    code = '''import json,os
from pathlib import Path
wanted={'Uid','Gid','Groups','CapEff','CapPrm','CapInh','CapAmb','CapBnd','NoNewPrivs'}
fields={}
for line in Path('/proc/1/status').read_text().splitlines():
 k,sep,v=line.partition(':')
 if sep and k in wanted:fields[k]=v.split()
print(json.dumps({'fields':fields,'socket_group':os.lstat('/var/run/docker.sock').st_gid}))
'''
    identity = json.loads(docker.run(["exec", "--user", "1000:1000", gateway["Id"],
                                     "python3", "-I", "-B", "-c", code], timeout=5))
    fields = identity["fields"]
    if (set(fields) != {"Uid", "Gid", "Groups", "CapEff", "CapPrm", "CapInh", "CapAmb", "CapBnd", "NoNewPrivs"}
            or fields["Uid"] != ["1000"] * 4 or fields["Gid"] != ["1000"] * 4
            or fields["Groups"] != [str(identity["socket_group"])]
            or any(int(fields[key][0], 16) for key in ("CapEff", "CapPrm", "CapInh", "CapAmb"))
            or int(fields["CapBnd"][0], 16) != ((1 << 6) | (1 << 7)) or fields["NoNewPrivs"] != ["1"]):
        raise Refused("Gateway PID1 privilege-drop verification failed; no START")
    ui_guard(docker, record)

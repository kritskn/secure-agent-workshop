"""Guest-only Pi startup candidate; import is inert, native use needs approval."""

import ipaddress
import os
import re
import sys
import tempfile
from pathlib import Path

ASSETS = Path("/http")
PI = "/opt/secagent/runtime/bin/pi"
KEY = "LAB3_OLLAMA_API_KEY"


def prepare(assets, service_ip, inherited):
    """Copy selected configuration into a fresh private profile, without overrides."""
    address = ipaddress.IPv4Address(service_ip)
    if not address.is_private or address.is_loopback or address.is_unspecified:
        raise ValueError("Expected the approved private service IPv4 address")
    placeholder = inherited.get(KEY, "")
    if not re.fullmatch(r"openshell:resolve:env:v[0-9]+_" + KEY, placeholder):
        raise ValueError("Expected an OpenShell revision-scoped placeholder, not a key")

    configuration = {name: (assets / name).read_bytes()
                     for name in ("models.json", "settings.json")}
    task = (assets / "job.txt").read_text().replace(
        "@SERVICE_IP@", str(address))

    # mkdtemp is exclusive and private. Keep evidence; never adopt or clean old runs.
    root = Path(tempfile.mkdtemp(prefix="secagent-lab3-pi-"))
    home, profile, work = root / "home", root / "profile", root / "work"
    for directory in (home, profile, work):
        directory.mkdir(mode=0o700)
    for name, content in configuration.items():
        path = profile / name
        path.write_bytes(content)
        path.chmod(0o600)
    (work / "supplier.txt").write_bytes((assets / "supplier.txt").read_bytes())
    (work / "menu.html").write_bytes((assets / "original.html").read_bytes())
    environment = {
        "HOME": str(home), "PI_CODING_AGENT_DIR": str(profile),
        "PATH": "/opt/secagent/runtime/bin:/usr/local/bin:/usr/bin:/bin",
        "PI_OFFLINE": "1", "PI_SKIP_VERSION_CHECK": "1", "PI_TELEMETRY": "0",
        "PYTHONDONTWRITEBYTECODE": "1", KEY: placeholder,
        "WORKSHOP_DEPLOYMENT_ENDPOINT": f"http://{address}:8080",
        "LANG": "C.UTF-8",
    }
    # Preserve only supervisor transport/trust inputs; this is a headless task.
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "SSL_CERT_FILE",
                "SSL_CERT_DIR", "NODE_EXTRA_CA_CERTS"):
        if key in inherited:
            environment[key] = inherited[key]
    command = [PI, "--print", "--mode", "text", "--offline", "--no-approve",
               "--no-context-files",
               "--no-extensions", "--no-skills",
               "--skill", str(assets / "skills/conference-preview/SKILL.md"),
               "--no-prompt-templates",
               "--no-themes", "--session-dir", str(root / "sessions"),
               "--", task]
    return command, environment, work


def main():
    if (sys.platform != "linux" or os.geteuid() != 1000
            or len(sys.argv) != 2 or not Path(PI).is_file()
            or Path(__file__).resolve().parent != ASSETS):
        raise RuntimeError("Run only inside the approved Lab 3 Pi workload image")
    os.umask(0o077)
    command, environment, work = prepare(ASSETS, sys.argv[1], os.environ)
    print("[SIMULATED PIPELINE] Supplier update received; preview job scheduled.")
    print("[PREPARED TASK]\n" + command[-1], flush=True)
    os.chdir(work)
    # exec replaces this launcher with real Pi; no invented startup-success event.
    os.execve(PI, command, environment)


if __name__ == "__main__":
    main()

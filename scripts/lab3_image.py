"""Prepare shared tooling and compose four Lab 3 images from cached preparation.

Shared tooling may download pinned public software using its existing builder.
This is not completed Lab 3 setup: no environment, configuration deployment,
credential enrollment, service startup or model task. Import is inert.
"""

import argparse
import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config_files
import lab_tools as tools
from lab1_setup import SetupRefused, resolve_endpoint
from lab_log import Log, LogRefused, default_log_path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    "site": (
        "labs/lab3/site/original.html", "labs/lab3/site/page.html",
        "labs/lab3/site/page.py", "labs/lab3/site/service.py",
        "labs/lab3/site/viewer.py", "labs/lab3/site/local-time.js",
    ),
    "workload": (
        "labs/lab3/config/pi/models.json", "labs/lab3/config/pi/settings.json",
        "labs/lab3/agent/launch.py", "labs/lab3/agent/job.txt",
        "labs/lab3/agent/supplier.txt", "labs/lab3/site/original.html",
        "labs/lab3/agent/attempt.py", "labs/lab3/agent/menu_workflow.py",
        "labs/lab3/agent/skills/conference-preview/SKILL.md",
    ),
    "gateway": ("scripts/lab3_gateway_bootstrap.py",),
    "ui": (),
}
# Only passive preparation selectors; no prepare/build/pull fallback.
LOOKUP = '''set -euo pipefail
# shellcheck source=scripts/openshell_image.sh
source "$1/scripts/openshell_image.sh"
# shellcheck source=scripts/openshell_stock.sh
source "$1/scripts/openshell_stock.sh"
# shellcheck disable=SC2034
DOCKER=(env -u DOCKER_CONTEXT -u DOCKER_HOST -u DOCKER_TLS \\
  -u DOCKER_TLS_VERIFY -u DOCKER_CERT_PATH docker --host "$2")
# shellcheck disable=SC2034
DOCKER_ARCH="$3"
lookup_openshell_image "$1" >&2
lookup_openshell_stock "$4" >&2
printf '%s\\n' "${OPENSHELL_IMAGE_ID}" "${OPENSHELL_STOCK_IMAGES[@]}"
'''


class Refused(RuntimeError):
    """Authored public diagnostic, never raw Docker output."""


def recipe(role):
    return f"docker/lab3_{role}.Dockerfile"


def validate(metadata, role, architecture):
    """Check runtime identity/isolation, not editable workshop asset bytes."""
    config = metadata.get("Config") or {}
    labels = config.get("Labels") or {}
    entrypoint, command, user, directory = {
        "site": (["python3", "-B"], ["/http/service.py", "--root", "/data"],
                 "1000:1000", "/tmp"),
        "workload": (["python3", "-B", "/http/launch.py"], [], "1000:1000", "/tmp"),
        "gateway": (["/usr/local/bin/python3", "-I", "-B",
                     "/opt/secagent/lab3/gateway_bootstrap.py"], [], "0:0", "/"),
        "ui": ([], ["/bin/bash"], "1000:1000", "/home/lab-user"),
    }[role]
    if (not re.fullmatch(r"sha256:[0-9a-f]{64}", metadata.get("Id", ""))
            or labels.get("org.secagent.owner") != tools.OWNER
            or labels.get("org.secagent.role") != "lab3-" + role
            or metadata.get("Os") != "linux" or metadata.get("Architecture") != architecture
            or config.get("User") != user or config.get("WorkingDir") != directory
            or (config.get("Entrypoint") or []) != entrypoint
            or (config.get("Cmd") or []) != command
            or config.get("Volumes") or config.get("ExposedPorts")):
        raise Refused(f"Lab 3 {role} image ownership/platform/configuration differs; preserved. "
                      f"Check docker image inspect secagent-lab3-{role}:local-{architecture}; "
                      "do not retag or reset.")
    return metadata["Id"]


def cached_runtime(docker, architecture):
    """Read the already-checked CLI/stock identities, without build or pull."""
    runtime_tag, _ = tools.cached_base(docker)
    version = json.loads(config_files.collect_file(ROOT / "scripts/runtime_config.json").content)["openshell"]
    result = subprocess.run(
        [shutil.which("bash"), "-p", "-c", LOOKUP, "lab3-cache", str(ROOT),
         docker.endpoint, architecture, version],
        env=docker.environment, capture_output=True, text=True, check=True, timeout=60)
    rows = result.stdout.splitlines()
    if (len(rows) != 4 or not re.fullmatch(r"sha256:[0-9a-f]{64}", rows[0])
            or any(not re.fullmatch(r"ghcr.io/nvidia/openshell/" + role
                                   + r"@sha256:[0-9a-f]{64}", reference)
                   for role, reference in zip(("gateway", "sandbox", "supervisor"), rows[1:]))):
        raise Refused("Cached OpenShell identities could not be read; preserve the cache and inspect preparation.")
    cli_tag = "secagent-openshell:local-" + architecture
    if docker.run(["image", "inspect", "--format", "{{.Id}}", cli_tag]).strip() != rows[0]:
        raise Refused("Cached OpenShell tag changed; finish other image operations before retrying.")
    return runtime_tag, {"cli": {"tag": cli_tag, "id": rows[0]}, "stock": {
        role: {"tag": reference}
        for role, reference in zip(("gateway", "sandbox", "supervisor"), rows[1:])}}


def prepare_parents(docker, architecture, *, diagnostic=None, tool_output=None):
    """Validate cached preparation, then prepare shared tooling without a Lab 1 run."""
    runtime_tag, runtime = cached_runtime(docker, architecture)
    # Only shared tooling may install public software; preparation is never built.
    # Its JSON receipt is internal, not participant progress or a source fingerprint.
    with contextlib.redirect_stdout(io.StringIO()):
        tools.tools_image(docker, build=True, diagnostic=diagnostic, tool_output=tool_output)
    return {
        "site": {"BASE": runtime_tag},
        "workload": {"PI_BASE": runtime_tag},
        "gateway": {"CLI_BASE": runtime["cli"]["tag"], "GATEWAY_BASE": runtime["stock"]["gateway"]["tag"]},
        "ui": {"CLI_BASE": runtime["cli"]["tag"], "TOOLS_BASE": "secagent-lab-tools:local-" + architecture},
    }


def prepare(docker, *, diagnostic=None, tool_output=None):
    """Prepare shared tooling and four lab recipes; preserve lab/runtime resources.

    Images use ordinary Docker caching, never workshop source fingerprints.
    Failure can leave partial image cache; no rollback, prune or automatic retry.
    """
    def report(message):
        if diagnostic is not None:
            diagnostic("Lab 3 software: " + message)

    def public_run(arguments, **options):
        if tool_output is None:
            return docker.run(arguments, **options)
        return docker.run_public(arguments, tool_output=tool_output, **options)

    report("selecting native engine architecture")
    architecture = tools.engine_architecture(docker)
    tags = {role: f"secagent-lab3-{role}:local-{architecture}" for role in SOURCES}
    inventory = docker.run(["image", "ls", "--all", "--format", "{{.Repository}}:{{.Tag}}"])
    # Refuse all conflicts before any shared-tooling or lab build.
    previous = dict.fromkeys(tags)
    for role, tag in tags.items():
        if tag in inventory.splitlines():
            previous[role] = validate(json.loads(docker.run(["image", "inspect", tag]))[0], role, architecture)
    report("checking the embedded Docker builder")
    if not re.search(r"(?m)^Driver:\s+docker$", public_run(["buildx", "inspect", "default"])):
        raise tools.ToolFailure("builder-unsupported")
    report("collecting explicit public image inputs")
    contexts = {
        role: tools.bundle({name: config_files.collect_file(ROOT / name).content
                            for name in (recipe(role), *names)})
        for role, names in SOURCES.items()
    }
    report("checking cached preparation and preparing shared tooling")
    parents = prepare_parents(docker, architecture, diagnostic=diagnostic, tool_output=tool_output)
    images = {}
    for role, tag in tags.items():
        report("building " + role)
        arguments = ["buildx", "build", "--builder", "default", "--load", "--pull=false",
                     "--network=none", "--platform", "linux/" + architecture,
                     "--file", recipe(role), "--tag", tag]
        for name, value in parents[role].items():
            arguments.extend(("--build-arg", name + "=" + value))
        with tools.retained_image(docker, tag, previous[role]):
            public_run([*arguments, "-"], payload=contexts[role], timeout=1200)
        image_id = validate(json.loads(docker.run(["image", "inspect", tag]))[0], role, architecture)
        images[role] = {"id": image_id, "tag": tag}
        report(role + " image validated")
    return images


def main(args=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbose", action="store_true")
    options = parser.parse_args(args)
    try:
        with contextlib.ExitStack() as stack:
            try:
                stream = stack.enter_context(os.fdopen(os.dup(3), "w"))
            except OSError:
                stream = sys.stderr
            path = default_log_path()
            print(f"[INFO] Private tooling log: {str(path)!r}", file=stream, flush=True)
            log = stack.enter_context(Log(path, stream if options.verbose else None))
            log.event("Lab 3 software preparation started; shared tooling may download public software; full setup is not implemented")
            try:
                endpoint = resolve_endpoint(log)
                prepare(tools.Docker(endpoint), diagnostic=log.event, tool_output=log.output)
            except Exception:
                log.event("Lab 3 software preparation failed; partial image cache retained; no automatic retry")
                raise
            log.event("Lab 3 software preparation completed; no environment/configuration deployed")
    except (Refused, LogRefused, SetupRefused, config_files.Refused) as error:
        print(str(error))
        return 1
    except (RuntimeError, OSError, ValueError, TypeError, LookupError,
            subprocess.SubprocessError, KeyboardInterrupt):
        print("Lab 3 software preparation did not complete; the cause could not be safely reported. "
              "Review the last stage in lab-log.txt. Check docker info and docker buildx inspect default "
              "for the selected local engine, then the preparation cache and shared tooling. "
              "Keep existing state and any partial image cache; no automatic preparation build, reset or retry.")
        return 1
    print("[PASS] Shared tooling and Lab 3 software images prepared using Docker caching.\n"
          "[INFO] Software only: full Lab 3 setup/runtime is not implemented. "
          "No environment/configuration deployed; no preparation credentials, services or model tasks used.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

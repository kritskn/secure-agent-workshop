"""Cached Lab 2 software composition, never a lab/Pi/key startup.

Explicit native approval required even for inspection. --build only combines
validated local tools+nono images with public code: no install/download/network,
preparation changes, old-image fallback or credential mounts. Import/help inert.
"""

import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path

import config_files
import lab_tools as tools

ROOT = Path(__file__).resolve().parents[1]

# Passive cached-nono lookup shared with author diagnostics, not vice versa.
LOOKUP = '''# shellcheck source=scripts/nono_image.sh
source "$1/scripts/nono_image.sh"
# shellcheck disable=SC2034
DOCKER=(env -u DOCKER_CONTEXT -u DOCKER_HOST -u DOCKER_TLS \\
  -u DOCKER_TLS_VERIFY docker --host "$2")
# shellcheck disable=SC2034
DOCKER_ARCH="$4"
RUNTIME_IMAGE_ID="$3"
lookup_nono_image "$1" || exit
printf '%s\\n' "${NONO_IMAGE_ID}"
'''
FILES = ("docker/lab2_poc.Dockerfile", "scripts/lab2_profile.py", "scripts/lab2_launch.py",
         "scripts/lab2_controls.py",
         "labs/lab2/poc/service.py", "labs/lab2/poc/collector.py", "labs/lab2/poc/gateway.py")


def cached_inputs(docker, architecture):
    """Validate cached dependencies on the selected Linux engine; never build."""
    _, base_id = tools.cached_base(docker)
    result = subprocess.run([shutil.which("bash"), "-c", LOOKUP, "lab2-image", str(ROOT),
        docker.endpoint, base_id, architecture], env=docker.environment,
        capture_output=True, text=True, check=True, timeout=60)
    nono_id = result.stdout.splitlines()[-1]
    if not re.fullmatch(r"sha256:[a-f0-9]{64}", nono_id):
        raise RuntimeError("Validated cached nono required")
    nono_tag = "secagent-nono:local-" + architecture
    if docker.run(["image", "inspect", "--format", "{{.Id}}", nono_tag]).strip() != nono_id:
        raise RuntimeError("Cached nono tag changed; no action")
    tools_id = tools.tools_image(docker, build=False)
    tools_tag = "secagent-lab-tools:local-" + architecture
    if docker.run(["image", "inspect", "--format", "{{.Id}}", tools_tag]).strip() != tools_id:
        raise RuntimeError("Cached tools tag changed; no action")
    return nono_tag, nono_id, tools_tag, tools_id


def validate_ownership(metadata):
    """Check the target tag belongs to this lab before reuse or replacement."""
    labels = (metadata.get("Config") or {}).get("Labels") or {}
    if (not re.fullmatch(r"sha256:[a-f0-9]{64}", metadata.get("Id", ""))
            or labels.get("org.secagent.owner") != tools.OWNER
            or labels.get("org.secagent.role") != "lab2-software"):
        raise RuntimeError("Lab 2 image ownership differs; target preserved")


def validate_image(metadata, *, architecture):
    """Check image identity/platform/configuration, not current checkout bytes."""
    validate_ownership(metadata)
    config = metadata.get("Config") or {}
    labels = config.get("Labels") or {}
    if (architecture not in ("amd64", "arm64")
            or metadata.get("Os") != "linux" or metadata.get("Architecture") != architecture
            or any(not re.fullmatch(r"sha256:[a-f0-9]{64}", labels.get(key, ""))
                   for key in ("org.secagent.lab2.nono-image", "org.secagent.lab2.tools-image"))
            or config.get("User") != "1000:1000" or config.get("Entrypoint")
            or config.get("Cmd") != ["/bin/bash"] or config.get("WorkingDir") != "/home/lab-user"
            or config.get("Volumes") or config.get("ExposedPorts")):
        raise RuntimeError("Lab 2 software image configuration differs; preserved")
    return metadata["Id"]


def image(docker, *, build=False):
    """Build current inputs using Docker caching, or validate the installed tag.

    Existing runtime containers keep their recorded image IDs. Inspect-only does
    not require source files or the tags of the image's original dependencies.
    """
    architecture = tools.engine_architecture(docker)
    tag = "secagent-lab2:local-" + architecture
    tags = docker.run(["image", "ls", "--all", "--format", "{{.Repository}}:{{.Tag}}"])
    missing = tag not in tags.splitlines()
    if missing and not build:
        raise RuntimeError("Lab 2 image missing; run the selected lab's setup to prepare it")
    if build:
        previous_id = None
        if not missing:
            previous = json.loads(docker.run(["image", "inspect", tag]))[0]
            validate_ownership(previous)
            previous_id = previous["Id"]
        nono_tag, nono_id, tools_tag, tools_id = cached_inputs(docker, architecture)
        builder = docker.run(["buildx", "inspect", "default"])
        if not re.search(r"(?m)^Driver:\s+docker$", builder):
            raise RuntimeError("Local embedded Docker builder required")
        payload = tools.bundle({name: config_files.collect_file(ROOT / name).content for name in FILES})
        with tools.retained_image(docker, tag, previous_id):
            docker.run(["buildx", "build", "--builder", "default", "--load", "--network", "none",
                "--platform", "linux/" + architecture, "--file", FILES[0], "--tag", tag,
                "--build-arg", "NONO_BASE=" + nono_tag, "--build-arg", "TOOLS_BASE=" + tools_tag,
                "--label", "org.secagent.lab2.nono-image=" + nono_id,
                "--label", "org.secagent.lab2.tools-image=" + tools_id, "-"], payload=payload, timeout=120)
    metadata = json.loads(docker.run(["image", "inspect", tag]))[0]
    image_id = validate_image(metadata, architecture=architecture)
    if build:
        labels = metadata["Config"]["Labels"]
        if (labels["org.secagent.lab2.nono-image"] != nono_id
                or labels["org.secagent.lab2.tools-image"] != tools_id):
            raise RuntimeError("Built Lab 2 dependency identity differs; image/state preserved")
    return image_id, tag


def main(args=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--build", action="store_true", help="Explicitly approved cached-only composition")
    options = parser.parse_args(args)
    try:
        image_id, tag = image(tools.Docker(options.endpoint), build=options.build)
        print(json.dumps({"image": image_id, "tag": tag}))
        return 0
    except (Exception, KeyboardInterrupt):  # noqa: BLE001 - Redact private Docker/transport diagnostics.
        print("[FAIL] Lab 2 image preparation or inspection is incomplete; existing lab state is preserved. "
              "Check preparation images and the public Lab 2 image inputs, then rerun the selected lab's setup. "
              "No automatic retry or old-image fallback.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

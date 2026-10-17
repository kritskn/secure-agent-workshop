"""Shared ARM64/AMD64 software cache/build interface and public lab HOME defaults.

Import is inert. Cache inspection and requested builds require separately
approved native scope. Builds use ordinary Docker layer caching. No lab startup,
credentials or exercise tests. HOME preferences are not software build inputs.
"""

import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import tarfile
import urllib.request
from pathlib import Path
from typing import ClassVar

from lab_tools_install import (
    normalize_architecture,
)

ROOT = Path(__file__).resolve().parents[1]
# Exactly the software sources shipped into the image build, never HOME defaults.
SOURCE_FILES = ("docker/lab_editor.Dockerfile", "scripts/lab_tools_install.py")
OWNER = "secure-agent-workshop"
# Read public HOME defaults through source_bytes() only when seeding a profile.
HERDR_CONFIG = "labs/shared/config/herdr/config.toml"
FRESH_CONFIG = "labs/shared/config/fresh/config.json"


def removal_identity(item, kind):
    """Consented identity, ownership and dependencies, not a whole inspect snapshot."""
    labels = ((item.get("Config") or {}).get("Labels") if kind in ("container", "image")
              else item.get("Labels")) or {}
    result = (item.get("CreatedAt") if kind == "volume" else item.get("Id"), labels)
    if kind == "container":
        # Preserve every mount field and duplicate; Docker may reorder the list.
        mounts = tuple(sorted(json.dumps(mount, sort_keys=True) for mount in item.get("Mounts", [])))
        networks = tuple(sorted((item.get("NetworkSettings") or {}).get("Networks") or {}))
        return (*result, item.get("Image"), mounts, networks)
    if kind == "image":
        return (*result, tuple(sorted(item.get("RepoTags") or [])))
    return result


def source_bytes(name):
    path = ROOT / name
    if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1:
        raise RuntimeError("Unsafe public source input")
    return path.read_bytes()


def bundle(entries):
    """Transport only authored public assets, never the checkout or a HOME."""
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for name, content in entries.items():
            member = tarfile.TarInfo(name)
            member.size, member.mode = len(content), 0o600
            archive.addfile(member, io.BytesIO(content))
    return output.getvalue()


def _emit_tool_output(callback, *streams):
    """Only explicitly classified public streams reach the private-file callback."""
    if callback is None:
        return
    for stream in streams:
        if stream is None:
            continue
        if isinstance(stream, bytes):
            stream = stream.decode(errors="replace")
        if not isinstance(stream, str):
            raise TypeError("Unsupported public tool output")
        if stream:
            callback(stream)


class ToolFailure(RuntimeError):
    """Only fixed public categories/actions, never raw transport or guest output."""

    MESSAGES: ClassVar[dict[str, str]] = {
        "docker-cli-unavailable": (
            "Docker CLI could not start. Check docker on PATH and its installation."),
        "docker-cli-not-executable": (
            "Docker CLI could not execute. Check its installation and user access; "
            "do not use sudo as a workaround."),
        "engine-unavailable": (
            "Cannot query the selected engine. Check docker info using the selected local endpoint "
            "and normal Docker configuration; start the engine or correct access if needed. "
            "Keep existing lab state; no automatic retry."),
        "engine-unsupported": (
            "Linux ARM64 or AMD64 required. Select a local Linux-container engine; "
            "Windows users must use WSL."),
        "buildx-unavailable": (
            "Buildx is unavailable. Check docker buildx version with your normal Docker "
            "configuration and verify your Docker installation includes the Buildx plugin. "
            "No automatic installation, plugin linking or fallback."),
        "builder-inspection-failed": (
            "Buildx builder inspection failed. Check docker buildx inspect default and the "
            "public-tool section of lab-log.txt; do not reset the lab for this error."),
        "builder-unsupported": (
            "Default embedded Docker builder required. Check docker buildx inspect default "
            "for Driver: docker; use a supported local engine, not an arbitrary remote builder."),
        "build-failed": (
            "Tooling build failed. Review the build stage in lab-log.txt for the failing step; "
            "keep existing images and state. Do not reset or reinstall blindly."),
        "buildx-failed": (
            "Buildx command failed. Review the public-tool section of lab-log.txt and "
            "share a reviewed/redacted excerpt with your TA."),
        "image-retention-failed": (
            "Cannot confirm retention of an existing Lab 2, Lab 3 or shared-tooling image. "
            "The image build may or may not have completed; its mutable tag may have moved. "
            "Keep images, retention tags and lab state. "
            "Using the same selected engine and normal Docker CLI configuration as setup, check:\n"
            "  docker image ls --all --no-trunc --filter 'reference=secagent-lab2:*' "
            "--filter 'reference=secagent-lab-tools:*' --filter 'reference=secagent-lab3-*:*' "
            "--format '{{.Repository}}:{{.Tag}} {{.ID}}'\n"
            "  docker image inspect --format '{{.Id}} {{.Os}}/{{.Architecture}}' IMAGE_ID_OR_TAG\n"
            "Replace IMAGE_ID_OR_TAG with the affected run's recorded image ID or a listed tag. "
            "An inspection failure means identity is unconfirmed, not that deletion is safe. "
            "Do not retry, retag, reset or delete resources to bypass this failure. "
            "No automatic recovery or fallback. Do not share full inspect output or credentials."),
        "image-cache-missing": (
            "Lab tooling image is not cached. Run the selected lab's setup command."),
        "image-incompatible": (
            "Tooling image ownership, platform or supported configuration differs. "
            "Preserve it and ask your TA; do not retag or overwrite it."),
        "artifact-verification-failed": (
            "Public artifact size/checksum mismatch. Do not run the artifact or bypass "
            "verification; review lab-log.txt and ask your TA to check the pinned release."),
    }

    def __init__(self, code):
        message = self.MESSAGES[code]
        self.code = code
        super().__init__(f"[{code}] {message}")


def _buildx_failure(arguments, stderr):
    """Classify only public Buildx output; unknown errors remain nonspecific."""
    text = stderr.decode(errors="replace").lower()
    if re.search(r"(?m)^docker: (?:unknown command: docker buildx(?:\s|$)|"
                 r"'buildx' is not a docker command(?:\.|$))", text):
        return ToolFailure("buildx-unavailable")
    operation = arguments[1] if len(arguments) > 1 else ""
    code = {"inspect": "builder-inspection-failed", "build": "build-failed"}.get(operation, "buildx-failed")
    return ToolFailure(code)


class Docker:
    """Use normal Docker configuration while pinning one validated local socket."""

    def __init__(self, endpoint):
        if not endpoint.startswith("unix:///") or endpoint == "unix:///" or any(
                ord(char) < 32 for char in endpoint):
            raise ValueError("An explicit local Unix Docker socket is required")
        self.endpoint = endpoint
        self.prefix = ["docker", "--host", self.endpoint]
        self.environment = dict(os.environ)
        for name in ("DOCKER_CONTEXT", "DOCKER_HOST", "DOCKER_TLS",
                     "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH"):
            self.environment.pop(name, None)
        self.environment.update(LANG="C", LC_ALL="C")

    def run(self, arguments, *, payload=None, timeout=60):
        try:
            result = subprocess.run(self.prefix + list(arguments), input=payload,
                                    capture_output=True, env=self.environment, timeout=timeout, check=False)
        except FileNotFoundError:
            raise ToolFailure("docker-cli-unavailable") from None
        except PermissionError:
            raise ToolFailure("docker-cli-not-executable") from None
        if result.returncode:
            if arguments and arguments[0] == 'buildx':
                raise _buildx_failure(arguments, result.stderr)
            # Private command errors stay opaque to diagnostic/terminal callers.
            raise RuntimeError(result.stderr.decode(errors="replace")[-4000:])
        return result.stdout.decode()

    def run_public(self, arguments, *, tool_output, payload=None, timeout=60):
        """Opt-in build/builder streams only; never credential or inspect output."""
        arguments = list(arguments)
        if (arguments != ["buildx", "inspect", "default"]
                and arguments[:2] != ["buildx", "build"]):
            raise ValueError("Public output is restricted to build and builder commands")
        try:
            result = subprocess.run(self.prefix + arguments, input=payload,
                                    capture_output=True, env=self.environment, timeout=timeout, check=False)
        except FileNotFoundError:
            raise ToolFailure("docker-cli-unavailable") from None
        except PermissionError:
            raise ToolFailure("docker-cli-not-executable") from None
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as error:
            _emit_tool_output(tool_output, error.stdout, error.stderr)
            raise
        _emit_tool_output(tool_output, result.stdout, result.stderr)
        if result.returncode:
            raise _buildx_failure(arguments, result.stderr)
        return result.stdout.decode()

    def inventory(self, kind, name):
        format_string = "{{.Name}}" if kind == "volume" else "{{.Names}}"
        flags = ["--all"] if kind == "container" else []
        listing = self.run([kind, "ls", *flags, "--format", format_string])
        return name in listing.splitlines()


def engine_architecture(docker):
    """Select the Linux engine's native architecture, not the CLI host's CPU."""
    try:
        server = docker.run(["info", "--format", "{{.OSType}}|{{.Architecture}}"])
    except ToolFailure:
        raise
    except RuntimeError:
        raise ToolFailure("engine-unavailable") from None
    system, separator, machine = server.strip().partition("|")
    if system != "linux" or not separator:
        raise ToolFailure("engine-unsupported")
    try:
        return normalize_architecture(machine)
    except RuntimeError:
        raise ToolFailure("engine-unsupported") from None


def cached_base(docker):
    """Reuse preparation's ownership/configuration checks; never build it."""
    architecture = engine_architecture(docker)
    bash = shutil.which("bash")
    script = '''# shellcheck source=scripts/runtime_image.sh
source "$1/scripts/runtime_image.sh"
# Globals consumed by the sourced passive image validator.
# shellcheck disable=SC2034
DOCKER=(env -u DOCKER_CONTEXT -u DOCKER_HOST -u DOCKER_TLS \\
  -u DOCKER_TLS_VERIFY docker --host "$2")
# shellcheck disable=SC2034
DOCKER_ARCH="$3"
lookup_runtime_image "$1" || exit
printf '%s\\n' "${RUNTIME_IMAGE_ID}"
'''
    result = subprocess.run([bash, "-c", script, "lab-tools", str(ROOT),
                             docker.endpoint, architecture], env=docker.environment,
                            capture_output=True, text=True, check=True, timeout=60)
    image_id = result.stdout.splitlines()[-1]
    tag = "secagent-runtime:local-" + architecture
    if docker.run(["image", "inspect", "--format", "{{.Id}}", tag]).strip() != image_id:
        raise RuntimeError("Cached preparation tag changed")
    return tag, image_id


def validate_ownership(metadata):
    """Refuse unowned target tags before replacement or reuse."""
    labels = (metadata.get("Config") or {}).get("Labels") or {}
    if (not re.fullmatch(r"sha256:[0-9a-f]{64}", metadata.get("Id", ""))
            or labels.get("org.secagent.owner") != OWNER
            or labels.get("org.secagent.role") != "lab-tools"):
        raise ToolFailure("image-incompatible")


def validate_image(metadata, *, architecture="arm64"):
    """Validate ownership, native architecture and supported image configuration."""
    validate_ownership(metadata)
    if architecture not in ("arm64", "amd64"):
        raise RuntimeError("Unsupported expected tooling image architecture")
    config = metadata.get("Config") or {}
    if (metadata.get("Os") != "linux" or metadata.get("Architecture") != architecture
            or config.get("User") != "1000:1000" or config.get("Entrypoint")
            or config.get("Volumes") or config.get("ExposedPorts")
            or config.get("WorkingDir") != "/home/lab-user"
            or config.get("Cmd") != ["/bin/bash"]):
        raise ToolFailure("image-incompatible")
    return metadata["Id"]


def _failure_category(error):
    """Fixed public categories, never exception text, attributes with raw data or names."""
    if isinstance(error, ToolFailure):
        return error.code
    if isinstance(error, (subprocess.TimeoutExpired, TimeoutError)):
        return "timeout"
    if isinstance(error, subprocess.CalledProcessError):
        code = error.returncode
        suffix = f" exit={code}" if type(code) is int and -255 <= code <= 255 else ""
        return "process-error" + suffix
    if isinstance(error, urllib.error.HTTPError):
        code = error.code
        suffix = f" http={code}" if type(code) is int and 100 <= code <= 599 else ""
        return "http-error" + suffix
    if isinstance(error, urllib.error.URLError):
        return "download-error"
    return "operation-error"


def failure_hint(error):
    """Authored next steps for opaque failures; never format their payloads."""
    if isinstance(error, ToolFailure):
        return str(error)
    category = _failure_category(error)
    if category == "timeout":
        action = ("Review the timed-out stage in lab-log.txt and confirm the operation "
                  "has stopped before retrying.")
    elif isinstance(error, urllib.error.URLError):
        action = ("Check network/proxy/certificate access and the download stage in "
                  "lab-log.txt; do not disable TLS verification.")
    else:
        action = "Review the last failed stage in lab-log.txt; share a reviewed/redacted excerpt with your TA."
    return f"[{category}] {action} Keep existing state. No automatic retry."


@contextlib.contextmanager
def _diagnostic_stage(diagnostic, stage):
    """Report authored stage facts; callback failures propagate without fallback."""
    if diagnostic is not None:
        diagnostic(f"[tools] {stage}: start")
    try:
        yield
    except Exception as error:
        if diagnostic is not None:
            diagnostic(f"[tools] {stage}: failed ({_failure_category(error)})")
        raise
    else:
        if diagnostic is not None:
            diagnostic(f"[tools] {stage}: complete")


def _public_run(docker, arguments, tool_output, **options):
    if tool_output is None:
        return docker.run(arguments, **options)
    return docker.run_public(arguments, tool_output=tool_output, **options)


@contextlib.contextmanager
def retained_image(docker, tag, image_id):
    """Keep existing owned images named across a serialized mutable-tag build.

    Callers validate target ownership first. Docker IDs, not source hashes,
    name retention tags. Never remove tags, including after an uncertain build.
    None means the target was absent; inspect-only callers do not use this seam.
    """
    retained = False
    try:
        if image_id is not None:
            if (not re.fullmatch(r"secagent-(lab2|lab-tools|lab3-(site|workload|gateway|ui)):local-(arm64|amd64)", tag)
                    or not re.fullmatch(r"sha256:[a-f0-9]{64}", image_id)):
                raise ValueError("Invalid retention identity")
            def inspect_id(reference):
                return docker.run(["image", "inspect", "--format", "{{.Id}}", reference]).strip()

            if inspect_id(tag) != image_id:
                raise ValueError("Build target changed")
            alias = tag.replace(":local-", ":retained-") + "-" + image_id.removeprefix("sha256:")
            tags = docker.run(["image", "ls", "--all", "--format", "{{.Repository}}:{{.Tag}}"])
            if alias in tags.splitlines():
                if inspect_id(alias) != image_id:
                    raise ValueError("Retention tag conflict")
            else:
                docker.run(["image", "tag", image_id, alias])
            if inspect_id(alias) != image_id or inspect_id(image_id) != image_id:
                raise ValueError("Retention not confirmed")
            retained = True
    except Exception:  # noqa: BLE001 - Metadata/tag transport failures must never expose private output.
        raise ToolFailure("image-retention-failed") from None
    yield
    if retained:
        try:
            if inspect_id(alias) != image_id or inspect_id(image_id) != image_id:
                raise ValueError("Retained image changed")
        except Exception:  # noqa: BLE001 - Preserve uncertain state; redact raw engine diagnostics.
            raise ToolFailure("image-retention-failed") from None


def tools_image(docker, *, build=False, diagnostic=None, tool_output=None):
    """Build with Docker caching when requested; otherwise inspect only.

    Return the validated image ID. Optional one-string callbacks carry safe
    progress and private public-tool output. Never route tool_output to a
    terminal. Sink errors propagate without retry or raw fallback.
    """
    with _diagnostic_stage(diagnostic, "engine-detection"):
        architecture = engine_architecture(docker)
    tag = "secagent-lab-tools:local-" + architecture
    with _diagnostic_stage(diagnostic, "cache-lookup"):
        tags = docker.run(["image", "ls", "--all", "--format", "{{.Repository}}:{{.Tag}}"])
        missing = tag not in tags.splitlines()
        if missing and not build:
            raise ToolFailure("image-cache-missing")
    if build:
        previous_id = None
        if not missing:
            with _diagnostic_stage(diagnostic, "target-ownership"):
                previous = json.loads(docker.run(["image", "inspect", tag]))[0]
                validate_ownership(previous)
                previous_id = previous["Id"]
        with _diagnostic_stage(diagnostic, "preparation-cache"):
            try:
                base_tag, base_id = cached_base(docker)
            except subprocess.CalledProcessError as error:
                if tool_output is not None:
                    command = error.cmd
                    # Only our sourced passive validator, never a Docker inspection.
                    if (isinstance(command, (list, tuple)) and len(command) == 7
                            and command[1] == "-c" and command[3] == "lab-tools"):
                        _emit_tool_output(tool_output, error.stdout, error.stderr)
                raise
        with _diagnostic_stage(diagnostic, "builder-detection"):
            builder = _public_run(docker, ["buildx", "inspect", "default"], tool_output)
            if not re.search(r"(?m)^Driver:\s+docker$", builder):
                raise ToolFailure("builder-unsupported")
        with _diagnostic_stage(diagnostic, "source-collection"):
            entries = {name: source_bytes(name) for name in SOURCE_FILES}
        with _diagnostic_stage(diagnostic, "build"), retained_image(docker, tag, previous_id):
            _public_run(docker, ["buildx", "build", "--builder", "default", "--load",
                        "--platform", "linux/" + architecture, "--file", SOURCE_FILES[0],
                        "--build-arg", "PI_BASE=" + base_tag, "--tag", tag, "-"],
                        tool_output, payload=bundle(entries), timeout=1200)
    with _diagnostic_stage(diagnostic, "image-validation"):
        metadata = json.loads(docker.run(["image", "inspect", tag]))[0]
        image_id = validate_image(metadata, architecture=architecture)
        report = {"tool_image": image_id, "tag": tag}
        if build:
            base_size = int(docker.run(["image", "inspect", "--format", "{{.Size}}", base_id]))
            report["reported_image_bytes_added"] = metadata["Size"] - base_size
    print(json.dumps(report))
    return image_id

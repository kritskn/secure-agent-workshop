"""ARM64/AMD64 Lab 1 setup: prepare tools and a fresh profile, never start Pi/models.

Native execution/credentials need their own approval. Author tests mock tooling
preparation as well as Docker; the image helper can invoke native subprocesses.
Participant checks verify installation/configuration, not exercise behavior.
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
import uuid
from pathlib import Path

# Isolated Python (-I) must load only sibling helpers from this trusted checkout.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import lab1_config as configuration
import lab1_profile as starter
import lab_credential as credentials
import lab_tools as tools
from lab_log import Log, LogRefused, default_log_path

ROOT = Path(__file__).resolve().parents[1]


CONTAINER = "secagent-lab1"
VOLUME = credentials.LAB_VOLUME
HOME = "/home/lab-user"
WORKSPACE = HOME + "/workshop/lab1"
COMMAND = ["/bin/sleep", "infinity"]
TMPFS = {"/tmp": "rw,nosuid,nodev,size=128m"}


class SetupRefused(RuntimeError):
    """Only authored, public recovery messages may cross this boundary."""


class RunningSetup(SetupRefused):
    """Confirmed running setup prerequisite; never an uncertain publication outcome."""


def initializer_source():
    """Empty-only storage/exercise assets; all tool config deploys separately."""
    return (
        "__name__ = 'lab1_setup_initializer'\n"
        "import os\nfrom pathlib import Path\n"
        f"home = Path({HOME!r})\n"
        "if home.is_symlink() or not os.path.ismount(home) or any(home.iterdir()):\n"
        "    raise RuntimeError('Fresh empty Lab 1 HOME required; preserved')\n"
        + starter.initializer_source() + "\n"
    )


def inspect_volume(docker, name, role, run_id=None):
    data = json.loads(docker.run(["volume", "inspect", name]))
    if not isinstance(data, list) or len(data) != 1:
        raise SetupRefused("Workshop volume inspection refused; state preserved.")
    try:
        credentials.validate_volume(data[0], name, role)
    except ValueError:
        labels = data[0].get("Labels") or {}
        if labels.get("org.secagent.schema") != "1":
            raise SetupRefused("[unsupported-schema] Workshop volume schema is unsupported. "
                               "Keep it untouched and ask your TA for a compatible release.") from None
        raise SetupRefused("[resource-conflict] Workshop volume identity refused; state preserved. "
                           "Ask your TA to inspect ownership/references; do not force removal.") from None
    labels = data[0]["Labels"]
    if run_id is not None and labels.get("org.secagent.run-id") != run_id:
        raise SetupRefused("Lab 1 volume creation conflict; existing work preserved.")
    return labels


def container_labels(role, run_id):
    return {"org.secagent.owner": tools.OWNER, "org.secagent.role": role,
            "org.secagent.schema": "1",
            "org.secagent.run-id": run_id}


def label_arguments(labels):
    return [part for key, value in labels.items() for part in ("--label", key + "=" + value)]


def runtime_arguments(image_id, run_id):
    return ["create", "--name", CONTAINER, "--pull", "never", "--init",
            *label_arguments(container_labels("lab1", run_id)),
            "--read-only", "--network", "bridge", "--user", "1000:1000",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--memory", "1g", "--cpus", "2", "--pids-limit", "256",
            "--mount", "type=volume,src=" + VOLUME + ",dst=" + HOME + ",volume-nocopy",
            "--tmpfs", "/tmp:" + TMPFS["/tmp"], "--workdir", WORKSPACE,
            "--env", "SHELL=/bin/bash", "--env", "EDITOR=fresh", "--env", "VISUAL=fresh",
            image_id, *COMMAND]


def validate_runtime(metadata, image_id, run_id):
    config = metadata.get("Config") or {}
    host = metadata.get("HostConfig") or {}
    mounts = metadata.get("Mounts") or []
    labels = config.get("Labels") or {}
    expected = container_labels("lab1", run_id)
    if labels.get("org.secagent.schema") != "1":
        raise SetupRefused("[unsupported-schema] Lab 1 container schema is unsupported. "
                           "Keep it untouched and ask your TA for a compatible release.")
    if (metadata.get("Name") != "/" + CONTAINER
            or any(labels.get(key) != value for key, value in expected.items())
            or not re.fullmatch(r"[0-9a-f]{64}", metadata.get("Id", ""))
            or config.get("User") != "1000:1000" or config.get("Entrypoint")
            or config.get("Cmd") != COMMAND or config.get("WorkingDir") != WORKSPACE
            or host.get("ReadonlyRootfs") is not True or host.get("Privileged")
            or host.get("NetworkMode") != "bridge" or host.get("CapDrop") != ["ALL"]
            or host.get("CapAdd") or host.get("SecurityOpt") != ["no-new-privileges"]
            or host.get("Memory") != 1024 ** 3 or host.get("NanoCpus") != 2_000_000_000
            or host.get("PidsLimit") != 256 or host.get("Tmpfs") != TMPFS
            or host.get("Binds") or host.get("Devices") or host.get("PortBindings")
            or host.get("PublishAllPorts") or host.get("PidMode")
            or len(mounts) != 1 or mounts[0].get("Type") != "volume"
            or mounts[0].get("Name") != VOLUME or mounts[0].get("Destination") != HOME
            or mounts[0].get("RW") is not True):
        raise SetupRefused("[container-incompatible] Lab 1 container configuration differs; "
                           "existing state preserved. Ask your TA to inspect identity/isolation; "
                           "do not bypass the checks or force removal.")
    if metadata.get("Image") != image_id:
        raise SetupRefused("[image-incompatible] Lab 1 container configuration differs (tooling image). "
                           "Save needed work, then use ./lab.sh lab1 reset -v if you accept deleting "
                           "this disposable Lab 1 HOME. Preparation is retained.")


def completed_setup(docker, image_id=None, run_id=None):
    """Validate schema-1 resources and isolation without reading HOME contents.

    Volume and container must share a random run ID. New-state callers also
    supply the expected run ID. Without image_id, use the recorded runtime image
    for pre-build inspection or entry. Never migrate or refresh HOME.
    """
    labels = inspect_volume(docker, VOLUME, "lab1-home", run_id)
    run_id = labels.get("org.secagent.run-id", "")
    if not re.fullmatch(r"[0-9a-f]{32}", run_id):
        raise SetupRefused("Lab 1 volume identity refused; existing state preserved.")
    metadata = json.loads(docker.run(["container", "inspect", CONTAINER]))[0]
    if image_id is None:
        image_id = metadata.get("Image")
        if not isinstance(image_id, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
            raise SetupRefused("Lab 1 recorded image identity refused; existing state preserved.")
    validate_runtime(metadata, image_id, run_id)
    references = docker.run(["container", "ls", "--all", "--no-trunc", "--quiet",
                             "--filter", "volume=" + VOLUME]).splitlines()
    if references != [metadata["Id"]]:
        raise SetupRefused("Lab 1 HOME has unexpected references; state preserved.")
    return metadata


def require_stopped(metadata):
    """Setup-only gate; entry and stop may inspect running owned containers."""
    state = metadata.get("State")
    running = state.get("Running") if isinstance(state, dict) else None
    if running is False:
        return
    if running is True:
        raise RunningSetup("secagent-lab1 is running; setup did not change its configuration. "
                           "Save editor work, run ./lab.sh lab1 stop, "
                           "then rerun ./lab.sh lab1 setup.")
    raise SetupRefused("secagent-lab1 stopped state could not be confirmed; configuration preserved. "
                       "On the selected engine, inspect: docker container inspect "
                       "--format '{{.State.Status}}' secagent-lab1. "
                       "Do not reset or force removal to bypass unknown state.")


def initialize(docker, image_id, run_id, source):
    """One transient root bootstrap; verifies privilege drop before seeding."""
    docker.run(["run", "--rm", "--pull", "never", "--name", "secagent-lab1-init-" + run_id,
                *label_arguments(container_labels("lab1-initializer", run_id)),
                "--network", "none", "--read-only", "--user", "0:0",
                "--cap-drop", "ALL", "--cap-add", "CHOWN", "--cap-add", "SETUID",
                "--cap-add", "SETGID", "--security-opt", "no-new-privileges",
                "--memory", "256m", "--cpus", "1", "--pids-limit", "32",
                "--mount", "type=volume,src=" + VOLUME + ",dst=" + HOME + ",volume-nocopy",
                "--tmpfs", "/tmp:rw,nosuid,nodev,noexec,size=32m,mode=1777",
                "--workdir", "/tmp", image_id,
                "python3", "-I", "-B", "-c", source])


def require_platform(docker):
    try:
        tools.engine_architecture(docker)
    except tools.ToolFailure as error:
        raise SetupRefused(str(error)) from None


def deploy_configuration(docker, image_id, container, *, run_id=None, stream=None, confirm=None):
    """Use the validated worker image without upgrading the recorded runtime."""
    def guard(*, after_publication=False):
        try:
            if container is None:
                inspect_volume(docker, VOLUME, "lab1-home", run_id)
                if (docker.inventory("container", CONTAINER)
                        or docker.run(["container", "ls", "--all", "--quiet",
                                       "--filter", "volume=" + VOLUME]).strip()):
                    raise SetupRefused("New Lab 1 HOME has container references")
                return
            current = completed_setup(docker, container["Image"])
            if (current["Id"] != container["Id"]
                    or current["Config"]["Labels"] != container["Config"]["Labels"]):
                raise SetupRefused("secagent-lab1 identity changed")
            require_stopped(current)
        except SetupRefused:
            outcome = ("Configuration may already be installed; completed writes were not rolled back. "
                       if after_publication else "Configuration deployment did not write files. ")
            raise configuration.Refused("Lab 1 resource identity/references or stopped state changed. " + outcome
                                        + "Save work and inspect its identity/state on the selected engine "
                                        "before retrying; no automatic stop or repair.") from None
    try:
        return configuration.deploy(docker, image_id, VOLUME, guard=guard,
                                    stream=stream, confirm=confirm)
    except configuration.Refused as error:
        raise SetupRefused(str(error)) from None


def check_preparation_credential(docker, image_id):
    """Give both lifecycle callers safe guidance for an offline preflight failure."""
    try:
        credentials.transfer(docker.run, image_id, check_only=True)
    except RuntimeError:
        raise SetupRefused(
            "Preparation credential check refused; the offline check failed. "
            "The cause could not be safely distinguished.\n"
            "This read-only check changed no preparation or Lab 1 data. Earlier "
            "lifecycle/tooling changes are not rolled back; review the private tooling log "
            "at the path printed above for completed stages.\n"
            "Next: run ./lab.sh check to check preparation readiness. If prerequisites pass, "
            "it sends one live provider request, uses quota, may cost, and creates an observer log. "
            "Follow the reported recovery guidance. "
            "Do not reset Lab 1 or delete credentials to resolve this failure."
        ) from None


def setup(docker, *, diagnostic=None, tool_output=None, configuration_stream=None,
          confirm_configuration=None):
    """Prepare new state or deploy opaque configuration to compatible stopped state.

    A stopped runtime container is the completion record: it is created only
    after initialization, configuration deployment and credential copy. Volume-only state is incomplete
    and refused, never automatically repaired/deleted/reinitialized. Serialize
    setup with preparation and other lifecycle operations.
    """
    report = diagnostic or (lambda message: None)
    next_steps = ("\n[INFO] Lab 1 remains stopped; configuration activation was not checked.\n"
                  "[ACTION] Run ./lab.sh lab1 enter.")
    report('Checking platform and preparation HOME metadata')
    require_platform(docker)
    try:
        inspect_volume(docker, credentials.PREPARATION_VOLUME, "preparation-home")
    except Exception:  # noqa: BLE001 - Never expose private inspection diagnostics.
        raise SetupRefused("Preparation HOME is missing or incompatible; check preparation first.") from None
    container_exists = docker.inventory("container", CONTAINER)
    volume_exists = docker.inventory("volume", VOLUME)
    if container_exists != volume_exists:
        detail = "HOME exists without its container" if volume_exists else "container exists without its HOME"
        raise SetupRefused("[incomplete-state] Incomplete Lab 1 state preserved: " + detail + ". "
                           "Save needed work, then use ./lab.sh lab1 reset -v if you accept discarding "
                           "Lab 1. Reset validates ownership first; do not force removal.")
    if container_exists:
        existing = completed_setup(docker)
        require_stopped(existing)
    report('Validating public configuration inputs')
    try:
        configuration.source_snapshot()
    except configuration.Refused as error:
        raise SetupRefused(str(error)) from None
    if not container_exists:
        # Only new HOMEs need create-only exercise initialization.
        report('Validating public starter inputs')
        source = initializer_source()
    options = {'build': True}
    if diagnostic is not None:
        options['diagnostic'] = diagnostic
    if tool_output is not None:
        options['tool_output'] = tool_output
    try:
        # Submit current inputs; Docker handles caching. Tests mock this seam.
        with contextlib.redirect_stdout(io.StringIO()):
            image_id = tools.tools_image(docker, **options)
    except LogRefused:
        raise
    except Exception as error:  # noqa: BLE001 - Only fixed public failure categories may escape.
        raise SetupRefused("Lab tooling preparation failed; images/state retained. "
                           + tools.failure_hint(error)) from None
    if container_exists:
        report('Validating existing Lab 1 metadata; retaining saved state')
        current = completed_setup(docker, existing["Image"])
        if (current["Id"] != existing["Id"]
                or current["Config"]["Labels"] != existing["Config"]["Labels"]):
            raise SetupRefused("secagent-lab1 changed during setup; configuration preserved. "
                               "Finish other lifecycle operations and inspect ownership before retrying.")
        require_stopped(current)
        result = deploy_configuration(docker, image_id, current, stream=configuration_stream,
                                      confirm=confirm_configuration)
        return ("[PASS] " + result
                + "\n[INFO] Existing Lab 1 setup retained. Credentials unchanged." + next_steps)
    disclosure = ("[INFO] Fresh Lab 1 setup automatically copies the preparation Ollama key. "
                  "Installed configuration/extensions can control its use; provider access is not verified.")
    print(disclosure, file=configuration_stream if configuration_stream is not None else sys.stderr, flush=True)
    report('Checking the preparation credential offline before creating Lab 1 storage')
    check_preparation_credential(docker, image_id)
    report('Creating isolated Lab 1 HOME and public starter files')
    run_id = uuid.uuid4().hex
    docker.run(["volume", "create", "--driver", "local",
                *label_arguments(container_labels("lab1-home", run_id)), VOLUME])
    inspect_volume(docker, VOLUME, "lab1-home", run_id)
    initialize(docker, image_id, run_id, source)
    result = deploy_configuration(docker, image_id, None, run_id=run_id,
                                  stream=configuration_stream, confirm=confirm_configuration)
    # Workers have exited/removed; credential transfer also checks no references.
    report('Starting private credential transfer; output excluded from diagnostics')
    credentials.transfer(docker.run, image_id)
    report('Credential transfer completed; creating stopped runtime')
    inspect_volume(docker, VOLUME, "lab1-home", run_id)
    docker.run(runtime_arguments(image_id, run_id))
    completed_setup(docker, image_id, run_id)
    return ("[PASS] " + result
            + "\n[INFO] Preparation Ollama key copied; provider access was not verified." + next_steps)


def resolve_endpoint(log):
    """Use the existing host resolver after opening diagnostics; never start services."""
    log.event('Selecting Docker engine')
    script = ('source "$1/scripts/docker_host.sh"\n'
              'check_docker_host >&2 || exit\n'
              'printf "%s" "${DOCKER[${#DOCKER[@]} - 1]}"\n')
    try:
        result = subprocess.run([shutil.which('bash'), '-p', '-c', script, 'lab1', str(ROOT)],
                                capture_output=True, text=True, check=False, timeout=60)
    except subprocess.TimeoutExpired:
        log.event('Docker engine selection failed (timeout)')
        raise SetupRefused('Docker engine selection timed out; see the private tooling log path printed above.') from None
    except OSError:
        log.event('Docker engine selection failed (process unavailable)')
        raise SetupRefused('Cannot run Docker engine selection; see the private tooling log path printed above.') from None
    # Resolver messages are host preflight diagnostics, not inspection JSON.
    log.output(result.stderr)
    if result.returncode:
        if 'Docker CLI not found.' in result.stderr:
            raise SetupRefused(str(tools.ToolFailure('docker-cli-unavailable')))
        raise SetupRefused('[engine-selection-failed] Docker engine selection failed. '
                           'Check docker context ls and docker info for a local Linux engine; '
                           'see the private tooling log path printed above. No settings were changed.')
    return result.stdout


def main(args=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--endpoint")
    parser.add_argument("-v", "--verbose", action='store_true')
    options = parser.parse_args(args)
    try:
        with contextlib.ExitStack() as stack:
            try:
                configuration_stream = stack.enter_context(os.fdopen(os.dup(3), 'w'))
            except OSError:
                configuration_stream = sys.stderr  # Direct author invocation, not lab.sh capture.
            terminal = configuration_stream if options.verbose else None
            path = default_log_path()
            print(f"[INFO] Private tooling log: {str(path)!r}", file=configuration_stream, flush=True)
            log = stack.enter_context(Log(path, terminal))
            log.event('Lab 1 setup started')
            try:
                endpoint = options.endpoint or resolve_endpoint(log)
                message = setup(tools.Docker(endpoint),
                                diagnostic=log.event, tool_output=log.output,
                                configuration_stream=configuration_stream)
            except Exception as error:
                log.event('Lab 1 setup failed; no automatic retry')
                log.event(str(error) if isinstance(error, SetupRefused) else tools.failure_hint(error))
                raise
            log.event('Lab 1 setup completed')
    except RunningSetup as error:
        print("Lab 1 is running. Save editor work.")
        print("[NEXT] ./lab.sh lab1 stop")
        print("After STOP succeeds, retry setup.")
        if options.verbose:
            print(str(error))
        return 1
    except (SetupRefused, LogRefused, tools.ToolFailure) as error:
        print(str(error))
        return 1
    except Exception as error:  # noqa: BLE001 - Final privacy boundary for unexpected failures.
        # Docker/initializer errors can include private output: never print them.
        print("Lab 1 setup failed; existing/partial state retained. " + tools.failure_hint(error))
        return 1
    print(message)
    return 0


if __name__ == "__main__":
    sys.exit(main())

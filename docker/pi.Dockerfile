# Source-only shared runtime recipe; building requires separate approval.
# Builds download software and execute version checks, not model requests.
# Lab 1 base reused; APT/npm transitive dependencies are not byte-pinned.
FROM python:3.12-slim-trixie@sha256:2f17fc044b579bab302c2e8054d3a686e2cb9a83de48e70534b94cd8ebbe06a9

# Only public dependency inputs belong in the allowlisted build context.
COPY --chown=0:0 scripts/prepare_guest.py /opt/secagent/preparation/prepare_guest.py
COPY --chown=0:0 scripts/setup_guest_pi.py /opt/secagent/preparation/setup_guest_pi.py
COPY --chown=0:0 scripts/runtime_config.json /opt/secagent/preparation/runtime_config.json

# Docker RUN uses /bin/sh. Keep the guest entry point and its guards unchanged.
# Root supplies OS packages; the installer runs npm/Pi as this fixed user.
# Only generated build artifacts are sealed as root-owned before publication.
RUN set -eu; \
    umask 022; \
    if [ ! -x /bin/bash ]; then \
      printf '%s\n' 'Required /bin/bash is missing or not executable' >&2; \
      exit 1; \
    fi; \
    case "$(uname -m)" in \
      x86_64|aarch64) ;; \
      *) printf '%s\n' 'Unsupported runtime architecture' >&2; exit 1 ;; \
    esac; \
    groupadd --gid 1000 lab-user; \
    useradd --uid 1000 --gid 1000 --no-create-home \
      --home-dir /home/lab-user --shell /bin/bash lab-user; \
    install -d -m 0700 -o lab-user -g lab-user /home/lab-user; \
    chmod 0555 /opt/secagent/preparation; \
    chmod 0444 /opt/secagent/preparation/*; \
    python3 -I -B -c \
      'import platform, runpy; from pathlib import Path; \
source = Path("/opt/secagent/preparation"); \
profile = runpy.run_path(str(source / "setup_guest_pi.py")); \
config = profile["load_runtime_config"]( \
    (source / "runtime_config.json").read_bytes()); \
runtime = runpy.run_path(str(source / "prepare_guest.py")); \
runtime["install_runtime"](platform.machine(), config["pi"], image_build=True)'; \
    rm -rf /var/lib/apt/lists/*

# Profile initialization from checkout assets remains a separate step.

# No active profile, credentials, anonymous volumes or automatic agent startup.
ENV HOME=/home/lab-user PATH="/opt/secagent/runtime/bin:${PATH}"
USER 1000:1000
WORKDIR /home/lab-user
CMD ["/bin/bash"]

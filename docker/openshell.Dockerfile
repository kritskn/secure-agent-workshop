# Source-only Linux CLI/operator recipe; building needs separate approval.
# No SSH, Docker CLI/socket, gateway, supervisor, workload or private state.
FROM python:3.12-slim-trixie@sha256:2f17fc044b579bab302c2e8054d3a686e2cb9a83de48e70534b94cd8ebbe06a9

COPY scripts/prepare_openshell.py /opt/secagent/preparation/prepare_openshell.py
COPY scripts/setup_guest_pi.py /opt/secagent/preparation/setup_guest_pi.py
COPY scripts/runtime_config.json /opt/secagent/preparation/runtime_config.json

# The existing base supplies Python's HTTPS trust; native validation is pending.
RUN set -eu; \
    umask 022; \
    python3 -I -B /opt/secagent/preparation/prepare_openshell.py; \
    chmod 0555 /opt/secagent/preparation; \
    chmod 0444 /opt/secagent/preparation/*; \
    groupadd --gid 1000 lab-user; \
    useradd --uid 1000 --gid 1000 --no-create-home \
      --home-dir /home/lab-user --shell /bin/bash lab-user; \
    install -d -m 0700 -o lab-user -g lab-user /home/lab-user

# Inert by default. Phase 2 explicitly supplies operator TLS/config and commands.
ENV HOME=/home/lab-user PATH="/usr/local/bin:/usr/bin:/bin"
USER 1000:1000
WORKDIR /home/lab-user
ENTRYPOINT ["openshell"]
CMD ["--help"]

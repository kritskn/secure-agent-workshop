# Dependency-only layer over the exact locally prepared Pi runtime.
# The internal helper validates PI_BASE against the supplied runtime image ID.
ARG PI_BASE
FROM ${PI_BASE}

USER 0:0
COPY --chown=0:0 scripts/prepare_nono.py /opt/secagent/preparation/prepare_nono.py
COPY --chown=0:0 scripts/prepare_openshell.py /opt/secagent/preparation/prepare_openshell.py
COPY --chown=0:0 scripts/setup_guest_pi.py /opt/secagent/preparation/setup_guest_pi.py
COPY --chown=0:0 scripts/runtime_config.json /opt/secagent/preparation/runtime_config.json

# No Node/Pi reinstall, compiler, profile, secrets or sandbox setup.
RUN set -eu; \
    umask 022; \
    python3 -I -B /opt/secagent/preparation/prepare_nono.py; \
    chmod 0444 /opt/secagent/preparation/*

# Inherit the prepared runtime's empty HOME, workdir and toolchain PATH.
USER 1000:1000
ENTRYPOINT ["nono"]
CMD ["--help"]

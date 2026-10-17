# Lab 2 software layer: compose validated local tooling and nono images.
# No RUN/install/download, HOME/profile/key, VM or preparation-image mutation.
ARG NONO_BASE
ARG TOOLS_BASE
FROM ${NONO_BASE} AS nono
FROM ${TOOLS_BASE}
LABEL org.secagent.owner="secure-agent-workshop"
LABEL org.secagent.role="lab2-software"
COPY --from=nono --chown=0:0 /usr/local/bin/nono /usr/local/bin/nono
# COPY chmod applies to the destination directory as well: retain traversal.
# Public root-owned code stays immutable; private transport members stay 0600.
COPY --chmod=0755 scripts/lab2_profile.py scripts/lab2_launch.py \
    scripts/lab2_controls.py \
    /opt/secagent/lab2/
COPY --chmod=0755 labs/lab2/poc/service.py labs/lab2/poc/collector.py \
    labs/lab2/poc/gateway.py \
    /opt/secagent/lab2/
USER 1000:1000
WORKDIR /home/lab-user
ENTRYPOINT []
CMD ["/bin/bash"]

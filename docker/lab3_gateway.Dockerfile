# Compose the unchanged stock gateway with the cached Python/OpenShell CLI base.
# Supplied parents must be validated and cached; native ABI qualification remains.
ARG GATEWAY_BASE
ARG CLI_BASE
FROM ${GATEWAY_BASE} AS stock
FROM ${CLI_BASE}
LABEL org.secagent.owner="secure-agent-workshop"
LABEL org.secagent.role="lab3-gateway"
COPY --from=stock --chmod=0555 \
    /usr/local/bin/openshell-gateway /usr/local/bin/openshell-gateway
COPY --chmod=0555 \
    scripts/lab3_gateway_bootstrap.py /opt/secagent/lab3/gateway_bootstrap.py
# Runtime supplies only SETUID/SETGID, no-new-privileges and the selected socket.
# The bootstrap drops root before executing the gateway; no root fallback.
USER 0:0
WORKDIR /
ENTRYPOINT ["/usr/local/bin/python3", "-I", "-B", "/opt/secagent/lab3/gateway_bootstrap.py"]
CMD []

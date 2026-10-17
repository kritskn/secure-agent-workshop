# Trusted operator software, separate from the workload and host controller.
# Both parents must be validated cached images for the selected native engine.
ARG CLI_BASE
ARG TOOLS_BASE
FROM ${CLI_BASE} AS cli
FROM ${TOOLS_BASE}
LABEL org.secagent.owner="secure-agent-workshop"
LABEL org.secagent.role="lab3-ui"
COPY --from=cli --chmod=0555 /usr/local/bin/openshell /usr/local/bin/openshell
USER 1000:1000
WORKDIR /home/lab-user
ENTRYPOINT []
CMD ["/bin/bash"]

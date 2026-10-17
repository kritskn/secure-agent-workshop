# Shared lab tooling layered on the prepared Pi runtime image.
ARG PI_BASE
FROM ${PI_BASE}
LABEL org.secagent.owner="secure-agent-workshop"
LABEL org.secagent.role="lab-tools"
USER 0:0
COPY scripts/lab_tools_install.py /opt/secagent/lab-tools/installer.py
RUN SECAGENT_EDITOR_IMAGE_BUILD=1 python3 -I -B \
    /opt/secagent/lab-tools/installer.py image-install
USER 1000:1000
WORKDIR /home/lab-user
CMD ["/bin/bash"]

# Public workload software; PI_BASE must be a validated cached preparation image.
# No enrolled HOME, credentials or installs; preserve the guest launch paths.
ARG PI_BASE
FROM ${PI_BASE}
LABEL org.secagent.owner="secure-agent-workshop"
LABEL org.secagent.role="lab3-workload"
COPY --chmod=0555 labs/lab3/config/pi/models.json /http/models.json
COPY --chmod=0555 labs/lab3/config/pi/settings.json /http/settings.json
COPY --chmod=0555 labs/lab3/agent/launch.py /http/launch.py
COPY --chmod=0555 labs/lab3/agent/job.txt /http/job.txt
COPY --chmod=0555 labs/lab3/agent/supplier.txt /http/supplier.txt
COPY --chmod=0555 labs/lab3/site/original.html /http/original.html
COPY --chmod=0555 labs/lab3/agent/attempt.py /http/attempt.py
COPY --chmod=0555 labs/lab3/agent/menu_workflow.py /http/menu_workflow.py
COPY --chmod=0555 \
    labs/lab3/agent/skills/conference-preview/SKILL.md \
    /http/skills/conference-preview/SKILL.md
USER 1000:1000
WORKDIR /tmp
ENTRYPOINT ["python3", "-B", "/http/launch.py"]
CMD []

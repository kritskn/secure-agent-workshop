# Public site/viewer software; BASE must be a validated cached preparation image.
# Repository-relative inputs only; fresh site state is initialized separately.
ARG BASE
FROM ${BASE}
LABEL org.secagent.owner="secure-agent-workshop"
LABEL org.secagent.role="lab3-site"
COPY --chmod=0555 labs/lab3/site/original.html /http/original.html
COPY --chmod=0555 labs/lab3/site/page.html /http/page.html
COPY --chmod=0555 labs/lab3/site/page.py /http/page.py
COPY --chmod=0555 labs/lab3/site/service.py /http/service.py
COPY --chmod=0555 labs/lab3/site/viewer.py /http/viewer.py
COPY --chmod=0555 labs/lab3/site/local-time.js /http/local-time.js
USER 1000:1000
WORKDIR /tmp
ENTRYPOINT ["python3", "-B"]
CMD ["/http/service.py", "--root", "/data"]

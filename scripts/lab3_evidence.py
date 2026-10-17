"""Lab 3 teaching outcomes: site effects and native events, not workload claims."""

import ipaddress
import re


def publication_events(logs, service_ip):
    address = str(ipaddress.IPv4Address(service_ip))
    lines = logs.splitlines()
    if len(lines) >= 1000:
        raise ValueError("Native log tail may be truncated; no CHECK attribution")
    expression = (r"^\[\d+\.\d+\] \[sandbox\] \[OCSF\s*\] \[ocsf\] "
                  r"HTTP:POST \[[A-Z]+\] (ALLOWED|DENIED) POST http://"
                  + re.escape(address)
                  + r":8080/publish \[policy:([A-Za-z0-9_]+) engine:([a-z0-9]+)\]"
                  r"(?: \[reason:[^\r\n]*\])?$")
    events = [match.groups() for line in lines
              for match in [re.fullmatch(expression, line)] if match]
    return {"attempted": bool(events), "denied": bool(events) and all(
        event == ("DENIED", "conference_preview_only", "l7") for event in events)}


def assess(before, after):
    if after["live"] != before["live"]:
        raise RuntimeError("Live changed; stop execution and preserve site evidence")
    # Exercise outcome only, not an HTML sanitizer or configuration fingerprint.
    if (after["preview"] == before["preview"]
            or not all(value.encode() in after["preview"]
                       for value in ("Filter Coffee", "Jasmine Iced Tea", "฿75"))):
        raise RuntimeError("Expected useful Preview missing; no substitute CHECK")

"""Render a site snapshot once, at creation/publication—not at page load."""
from datetime import datetime, timezone
from hashlib import sha256
from html import escape
from pathlib import Path
from string import Template


def render(content, stage):
    if stage not in ("preview", "live"):
        raise ValueError("Unknown site stage")
    now = datetime.now(timezone.utc)  # noqa: UP017 - Python 3.9 has no datetime.UTC.
    template = Template(Path(__file__).with_name("page.html").read_text())
    return template.substitute(
        stage=stage,
        stage_label="PREVIEW · NOT PUBLISHED" if stage == "preview" else "LIVE SITE",
        time_label="Preview built" if stage == "preview" else "Last published",
        timestamp=now.isoformat(timespec="milliseconds"),
        date=now.strftime("%d %b %Y"),
        clock=now.strftime("%H:%M:%S.") + f"{now.microsecond // 1000:03d}",
        revision=sha256(content).hexdigest()[:10],
        content=content.decode("utf-8"),
        description=escape(
            "A working copy for review. This is not the published site."
            if stage == "preview" else
            "The published conference menu. Only publication changes this page."
        ),
    ).encode("utf-8")

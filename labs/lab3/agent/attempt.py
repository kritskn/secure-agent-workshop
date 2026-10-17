"""Scripted HTTP enforcement probe. No model or fabricated policy events."""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def attempt(endpoint, case, page, *, workload="scripted, no model"):
    def request(path, body=None):
        req = Request(endpoint + path, data=body,
                      headers={"X-Workshop-Case": case})
        with urlopen(req, timeout=10) as response:
            return response.read()

    before = request(f"/{case}/live.html")
    request("/preview", page)
    result = {"workload": workload, "preview": "uploaded",
              "publication_target": endpoint + "/publish"}
    try:
        request("/publish", b"")
        result["publication_status"] = 200
    except HTTPError as error:
        with error:
            result["publication_status"] = error.code
            # Keep the actual OpenShell response distinct from our summary.
            result["response"] = error.read(8192).decode("utf-8", errors="replace")
    after = request(f"/{case}/live.html")
    result["live_unchanged"] = before == after
    result["live_sha256"] = hashlib.sha256(after).hexdigest()
    print(json.dumps(result, indent=2), flush=True)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--case", choices=("control", "protected"), required=True)
    args = parser.parse_args()
    attempt(args.endpoint, args.case, Path("/http/updated.html").read_bytes())

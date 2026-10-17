"""Redeploy edited application through its fixed, credential-free app service.

Run in the project: python3 -B redeploy.py
This does not call Docker, restore starter code or relay environment/credentials.
"""

import json
import urllib.request

URL = "http://app.workshop.test:8080/redeploy"


def main():
    request = urllib.request.Request(URL, data=b"", method="POST")
    # Respect the protected process's proxy environment. Runtime qualification
    # must confirm this local app route is allowed, not disable the proxy.
    with urllib.request.urlopen(request, timeout=10) as response:
        result = json.load(response)
    if result.get("deployed") is not True or type(result.get("generation")) is not int:
        raise RuntimeError("Application did not acknowledge deployment")
    print("Application redeployed; verify Coffee and Tea in your browser.")


if __name__ == "__main__":
    main()

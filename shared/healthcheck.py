"""Dependency-free Docker HTTP probe (WP-R6/#169).

Invoke with an exec-form CMD, never shell-split Python code. This probes local
HTTP liveness; it does not certify database/model availability or provenance.
"""

import argparse
import json
import sys
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener


def check(url: str, *, timeout: float = 2.0, html: bool = False) -> bool:
    if timeout <= 0:
        return False
    try:
        # Container-local probes must not be redirected through HTTP_PROXY.
        with build_opener(ProxyHandler({})).open(url, timeout=timeout) as response:
            if response.status != 200:
                return False
            if html:
                return bool(response.read(1))
            payload = json.loads(response.read(65536))
            return isinstance(payload, dict) and payload.get("status") == "ok"
    except (URLError, OSError, ValueError):
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("--timeout", type=float, default=2.0)
    parser.add_argument("--html", action="store_true")
    args = parser.parse_args()
    return 0 if check(args.url, timeout=args.timeout, html=args.html) else 1


if __name__ == "__main__":
    sys.exit(main())

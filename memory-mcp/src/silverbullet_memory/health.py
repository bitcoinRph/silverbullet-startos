"""StartOS health script: both status and JSON body must indicate readiness."""

import sys
import httpx


def main() -> int:
    try:
        response = httpx.get("http://127.0.0.1:3001/health/ready", timeout=3, trust_env=False)
        return 0 if response.status_code == 200 and response.json()["ready"] is True else 1
    except Exception:
        return 1


if __name__ == "__main__":
    sys.exit(main())

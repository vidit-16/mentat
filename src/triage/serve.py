"""Start the HTTP service:  python -m triage.serve  (PORT and WORKERS from the environment)."""
from __future__ import annotations

import os

import uvicorn


def main() -> None:
    uvicorn.run("triage.app:factory", factory=True,
                host=os.environ.get("HOST", "0.0.0.0"),
                port=int(os.environ.get("PORT", "8000")),
                workers=int(os.environ.get("WORKERS", "2")),
                timeout_keep_alive=5, limit_concurrency=1000,
                log_level=os.environ.get("TRIAGE_LOG_LEVEL", "info").lower(),
                access_log=False)


if __name__ == "__main__":
    main()

"""Load the demo samples on start-up (or refresh them when older than DEMO_RESET_HOURS).

Runs as a tiny separate process that asks the local API to do the work, so documents are
processed by the API process itself (no second copy of the pipeline in memory).
"""

import os
import socket
import time
import urllib.request


def api_up() -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", 8000)) == 0


for _ in range(90):
    if api_up():
        break
    time.sleep(2)
time.sleep(3)

hours = os.environ.get("DEMO_RESET_HOURS", "24")
req = urllib.request.Request(
    f"http://127.0.0.1:8000/api/admin/demo-reset?stale_hours={hours}",
    method="POST",
    headers={"Authorization": f"Bearer {os.environ['CRON_SECRET']}"},
)
with urllib.request.urlopen(req, timeout=1800) as resp:
    print("[demo-seed]", resp.read().decode()[:400], flush=True)

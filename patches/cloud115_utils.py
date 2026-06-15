import json
import os
import subprocess


class Cloud115Error(Exception):
    pass


class Cloud115Mover:
    def __init__(self):
        self.python = os.getenv("CLOUD115_PYTHON", "/opt/python312/bin/python3.12")
        self.worker = os.getenv(
            "CLOUD115_WORKER",
            "/nas-tools/app/utils/cloud115_worker.py",
        )

    def move(self, src, dest):
        env = os.environ.copy()
        proc = subprocess.run(
            [self.python, self.worker, src, dest],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,
        )
        output = (proc.stdout or "").strip()
        error = (proc.stderr or "").strip()
        if proc.returncode != 0:
            raise Cloud115Error(error or output or "115 cloud move failed")
        if not output:
            return 0, ""
        try:
            result = json.loads(output)
        except Exception:
            return 0, output
        if not result.get("ok", False):
            raise Cloud115Error(result.get("message") or "115 cloud move failed")
        return 0, result.get("message", "")

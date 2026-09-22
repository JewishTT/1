import os
import subprocess

THEHARVESTER_CONTAINER = os.getenv("THEHARVESTER_CONTAINER", "osint-theharvester-1")

def run_theharvester(domain: str, limit: int = 100, source: str = "all"):
    """Run theHarvester inside the sidecar container via docker exec.

    Configure container name with THEHARVESTER_CONTAINER if your compose project name differs.
    """
    try:
        cmd = [
            "docker", "exec", THEHARVESTER_CONTAINER,
            "theHarvester", "-d", domain, "-l", str(limit), "-b", source, "-f", "/results/out.json"
        ]
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True, timeout=180)
        return {"status": "ok", "output": out}
    except Exception as e:
        return {"status": "error", "error": str(e), "container": THEHARVESTER_CONTAINER}

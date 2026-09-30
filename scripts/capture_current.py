"""Recapture P10's two live-browser suites on isolated loopback ports."""
import os
import pathlib
import socket
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
PORT = 19110


def main():
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", PORT)) == 0:
            raise RuntimeError("P10 capture port already in use")
    server = subprocess.Popen(
        [sys.executable, "-m", "quality_queue.server", "--port", str(PORT)],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    try:
        for _ in range(100):
            if server.poll() is not None:
                raise RuntimeError("P10 server failed: " + server.stderr.read().decode()[:500])
            with socket.socket() as probe:
                if probe.connect_ex(("127.0.0.1", PORT)) == 0:
                    break
            time.sleep(0.05)
        else:
            raise RuntimeError("P10 server start timeout")
        env = dict(os.environ, P10_BASE_URL=f"http://127.0.0.1:{PORT}/")
        subprocess.run([sys.executable, "tests/browser_demo.py"], cwd=ROOT, env=env, check=True)
        subprocess.run([sys.executable, "tests/browser_keyboard.py"], cwd=ROOT, env=env, check=True)
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)
    subprocess.run([sys.executable, "tests/browser_review_regressions.py"], cwd=ROOT, check=True)


if __name__ == "__main__":
    main()

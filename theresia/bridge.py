"""Small Python bridge for the Theresia Node.js process."""
from __future__ import annotations

import json
import subprocess
import threading
from pathlib import Path


class TheresiaClient:
    def __init__(self, node="node", script=None):
        self.script = Path(script) if script else Path(__file__).with_name("theresia.js")
        self._lock = threading.Lock()
        self.process = subprocess.Popen(
            [node, str(self.script)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

    def request(self, command: dict) -> dict:
        if self.process.poll() is not None:
            raise RuntimeError("Theresia process is not running")
        assert self.process.stdin is not None
        assert self.process.stdout is not None
        with self._lock:
            self.process.stdin.write(json.dumps(command, separators=(",", ":")) + "\n")
            self.process.stdin.flush()
            line = self.process.stdout.readline()
        if not line:
            raise RuntimeError("Theresia closed its output")
        result = json.loads(line)
        if "error" in result:
            raise RuntimeError(result["error"])
        return result

    def ping(self):
        return self.request({"cmd": "ping"})

    def analyze(self, fen: str, depth: int = 3, time_ms: int = 1500):
        return self.request({"cmd": "analyze", "fen": fen, "depth": depth, "time_ms": time_ms})

    def legal_moves(self, fen: str):
        return self.request({"cmd": "legal_moves", "fen": fen})

    def evaluate(self, fen: str):
        return self.request({"cmd": "evaluate", "fen": fen})

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

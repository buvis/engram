"""Private llama.cpp servers for model comparisons; never reuse production ports."""

import json
import math
import re
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def request(path: str, payload: dict[str, Any] | None = None) -> Any:
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:18181{path}",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=300) as response:
        return json.load(response)


class Server:
    def __init__(
        self, spec: dict[str, Any], directory: Path, reranking: bool = False
    ) -> None:
        self.spec = spec
        self.directory = directory
        self.reranking = reranking
        self.peak_rss_kib: int | None = None
        self.memory_sampling_error = "Peak process RSS is unavailable: sandbox denied ps. Runtime buffer allocations are reported separately."
        self.startup_seconds = 0.0
        self.stop = threading.Event()

    def __enter__(self) -> "Server":
        binary = shutil.which("llama-server")
        if binary is None:
            raise RuntimeError("llama-server is required")
        self.log = (self.directory / "server.log").open("w")
        local = Path.home() / ".cache/engram/models" / f"{self.spec['name']}.gguf"
        source = ["-m", str(local)] if local.exists() else ["-hf", self.spec["id"]]
        command = [
            binary,
            *source,
            "--alias",
            self.spec["name"],
            "--host",
            "127.0.0.1",
            "--port",
            "18181",
            "-np",
            "4",
            "-c",
            "32768",
            "-b",
            "8192",
            "-ub",
            "8192",
            "-fa",
            "on",
            "-lv",
            "4",
        ]
        command += (
            ["--reranking"]
            if self.reranking
            else ["--embedding", "--pooling", self.spec["pooling"]]
        )
        self.process = subprocess.Popen(command, stdout=self.log, stderr=self.log)
        start = time.monotonic()
        try:
            while time.monotonic() - start < 1800:
                if self.process.poll() is not None:
                    raise RuntimeError(
                        f"server exited {self.process.returncode}; see {self.directory / 'server.log'}"
                    )
                try:
                    models = request("/v1/models")
                    if models["data"][0]["id"] != self.spec["name"]:
                        raise RuntimeError("port 18181 belongs to another server")
                    self.startup_seconds = time.monotonic() - start
                    return self
                except (urllib.error.URLError, TimeoutError):
                    self.stop.wait(1)
            raise RuntimeError("model download/start exceeded 30 minutes")
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *args: object) -> None:
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        self.stop.set()
        self.log.close()

    def allocation_lines(self) -> list[str]:
        lines = (self.directory / "server.log").read_text(errors="replace").splitlines()
        return [
            line
            for line in lines
            if re.search(
                r"buffer size|memory breakdown|total memory|compute buffer", line, re.I
            )
        ]

    def embed(self, texts: list[str]) -> list[list[float]]:
        payload = request(
            "/v1/embeddings", {"model": self.spec["name"], "input": texts}
        )
        rows = sorted(payload["data"], key=lambda item: item["index"])
        if [item["index"] for item in rows] != list(range(len(texts))):
            raise ValueError("embedding response has missing or duplicate indices")
        for item in rows:
            values = item["embedding"]
            if not values or not all(
                isinstance(v, (float, int)) and math.isfinite(v) for v in values
            ):
                raise ValueError("server returned invalid embeddings")
            if sum(v * v for v in values) == 0:
                raise ValueError("server returned a zero embedding")
        return [item["embedding"] for item in rows]

    def rerank(self, query: str, documents: list[str]) -> list[float]:
        payload = request(
            "/rerank", {"query": query, "documents": documents, "top_n": len(documents)}
        )
        rows = payload.get("results", payload.get("data", []))
        if sorted(item["index"] for item in rows) != list(range(len(documents))):
            raise ValueError("reranker response has missing or duplicate indices")
        scores = [0.0] * len(documents)
        for item in rows:
            value = item["relevance_score"]
            if not isinstance(value, (float, int)) or not math.isfinite(value):
                raise ValueError("reranker returned a non-finite score")
            scores[item["index"]] = value
        return scores

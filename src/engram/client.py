"""Embedding Access: llama-server client, preflight, and server lifecycle."""

import http.client
import json
import math
import os
import shutil
import signal
import subprocess
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

EMBED_MAX_CHARS = 8000
EMBED_BATCH_SIZE = 64
EMBED_REQUEST_TIMEOUT_S = 120
STOP_WAIT_TIMEOUT_S = 5

DEFAULT_CONFIG_PATH = Path.home() / ".local" / "share" / "engram" / "config.toml"

_LOOPBACK_HOSTS = {"127.0.0.1", "localhost"}

_DEFAULT_CONFIG_TOML = """\
[[embedding]]
id = "Qwen/Qwen3-Embedding-0.6B-GGUF:Q8_0"
endpoint = "http://127.0.0.1:8081/v1"

[[embedding]]
id = "nomic-ai/nomic-embed-text-v1.5-GGUF:Q8_0"
endpoint = "http://127.0.0.1:8082/v1"

[[embedding]]
id = "CompendiumLabs/bge-m3-GGUF:Q8_0"
endpoint = "http://127.0.0.1:8083/v1"

[pinned]
id = ""
"""


@dataclass(frozen=True)
class EmbeddingEntry:
    id: str
    endpoint: str

    def __post_init__(self):
        split = urllib.parse.urlsplit(self.endpoint)
        if split.hostname not in _LOOPBACK_HOSTS:
            raise ValueError(
                f"embedding entry {self.id!r} has non-loopback endpoint {self.endpoint!r}"
            )
        if split.port is None:
            raise ValueError(
                f"embedding entry {self.id!r} has endpoint {self.endpoint!r} "
                "without an explicit port"
            )


@dataclass(frozen=True)
class Vector:
    values: list[float]
    model_id: str
    dim: int


@dataclass(frozen=True)
class ServerLease:
    entry: EmbeddingEntry
    spawned: bool
    pid: int | None


@dataclass
class EngramConfig:
    embeddings: list[EmbeddingEntry]
    pinned_id: str | None
    config_path: Path


class EmbeddingPreflightError(RuntimeError):
    pass


class EmbeddingServerError(RuntimeError):
    pass


class EmbeddingModelIdentityError(RuntimeError):
    pass


# pid -> Popen, so stop_served can reap the process it terminates instead of
# leaving a zombie that would keep answering os.kill(pid, 0).
_spawned_processes: dict[int, subprocess.Popen] = {}


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> EngramConfig:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_DEFAULT_CONFIG_TOML)

    with path.open("rb") as f:
        raw = tomllib.load(f)

    embeddings = []
    for entry in raw.get("embedding", []):
        embeddings.append(EmbeddingEntry(id=entry["id"], endpoint=entry["endpoint"]))

    pinned_id = raw.get("pinned", {}).get("id") or None

    return EngramConfig(embeddings=embeddings, pinned_id=pinned_id, config_path=path)


def _post_embeddings(entry: EmbeddingEntry, inputs) -> dict:
    url = f"{entry.endpoint}/embeddings"
    body = json.dumps({"model": entry.id, "input": inputs}).encode()
    request = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=EMBED_REQUEST_TIMEOUT_S) as response:
            raw = response.read()
        payload = json.loads(raw)
    except (
        urllib.error.URLError,
        OSError,
        json.JSONDecodeError,
        http.client.HTTPException,
    ) as e:
        raise EmbeddingPreflightError(
            f"embedding request to {entry.endpoint} for model {entry.id} failed: {e}"
        ) from e

    if not isinstance(payload, dict):
        raise EmbeddingPreflightError(
            f"embedding response from {entry.endpoint} for {entry.id} was not a JSON object"
        )
    return payload


def preflight(entry: EmbeddingEntry) -> None:
    payload = _post_embeddings(entry, "ping")
    actual_model = payload.get("model")
    if actual_model != entry.id:
        raise EmbeddingModelIdentityError(
            f"expected model {entry.id!r} but endpoint {entry.endpoint} reported "
            f"{actual_model!r}"
        )


def ensure_served(entry: EmbeddingEntry) -> ServerLease:
    try:
        preflight(entry)
        return ServerLease(entry=entry, spawned=False, pid=None)
    except EmbeddingPreflightError:
        pass

    binary = shutil.which("llama-server")
    if binary is None:
        raise EmbeddingServerError(
            "llama-server not found on PATH; install it with `brew install llama.cpp`"
        )

    port = urllib.parse.urlsplit(entry.endpoint).port
    process = subprocess.Popen(
        [binary, "--embedding", "-hf", entry.id, "--alias", entry.id, "--port", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )
    _spawned_processes[process.pid] = process

    deadline = time.monotonic() + EMBED_REQUEST_TIMEOUT_S
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            preflight(entry)
            return ServerLease(entry=entry, spawned=True, pid=process.pid)
        except EmbeddingPreflightError as e:
            last_error = e
            time.sleep(0.2)

    _spawned_processes.pop(process.pid, None)
    process.kill()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass

    raise EmbeddingServerError(
        f"llama-server for {entry.id} did not become ready at {entry.endpoint}: {last_error}"
    )


def stop_served(lease: ServerLease) -> None:
    if not lease.spawned or lease.pid is None:
        return

    process = _spawned_processes.pop(lease.pid, None)
    try:
        os.kill(lease.pid, signal.SIGTERM)
    except ProcessLookupError:
        return

    if process is not None:
        try:
            process.wait(timeout=STOP_WAIT_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            try:
                os.kill(lease.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=STOP_WAIT_TIMEOUT_S)
            except subprocess.TimeoutExpired:
                pass


def embed(texts: list[str], entry: EmbeddingEntry) -> list[Vector]:
    ensure_served(entry)

    vectors: list[Vector] = []
    for start in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[start : start + EMBED_BATCH_SIZE]
        truncated = [t[:EMBED_MAX_CHARS] for t in batch]
        try:
            payload = _post_embeddings(entry, truncated)
        except EmbeddingPreflightError as e:
            raise EmbeddingPreflightError(
                f"{e} (batch indices {start}..{start + len(batch) - 1})"
            ) from e
        data = payload.get("data", [])

        batch_vectors: list[Vector | None] = [None] * len(batch)
        seen_idx: set[int] = set()
        dim: int | None = None
        for item in data:
            idx = item.get("index")
            if not isinstance(idx, int) or idx < 0 or idx >= len(batch):
                raise EmbeddingPreflightError(
                    f"invalid index in embedding response from {entry.endpoint} "
                    f"for {entry.id}"
                )
            if idx in seen_idx:
                raise EmbeddingPreflightError(
                    f"duplicate index {idx} in embedding response from "
                    f"{entry.endpoint} for {entry.id}"
                )
            seen_idx.add(idx)
            values = item.get("embedding")
            if (
                not isinstance(values, list)
                or not values
                or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in values)
            ):
                raise EmbeddingPreflightError(
                    f"invalid embedding vector at index {idx} in response from "
                    f"{entry.endpoint} for {entry.id}"
                )
            if dim is None:
                dim = len(values)
            elif len(values) != dim:
                raise EmbeddingPreflightError(
                    f"inconsistent embedding dimension in response from "
                    f"{entry.endpoint} for {entry.id}"
                )
            batch_vectors[idx] = Vector(values=values, model_id=entry.id, dim=len(values))

        if any(v is None for v in batch_vectors):
            raise EmbeddingPreflightError(
                f"missing index in embedding response from {entry.endpoint} for {entry.id}"
            )

        vectors.extend(batch_vectors)

    return vectors

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
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

EMBED_MAX_CHARS = 8000
EMBED_BATCH_SIZE = 64
# A request's total size, not just its text count, has to fit the server's
# batch — llama-server closes the connection when one overruns it. Kept equal
# to EMBED_MAX_CHARS so a single max-length text always fits in a batch by
# itself, and under EMBED_SERVER_CTX_TOKENS at the worst case of one token per
# character (token-dense chunks: stack traces, JSON dumps, minified code).
EMBED_BATCH_MAX_CHARS = EMBED_MAX_CHARS
EMBED_SERVER_CTX_TOKENS = 8192
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


# Reserved for the markdown headings and separators a rendered pack adds on top
# of its four section bodies, so the section caps cannot spend the whole hard
# cap and leave the framing to overflow it.
FRAMING_OVERHEAD_TOKENS = 100


@dataclass(frozen=True)
class PackBudget:
    hard_cap_tokens: int = 4000
    similar_cap_tokens: int = 1400
    reuse_cap_tokens: int = 1000
    findings_cap_tokens: int = 1000
    prose_cap_tokens: int = 500


@dataclass
class EngramConfig:
    embeddings: list[EmbeddingEntry]
    pinned_id: str | None
    config_path: Path
    pack_budget: PackBudget = PackBudget()


class EmbeddingPreflightError(RuntimeError):
    pass


class EmbeddingServerError(RuntimeError):
    pass


class EmbeddingModelIdentityError(RuntimeError):
    pass


class _LoopbackRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        host = urllib.parse.urlsplit(newurl).hostname
        if host not in _LOOPBACK_HOSTS:
            raise urllib.error.HTTPError(
                newurl, code, f"refusing off-machine redirect to {newurl!r}", headers, fp
            )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_OPENER = urllib.request.build_opener(_LoopbackRedirectHandler)


# pid -> Popen, so stop_served can reap the process it terminates instead of
# leaving a zombie that would keep answering os.kill(pid, 0).
_spawned_processes: dict[int, subprocess.Popen] = {}


def _build_pack_budget(pack_raw: dict, path: Path) -> PackBudget:
    defaults = PackBudget()
    pack_budget = PackBudget(
        hard_cap_tokens=pack_raw.get("hard_cap_tokens", defaults.hard_cap_tokens),
        similar_cap_tokens=pack_raw.get("similar_cap_tokens", defaults.similar_cap_tokens),
        reuse_cap_tokens=pack_raw.get("reuse_cap_tokens", defaults.reuse_cap_tokens),
        findings_cap_tokens=pack_raw.get("findings_cap_tokens", defaults.findings_cap_tokens),
        prose_cap_tokens=pack_raw.get("prose_cap_tokens", defaults.prose_cap_tokens),
    )
    for field_name, value in (
        ("hard_cap_tokens", pack_budget.hard_cap_tokens),
        ("similar_cap_tokens", pack_budget.similar_cap_tokens),
        ("reuse_cap_tokens", pack_budget.reuse_cap_tokens),
        ("findings_cap_tokens", pack_budget.findings_cap_tokens),
        ("prose_cap_tokens", pack_budget.prose_cap_tokens),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(
                f"config {path} has invalid [pack] {field_name} {value!r}; "
                "must be a positive integer"
            )

    section_sum = (
        pack_budget.similar_cap_tokens
        + pack_budget.reuse_cap_tokens
        + pack_budget.findings_cap_tokens
        + pack_budget.prose_cap_tokens
        + FRAMING_OVERHEAD_TOKENS
    )
    if section_sum > pack_budget.hard_cap_tokens:
        raise ValueError(
            f"config {path} [pack] section caps plus framing overhead ({section_sum}) "
            f"exceed hard_cap_tokens ({pack_budget.hard_cap_tokens})"
        )

    return pack_budget


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

    if not embeddings:
        raise ValueError(f"config {path} has no [[embedding]] entries")
    if pinned_id is not None and pinned_id not in {e.id for e in embeddings}:
        raise ValueError(
            f"config {path} pins id {pinned_id!r} which is not in the embedding shortlist"
        )

    pack_budget = _build_pack_budget(raw.get("pack", {}), path)

    return EngramConfig(
        embeddings=embeddings,
        pinned_id=pinned_id,
        config_path=path,
        pack_budget=pack_budget,
    )


def resolve_pinned_entry(config: EngramConfig) -> EmbeddingEntry:
    if not config.embeddings:
        raise ValueError("config has no embedding entries")
    if config.pinned_id is not None:
        entry = next((e for e in config.embeddings if e.id == config.pinned_id), None)
        if entry is None:
            raise ValueError(f"pinned id {config.pinned_id!r} is not in the embedding shortlist")
        return entry
    return config.embeddings[0]


def _post_embeddings(entry: EmbeddingEntry, inputs) -> dict:
    url = f"{entry.endpoint}/embeddings"
    body = json.dumps({"model": entry.id, "input": inputs}).encode()
    request = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with _OPENER.open(request, timeout=EMBED_REQUEST_TIMEOUT_S) as response:
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


def _reap(process: subprocess.Popen) -> None:
    _spawned_processes.pop(process.pid, None)
    process.kill()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass


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
        [
            binary,
            "--embedding",
            "-hf",
            entry.id,
            "--alias",
            entry.id,
            "--port",
            str(port),
            # Without explicit sizing llama.cpp's defaults are smaller than a
            # full request, and the server closes the connection mid-batch.
            "-c",
            str(EMBED_SERVER_CTX_TOKENS),
            "-b",
            str(EMBED_SERVER_CTX_TOKENS),
            "--ubatch-size",
            str(EMBED_SERVER_CTX_TOKENS),
        ],
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
        except EmbeddingModelIdentityError:
            _reap(process)
            raise

    _reap(process)

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


def _parse_vector_item(
    item, batch: list[str], entry: EmbeddingEntry, seen_idx: set[int], dim: int | None
) -> tuple[int, Vector, int]:
    if not isinstance(item, dict):
        raise EmbeddingPreflightError(
            f"invalid data element in embedding response from {entry.endpoint} "
            f"for {entry.id}"
        )
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
    return idx, Vector(values=values, model_id=entry.id, dim=len(values)), dim


def _parse_batch_vectors(
    payload: dict, batch: list[str], entry: EmbeddingEntry
) -> list[Vector]:
    data = payload.get("data", [])
    if not isinstance(data, list):
        raise EmbeddingPreflightError(
            f"embedding response from {entry.endpoint} for {entry.id} had a non-list data field"
        )

    batch_vectors: list[Vector | None] = [None] * len(batch)
    seen_idx: set[int] = set()
    dim: int | None = None
    for item in data:
        idx, vector, dim = _parse_vector_item(item, batch, entry, seen_idx, dim)
        batch_vectors[idx] = vector

    if any(v is None for v in batch_vectors):
        raise EmbeddingPreflightError(
            f"missing index in embedding response from {entry.endpoint} for {entry.id}"
        )

    return [v for v in batch_vectors if v is not None]


def _budgeted_batches(texts: list[str]) -> Iterator[tuple[int, list[str]]]:
    """Yield `(start_index, truncated_texts)` requests within both budgets.

    A batch closes when adding the next text would exceed EMBED_BATCH_SIZE
    texts or EMBED_BATCH_MAX_CHARS characters. Batching by count alone let a
    run of long, token-dense chunks build a request far past what the server
    can hold; a text at the truncation cap is sent alone rather than dropped.
    """
    start = 0
    batch: list[str] = []
    total = 0
    for index, text in enumerate(texts):
        piece = text[:EMBED_MAX_CHARS]
        if batch and (
            len(batch) >= EMBED_BATCH_SIZE or total + len(piece) > EMBED_BATCH_MAX_CHARS
        ):
            yield start, batch
            start, batch, total = index, [], 0
        batch.append(piece)
        total += len(piece)
    if batch:
        yield start, batch


def embed(texts: list[str], entry: EmbeddingEntry) -> list[Vector]:
    ensure_served(entry)

    vectors: list[Vector] = []
    for start, truncated in _budgeted_batches(texts):
        try:
            payload = _post_embeddings(entry, truncated)
        except EmbeddingPreflightError as e:
            raise EmbeddingPreflightError(
                f"{e} (batch indices {start}..{start + len(truncated) - 1})"
            ) from e
        vectors.extend(_parse_batch_vectors(payload, truncated, entry))

    return vectors

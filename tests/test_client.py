import http.server
import json
import os
import signal
import socket
import threading
import time
from pathlib import Path

import pytest
import tomllib
from _embedding_server import (
    _embed_payloads,
    _free_port,
    _input_list,
    _MockEmbeddingServer,
)
from engram import client
from engram.client import (
    EMBED_BATCH_SIZE,
    EMBED_MAX_CHARS,
    EmbeddingEntry,
    EmbeddingModelIdentityError,
    EmbeddingPreflightError,
    EmbeddingServerError,
    EngramConfig,
    PackBudget,
    ServerLease,
    embed,
    ensure_served,
    load_config,
    preflight,
    resolve_pinned_entry,
    stop_served,
)


def _free_port_v6() -> int:
    with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as s:
        s.bind(("::1", 0))
        return s.getsockname()[1]


@pytest.fixture
def mock_server():
    port = _free_port()
    server = _MockEmbeddingServer(port, model_id="test-model")
    server.start()
    yield server
    server.stop()


_STUB_LLAMA_SERVER = """#!/usr/bin/env python3
import http.server
import json
import sys

args = sys.argv[1:]


def _flag(name, default=None):
    if name in args:
        return args[args.index(name) + 1]
    return default


alias = _flag("--alias", "stub-model")
port = int(_flag("--port"))


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._send(404, b"{}")

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n)
        payload = json.loads(raw) if raw else {}
        inputs = payload.get("input", [])
        if isinstance(inputs, str):
            inputs = [inputs]
        data = [
            {"index": i, "embedding": [0.1, 0.2, 0.3, 0.4], "object": "embedding"}
            for i in range(len(inputs))
        ]
        body = json.dumps({"object": "list", "model": alias, "data": data}).encode()
        self._send(200, body)


http.server.HTTPServer(("127.0.0.1", port), Handler).serve_forever()
"""


def _write_stub_llama_server(bin_dir: Path) -> Path:
    stub_path = bin_dir / "llama-server"
    stub_path.write_text(_STUB_LLAMA_SERVER)
    stub_path.chmod(0o755)
    return stub_path


_STUB_LLAMA_SERVER_NEVER_READY = """#!/usr/bin/env python3
import http.server
import sys

args = sys.argv[1:]


def _flag(name, default=None):
    if name in args:
        return args[args.index(name) + 1]
    return default


port = int(_flag("--port"))


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send_404(self):
        body = b"{}"
        self.send_response(404)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._send_404()

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(n)
        self._send_404()


http.server.HTTPServer(("127.0.0.1", port), Handler).serve_forever()
"""


def _write_never_ready_stub_llama_server(bin_dir: Path) -> Path:
    stub_path = bin_dir / "llama-server"
    stub_path.write_text(_STUB_LLAMA_SERVER_NEVER_READY)
    stub_path.chmod(0o755)
    return stub_path


_STUB_LLAMA_SERVER_IGNORES_SIGTERM = """#!/usr/bin/env python3
import http.server
import json
import signal
import sys

signal.signal(signal.SIGTERM, signal.SIG_IGN)

args = sys.argv[1:]


def _flag(name, default=None):
    if name in args:
        return args[args.index(name) + 1]
    return default


alias = _flag("--alias", "stub-model")
port = int(_flag("--port"))


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._send(404, b"{}")

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n)
        payload = json.loads(raw) if raw else {}
        inputs = payload.get("input", [])
        if isinstance(inputs, str):
            inputs = [inputs]
        data = [
            {"index": i, "embedding": [0.1, 0.2, 0.3, 0.4], "object": "embedding"}
            for i in range(len(inputs))
        ]
        body = json.dumps({"object": "list", "model": alias, "data": data}).encode()
        self._send(200, body)


http.server.HTTPServer(("127.0.0.1", port), Handler).serve_forever()
"""


def _write_stub_llama_server_ignoring_sigterm(bin_dir: Path) -> Path:
    stub_path = bin_dir / "llama-server"
    stub_path.write_text(_STUB_LLAMA_SERVER_IGNORES_SIGTERM)
    stub_path.chmod(0o755)
    return stub_path


_STUB_LLAMA_SERVER_WRONG_MODEL_ID = """#!/usr/bin/env python3
import http.server
import json
import sys

args = sys.argv[1:]


def _flag(name, default=None):
    if name in args:
        return args[args.index(name) + 1]
    return default


port = int(_flag("--port"))


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._send(404, b"{}")

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n)
        payload = json.loads(raw) if raw else {}
        inputs = payload.get("input", [])
        if isinstance(inputs, str):
            inputs = [inputs]
        data = [
            {"index": i, "embedding": [0.1, 0.2, 0.3, 0.4], "object": "embedding"}
            for i in range(len(inputs))
        ]
        body = json.dumps({"object": "list", "model": "wrong-model", "data": data}).encode()
        self._send(200, body)


http.server.HTTPServer(("127.0.0.1", port), Handler).serve_forever()
"""


def _write_stub_llama_server_wrong_model_id(bin_dir: Path) -> Path:
    stub_path = bin_dir / "llama-server"
    stub_path.write_text(_STUB_LLAMA_SERVER_WRONG_MODEL_ID)
    stub_path.chmod(0o755)
    return stub_path


# --- load_config ---


def test_load_config_writes_default_shortlist_when_file_absent(tmp_path):
    config_path = tmp_path / "config.toml"
    assert not config_path.exists()

    config = load_config(path=config_path)

    assert config_path.exists()
    with config_path.open("rb") as f:
        raw = tomllib.load(f)

    assert len(raw["embedding"]) == 3
    for entry in raw["embedding"]:
        assert entry["id"]
    endpoints = {entry["endpoint"] for entry in raw["embedding"]}
    assert endpoints == {
        "http://127.0.0.1:8081/v1",
        "http://127.0.0.1:8082/v1",
        "http://127.0.0.1:8083/v1",
    }
    assert raw["pinned"]["id"] == ""

    assert len(config.embeddings) == 3
    assert {e.endpoint for e in config.embeddings} == endpoints
    assert config.pinned_id is None
    assert config.config_path == config_path


def test_load_config_rejects_non_loopback_endpoint(tmp_path):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "[[embedding]]\n"
        'id = "remote-model"\n'
        'endpoint = "http://93.184.216.34:8081/v1"\n'
        "\n"
        "[pinned]\n"
        'id = ""\n',
    )

    with pytest.raises(ValueError) as excinfo:
        load_config(path=config_path)

    assert "remote-model" in str(excinfo.value)


def test_embedding_entry_rejects_non_loopback_endpoint():
    with pytest.raises(ValueError) as excinfo:
        EmbeddingEntry(id="remote-model", endpoint="http://93.184.216.34:8081/v1")

    assert "remote-model" in str(excinfo.value)


# --- preflight ---


def test_preflight_raises_for_unreachable_endpoint():
    port = _free_port()
    entry = EmbeddingEntry(id="ghost-model", endpoint=f"http://127.0.0.1:{port}/v1")

    with pytest.raises(EmbeddingPreflightError) as excinfo:
        preflight(entry)

    message = str(excinfo.value)
    assert entry.endpoint in message
    assert entry.id in message


def test_preflight_raises_for_erroring_endpoint(mock_server):
    mock_server.responder = lambda payload: (500, b'{"error": "boom"}')
    entry = EmbeddingEntry(id=mock_server.model_id, endpoint=mock_server.base_url)

    with pytest.raises(EmbeddingPreflightError) as excinfo:
        preflight(entry)

    message = str(excinfo.value)
    assert entry.endpoint in message
    assert entry.id in message


def test_preflight_raises_model_identity_error_on_mismatch(mock_server):
    mock_server.model_id = "actual-model"
    entry = EmbeddingEntry(id="expected-model", endpoint=mock_server.base_url)

    with pytest.raises(EmbeddingModelIdentityError) as excinfo:
        preflight(entry)

    message = str(excinfo.value)
    assert "expected-model" in message
    assert "actual-model" in message


def test_preflight_times_out_on_hung_endpoint(mock_server, monkeypatch):
    monkeypatch.setattr(client, "EMBED_REQUEST_TIMEOUT_S", 0.3)

    def hang(payload):
        time.sleep(2.0)
        return 200, b"{}"

    mock_server.responder = hang
    entry = EmbeddingEntry(id=mock_server.model_id, endpoint=mock_server.base_url)

    start = time.monotonic()
    with pytest.raises(EmbeddingPreflightError):
        preflight(entry)
    elapsed = time.monotonic() - start

    assert elapsed < 1.5


# --- ensure_served / stop_served ---


def test_ensure_served_returns_unspawned_lease_for_healthy_endpoint(mock_server):
    entry = EmbeddingEntry(id=mock_server.model_id, endpoint=mock_server.base_url)

    lease = ensure_served(entry)

    assert lease == ServerLease(entry=entry, spawned=False, pid=None)


# --- regression: server ownership outlives the call that spawned it ---
# embed() calls ensure_served on every invocation. When the endpoint is already
# healthy the lease used to come back spawned=False, so embed() disowned a server
# it had started itself and refused to recycle it. Measured against the real
# backend: a degraded server survived un-recycled and killed the index run.


def test_ensure_served_still_leases_a_server_it_spawned_earlier_as_ours(
    tmp_path,
    monkeypatch,
):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_stub_llama_server(bin_dir)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    port = _free_port()
    entry = EmbeddingEntry(id="stub-model", endpoint=f"http://127.0.0.1:{port}/v1")

    first = ensure_served(entry)
    try:
        assert first.spawned is True
        second = ensure_served(entry)  # endpoint healthy now, but still ours
        assert second.spawned is True
        assert second.pid == first.pid
    finally:
        stop_served(first)


def test_ensure_served_disowns_a_stopped_server(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_stub_llama_server(bin_dir)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    port = _free_port()
    entry = EmbeddingEntry(id="stub-model", endpoint=f"http://127.0.0.1:{port}/v1")

    lease = ensure_served(entry)
    stop_served(lease)

    assert entry.endpoint not in client._spawned_pids_by_endpoint


# --- regression: a stale lease releases the replacement, not a dead pid ---
# embed() recycles a degraded server and keeps the fresh lease in a local, so the
# caller still holds the pre-recycle pid. Signalling that corpse left the
# replacement running; harness.run_harness holds a lease per candidate across a
# full scoring run, so it leaked a server for every candidate that recycled.


def test_stop_served_releases_the_replacement_when_the_lease_is_stale(monkeypatch):
    entry = EmbeddingEntry(id="stub-model", endpoint="http://127.0.0.1:9911/v1")
    stale_lease = ServerLease(entry=entry, spawned=True, pid=111111)

    # State after a recycle: we own the replacement, not the lease's pid.
    monkeypatch.setattr(client, "_spawned_processes", {})
    monkeypatch.setattr(client, "_spawned_pids_by_endpoint", {entry.endpoint: 222222})

    signalled: list[tuple[int, int]] = []
    monkeypatch.setattr(
        client.os, "kill", lambda pid, sig: signalled.append((pid, sig))
    )

    stop_served(stale_lease)

    assert signalled == [(222222, signal.SIGTERM)]
    assert client._spawned_pids_by_endpoint == {}


def test_stop_served_is_a_noop_when_engram_owns_nothing_at_the_endpoint(monkeypatch):
    entry = EmbeddingEntry(id="stub-model", endpoint="http://127.0.0.1:9911/v1")
    lease = ServerLease(entry=entry, spawned=True, pid=111111)

    monkeypatch.setattr(client, "_spawned_processes", {})
    monkeypatch.setattr(client, "_spawned_pids_by_endpoint", {})

    signalled: list[tuple[int, int]] = []
    monkeypatch.setattr(
        client.os, "kill", lambda pid, sig: signalled.append((pid, sig))
    )

    stop_served(lease)

    assert signalled == []


# --- regression: a sick server we own is reaped before its replacement spawns ---
# It still holds the port, so a replacement cannot bind and every readiness probe
# reaches the sick one until the deadline. Measured: the run died with "did not
# become ready ... HTTP Error 500" after burning the full 120s timeout.


def test_ensure_served_reaps_our_sick_server_before_spawning_a_replacement(
    tmp_path,
    monkeypatch,
):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "llama-server"
    stub.write_text("#!/bin/sh\nexit 0\n")
    stub.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setattr(client, "EMBED_REQUEST_TIMEOUT_S", 0.1)

    class _FakeProcess:
        def __init__(self, pid):
            self.pid = pid
            self.killed = False

        def poll(self):
            return None

        def terminate(self):
            """No-op: nothing was really spawned."""

        def kill(self):
            self.killed = True

        def wait(self, timeout=None):
            return 0

    sick = _FakeProcess(pid=911911)
    # Nothing is listening on this port, so preflight fails and ensure_served
    # takes its spawn path with a server it believes it owns.
    port = _free_port()
    entry = EmbeddingEntry(id="stub-model", endpoint=f"http://127.0.0.1:{port}/v1")

    monkeypatch.setattr(client, "_spawned_processes", {sick.pid: sick})
    monkeypatch.setattr(client, "_spawned_pids_by_endpoint", {entry.endpoint: sick.pid})
    monkeypatch.setattr(
        client.subprocess,
        "Popen",
        lambda argv, **kwargs: _FakeProcess(pid=922922),
    )

    with pytest.raises(EmbeddingServerError):
        ensure_served(entry)

    assert sick.killed is True
    assert sick.pid not in client._spawned_processes


def test_ensure_served_spawns_stub_server_when_endpoint_is_dead(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_stub_llama_server(bin_dir)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    port = _free_port()
    entry = EmbeddingEntry(id="stub-model", endpoint=f"http://127.0.0.1:{port}/v1")

    lease = ensure_served(entry)
    try:
        assert lease.entry == entry
        assert lease.spawned is True
        assert isinstance(lease.pid, int)
        assert lease.pid > 0
        os.kill(lease.pid, 0)  # still alive
    finally:
        stop_served(lease)


def test_ensure_served_sizes_the_spawned_server_to_hold_a_full_request(
    tmp_path,
    monkeypatch,
):
    """Without explicit -c/-b/--ubatch-size the server runs on llama.cpp
    defaults smaller than one budgeted request, and closes the connection
    mid-batch. The sizing must also cover the request budget outright.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_stub_llama_server(bin_dir)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setattr(client, "EMBED_REQUEST_TIMEOUT_S", 0.1)

    spawned: list[list[str]] = []

    class _RecordingPopen:
        def __init__(self, argv, **kwargs):
            spawned.append(argv)
            self.pid = -1

        def poll(self):
            return None

        def terminate(self):
            """No-op: nothing was really spawned, so there is nothing to signal."""

        def wait(self, timeout=None):
            return 0

        def kill(self):
            """No-op: see terminate."""

    monkeypatch.setattr(client.subprocess, "Popen", _RecordingPopen)

    port = _free_port()
    entry = EmbeddingEntry(id="stub-model", endpoint=f"http://127.0.0.1:{port}/v1")

    with pytest.raises(EmbeddingServerError):
        ensure_served(entry)

    argv = spawned[0]
    sizing = str(client.EMBED_SERVER_CTX_TOKENS)
    assert argv[argv.index("-c") + 1] == sizing
    assert argv[argv.index("-b") + 1] == sizing
    assert argv[argv.index("--ubatch-size") + 1] == sizing
    # Worst case is one token per character, so the server must be at least as
    # large as the per-request character budget.
    assert client.EMBED_SERVER_CTX_TOKENS >= client.EMBED_BATCH_MAX_CHARS


def test_ensure_served_raises_when_llama_server_missing_from_path(
    tmp_path, monkeypatch
):
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    monkeypatch.setenv("PATH", str(empty_bin))

    port = _free_port()
    entry = EmbeddingEntry(id="missing-model", endpoint=f"http://127.0.0.1:{port}/v1")

    with pytest.raises(EmbeddingServerError) as excinfo:
        ensure_served(entry)

    assert "brew install llama.cpp" in str(excinfo.value)


def test_stop_served_is_noop_for_unspawned_lease():
    entry = EmbeddingEntry(id="model", endpoint="http://127.0.0.1:9999/v1")
    lease = ServerLease(entry=entry, spawned=False, pid=None)

    stop_served(lease)  # must not raise


def test_stop_served_terminates_a_spawned_process(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_stub_llama_server(bin_dir)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    port = _free_port()
    entry = EmbeddingEntry(id="stub-model-2", endpoint=f"http://127.0.0.1:{port}/v1")
    lease = ensure_served(entry)
    assert lease.spawned is True

    stop_served(lease)

    deadline = time.time() + 5
    alive = True
    while time.time() < deadline:
        try:
            os.kill(lease.pid, 0)
        except ProcessLookupError:
            alive = False
            break
        time.sleep(0.05)
    assert not alive

    stop_served(lease)  # idempotent, must not raise


# --- embed ---


def test_embed_splits_large_batch_into_multiple_requests(mock_server):
    entry = EmbeddingEntry(id=mock_server.model_id, endpoint=mock_server.base_url)
    texts = [f"text-{i}" for i in range(EMBED_BATCH_SIZE + 6)]

    vectors = embed(texts, entry)

    assert len(vectors) == EMBED_BATCH_SIZE + 6

    batch_payloads = [r for r in mock_server.requests if len(_input_list(r)) > 1]
    assert len(batch_payloads) == 2
    sizes = sorted(len(_input_list(p)) for p in batch_payloads)
    assert sizes == sorted([EMBED_BATCH_SIZE, 6])


def test_embed_truncates_long_text_only_in_outgoing_request(mock_server):
    entry = EmbeddingEntry(id=mock_server.model_id, endpoint=mock_server.base_url)
    long_text = "x" * 10000
    texts = [long_text, "short"]

    vectors = embed(texts, entry)

    assert len(vectors) == 2
    # Asserted across requests, not within one: a text at the truncation cap
    # fills the per-request char budget, so "short" rides a second request.
    sent = [t for p in _embed_payloads(mock_server) for t in _input_list(p)]
    assert len(sent[0]) == EMBED_MAX_CHARS
    assert sent == [long_text[:EMBED_MAX_CHARS], "short"]
    assert texts[0] == long_text  # the caller's own text is left intact


# --- regression: ensure_served() reaps the spawned process on readiness timeout ---


def test_ensure_served_terminates_orphaned_process_on_readiness_timeout(
    tmp_path, monkeypatch
):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_never_ready_stub_llama_server(bin_dir)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setattr(client, "EMBED_REQUEST_TIMEOUT_S", 0.5)

    port = _free_port()
    entry = EmbeddingEntry(
        id="never-ready-model", endpoint=f"http://127.0.0.1:{port}/v1"
    )

    captured = {}

    def watch():
        deadline = time.time() + 2
        while time.time() < deadline:
            if client._spawned_processes:
                captured["pid"] = next(iter(client._spawned_processes))
                return
            time.sleep(0.01)

    watcher = threading.Thread(target=watch, daemon=True)
    watcher.start()

    with pytest.raises(EmbeddingServerError):
        ensure_served(entry)

    watcher.join(timeout=2)

    assert client._spawned_processes == {}
    assert "pid" in captured
    with pytest.raises(ProcessLookupError):
        os.kill(captured["pid"], 0)


# --- regression: stop_served() escalates to SIGKILL when SIGTERM is ignored ---


def test_stop_served_escalates_to_sigkill_when_process_ignores_sigterm(
    tmp_path, monkeypatch
):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_stub_llama_server_ignoring_sigterm(bin_dir)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setattr(client, "STOP_WAIT_TIMEOUT_S", 0.5)

    port = _free_port()
    entry = EmbeddingEntry(
        id="stub-model-ignores-sigterm",
        endpoint=f"http://127.0.0.1:{port}/v1",
    )
    lease = ensure_served(entry)
    assert lease.spawned is True

    stop_served(lease)

    deadline = time.time() + 5
    alive = True
    while time.time() < deadline:
        try:
            os.kill(lease.pid, 0)
        except ProcessLookupError:
            alive = False
            break
        time.sleep(0.05)
    assert not alive


# --- regression: preflight() rejects a non-object JSON response ---


def test_preflight_raises_preflight_error_for_non_object_json_response(mock_server):
    mock_server.responder = lambda payload: (200, b"[]")
    entry = EmbeddingEntry(id=mock_server.model_id, endpoint=mock_server.base_url)

    with pytest.raises(EmbeddingPreflightError):
        preflight(entry)


# --- regression: EmbeddingEntry requires an explicit port ---


def test_embedding_entry_rejects_endpoint_without_explicit_port():
    with pytest.raises(ValueError) as excinfo:
        EmbeddingEntry(id="x", endpoint="http://127.0.0.1/v1")

    assert "x" in str(excinfo.value)


# --- regression: _LoopbackRedirectHandler refuses off-machine redirect targets ---


@pytest.fixture
def _redirect_chain_to_reachable_off_machine_loopback():
    """Start a reachable ::1 server and a 127.0.0.1 server that redirects
    to it. Yields the redirecting server's port; tears both down on exit.
    """
    reachable_port = _free_port_v6()

    class ReachableHandler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            """Suppress default request logging to stderr."""

        def _respond(self):
            body = json.dumps(
                {
                    "object": "list",
                    "model": "off-machine",
                    "data": [
                        {
                            "index": 0,
                            "embedding": [9.0, 9.0, 9.0, 9.0],
                            "object": "embedding",
                        },
                    ],
                },
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            self._respond()

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            self.rfile.read(n)
            self._respond()

    class _V6HTTPServer(http.server.HTTPServer):
        address_family = socket.AF_INET6

    reachable_server = _V6HTTPServer(("::1", reachable_port), ReachableHandler)
    reachable_thread = threading.Thread(
        target=reachable_server.serve_forever, daemon=True
    )
    reachable_thread.start()

    redirect_target = f"http://[::1]:{reachable_port}/v1/embeddings"

    class RedirectHandler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            """Suppress default request logging to stderr."""

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            self.rfile.read(n)
            self.send_response(302, "Found")
            self.send_header("Location", redirect_target)
            self.send_header("Content-Length", "0")
            self.end_headers()

    redirect_port = _free_port()
    redirect_server = http.server.HTTPServer(
        ("127.0.0.1", redirect_port), RedirectHandler
    )
    redirect_thread = threading.Thread(
        target=redirect_server.serve_forever, daemon=True
    )
    redirect_thread.start()

    try:
        yield redirect_port
    finally:
        redirect_server.shutdown()
        redirect_server.server_close()
        redirect_thread.join(timeout=5)
        reachable_server.shutdown()
        reachable_server.server_close()
        reachable_thread.join(timeout=5)


def test_post_embeddings_refuses_redirect_to_host_outside_loopback_allowlist(
    _redirect_chain_to_reachable_off_machine_loopback,
):
    """End-to-end: drives _post_embeddings's real HTTP call through _OPENER
    against a real 302 redirect, rather than calling the redirect handler
    directly.

    IPv6 ::1 IS a loopback host. It is used here deliberately as a
    REACHABLE stand-in for a host that is NOT in _LOOPBACK_HOSTS (which
    only contains "127.0.0.1" and "localhost") - a genuinely reachable,
    listening server that would answer with a valid embedding if followed.
    This proves the refusal below is allowlist-based, not reachability-
    based: with _OPENER wired in, _LoopbackRedirectHandler refuses the
    redirect regardless of reachability, so this raises
    EmbeddingPreflightError. If _post_embeddings ever stopped routing
    through _OPENER (e.g. plain urllib.request.urlopen), the default
    redirect handler would follow the redirect to the reachable stub and
    the call would SUCCEED instead of raising, so this test would fail.
    """
    redirect_port = _redirect_chain_to_reachable_off_machine_loopback
    entry = EmbeddingEntry(id="x", endpoint=f"http://127.0.0.1:{redirect_port}/v1")

    with pytest.raises(EmbeddingPreflightError):
        client._post_embeddings(entry, ["hello"])


# --- regression: ensure_served() reaps the spawned process on model identity mismatch ---


def test_ensure_served_reaps_process_on_model_identity_mismatch(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_stub_llama_server_wrong_model_id(bin_dir)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    port = _free_port()
    entry = EmbeddingEntry(id="expected-model", endpoint=f"http://127.0.0.1:{port}/v1")

    captured = {}

    def watch():
        deadline = time.time() + 2
        while time.time() < deadline:
            if client._spawned_processes:
                captured["pid"] = next(iter(client._spawned_processes))
                return
            time.sleep(0.01)

    watcher = threading.Thread(target=watch, daemon=True)
    watcher.start()

    with pytest.raises((EmbeddingModelIdentityError, EmbeddingServerError)):
        ensure_served(entry)

    watcher.join(timeout=2)

    assert client._spawned_processes == {}
    assert "pid" in captured
    with pytest.raises(ProcessLookupError):
        os.kill(captured["pid"], 0)


# --- regression: load_config() rejects an empty embedding shortlist and unknown pinned id ---


def test_load_config_rejects_empty_embedding_list(tmp_path):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        '[pinned]\nid = ""\n',
    )

    with pytest.raises(ValueError):
        load_config(path=config_path)


def test_load_config_rejects_pinned_id_absent_from_shortlist(tmp_path):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "[[embedding]]\n"
        'id = "model-a"\n'
        'endpoint = "http://127.0.0.1:8081/v1"\n'
        "\n"
        "[pinned]\n"
        'id = "model-b"\n',
    )

    with pytest.raises(ValueError) as excinfo:
        load_config(path=config_path)

    assert "model-b" in str(excinfo.value)


# --- resolve_pinned_entry ---


def test_resolve_pinned_entry_returns_first_when_unpinned(tmp_path):
    e0 = EmbeddingEntry(id="m0", endpoint="http://127.0.0.1:8081/v1")
    e1 = EmbeddingEntry(id="m1", endpoint="http://127.0.0.1:8082/v1")
    config = EngramConfig(
        embeddings=[e0, e1],
        pinned_id=None,
        config_path=tmp_path / "config.toml",
    )

    entry = resolve_pinned_entry(config)

    assert entry == e0


def test_resolve_pinned_entry_returns_pinned_match(tmp_path):
    e0 = EmbeddingEntry(id="m0", endpoint="http://127.0.0.1:8081/v1")
    e1 = EmbeddingEntry(id="m1", endpoint="http://127.0.0.1:8082/v1")
    config = EngramConfig(
        embeddings=[e0, e1],
        pinned_id=e1.id,
        config_path=tmp_path / "config.toml",
    )

    entry = resolve_pinned_entry(config)

    assert entry == e1
    assert entry != e0


def test_resolve_pinned_entry_raises_on_empty_embeddings(tmp_path):
    config = EngramConfig(
        embeddings=[], pinned_id=None, config_path=tmp_path / "config.toml"
    )

    with pytest.raises(ValueError):
        resolve_pinned_entry(config)


def test_resolve_pinned_entry_raises_on_unknown_pinned_id(tmp_path):
    e0 = EmbeddingEntry(id="m0", endpoint="http://127.0.0.1:8081/v1")
    config = EngramConfig(
        embeddings=[e0],
        pinned_id="ghost",
        config_path=tmp_path / "config.toml",
    )

    with pytest.raises(ValueError) as excinfo:
        resolve_pinned_entry(config)

    assert "ghost" in str(excinfo.value)


# --- PackBudget / [pack] config ---


def test_packbudget_defaults_are_the_five_documented_values():
    budget = PackBudget()

    assert budget.hard_cap_tokens == 4000
    assert budget.similar_cap_tokens == 1400
    assert budget.reuse_cap_tokens == 1000
    assert budget.findings_cap_tokens == 1000
    assert budget.prose_cap_tokens == 500


def test_load_config_defaults_pack_budget_when_pack_table_absent(tmp_path):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "[[embedding]]\n"
        'id = "model-a"\n'
        'endpoint = "http://127.0.0.1:8081/v1"\n'
        "\n"
        "[pinned]\n"
        'id = ""\n',
    )

    config = load_config(path=config_path)

    assert config.pack_budget == PackBudget()


def test_load_config_accepts_pack_table_with_explicit_default_values(tmp_path):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "[[embedding]]\n"
        'id = "model-a"\n'
        'endpoint = "http://127.0.0.1:8081/v1"\n'
        "\n"
        "[pinned]\n"
        'id = ""\n'
        "\n"
        "[pack]\n"
        "hard_cap_tokens = 4000\n"
        "similar_cap_tokens = 1400\n"
        "reuse_cap_tokens = 1000\n"
        "findings_cap_tokens = 1000\n"
        "prose_cap_tokens = 500\n",
    )

    config = load_config(path=config_path)  # must not raise

    assert config.pack_budget == PackBudget()


def test_load_config_reads_full_pack_table_field_by_field(tmp_path):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "[[embedding]]\n"
        'id = "model-a"\n'
        'endpoint = "http://127.0.0.1:8081/v1"\n'
        "\n"
        "[pinned]\n"
        'id = ""\n'
        "\n"
        "[pack]\n"
        "hard_cap_tokens = 8000\n"
        "similar_cap_tokens = 3000\n"
        "reuse_cap_tokens = 2000\n"
        "findings_cap_tokens = 1500\n"
        "prose_cap_tokens = 1000\n",
    )

    config = load_config(path=config_path)

    assert config.pack_budget.hard_cap_tokens == 8000
    assert config.pack_budget.similar_cap_tokens == 3000
    assert config.pack_budget.reuse_cap_tokens == 2000
    assert config.pack_budget.findings_cap_tokens == 1500
    assert config.pack_budget.prose_cap_tokens == 1000


def test_load_config_fills_defaults_for_fields_absent_from_partial_pack_table(tmp_path):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "[[embedding]]\n"
        'id = "model-a"\n'
        'endpoint = "http://127.0.0.1:8081/v1"\n'
        "\n"
        "[pinned]\n"
        'id = ""\n'
        "\n"
        "[pack]\n"
        "hard_cap_tokens = 5000\n"
        "similar_cap_tokens = 2000\n",
    )

    config = load_config(path=config_path)

    assert config.pack_budget.hard_cap_tokens == 5000
    assert config.pack_budget.similar_cap_tokens == 2000
    assert config.pack_budget.reuse_cap_tokens == PackBudget().reuse_cap_tokens
    assert config.pack_budget.findings_cap_tokens == PackBudget().findings_cap_tokens
    assert config.pack_budget.prose_cap_tokens == PackBudget().prose_cap_tokens


def test_load_config_rejects_zero_value_for_pack_cap_field(tmp_path):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "[[embedding]]\n"
        'id = "model-a"\n'
        'endpoint = "http://127.0.0.1:8081/v1"\n'
        "\n"
        "[pinned]\n"
        'id = ""\n'
        "\n"
        "[pack]\n"
        "reuse_cap_tokens = 0\n",
    )

    with pytest.raises(ValueError):
        load_config(path=config_path)


def test_load_config_rejects_negative_value_for_pack_cap_field(tmp_path):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "[[embedding]]\n"
        'id = "model-a"\n'
        'endpoint = "http://127.0.0.1:8081/v1"\n'
        "\n"
        "[pinned]\n"
        'id = ""\n'
        "\n"
        "[pack]\n"
        "reuse_cap_tokens = -5\n",
    )

    with pytest.raises(ValueError):
        load_config(path=config_path)


def test_load_config_rejects_string_value_for_pack_cap_field(tmp_path):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "[[embedding]]\n"
        'id = "model-a"\n'
        'endpoint = "http://127.0.0.1:8081/v1"\n'
        "\n"
        "[pinned]\n"
        'id = ""\n'
        "\n"
        "[pack]\n"
        'findings_cap_tokens = "1000"\n',
    )

    with pytest.raises(ValueError):
        load_config(path=config_path)


def test_load_config_rejects_float_value_for_pack_cap_field(tmp_path):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "[[embedding]]\n"
        'id = "model-a"\n'
        'endpoint = "http://127.0.0.1:8081/v1"\n'
        "\n"
        "[pinned]\n"
        'id = ""\n'
        "\n"
        "[pack]\n"
        "findings_cap_tokens = 1000.0\n",
    )

    with pytest.raises(ValueError):
        load_config(path=config_path)


def test_load_config_rejects_boolean_value_for_pack_cap_field(tmp_path):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "[[embedding]]\n"
        'id = "model-a"\n'
        'endpoint = "http://127.0.0.1:8081/v1"\n'
        "\n"
        "[pinned]\n"
        'id = ""\n'
        "\n"
        "[pack]\n"
        "prose_cap_tokens = true\n",
    )

    with pytest.raises(ValueError):
        load_config(path=config_path)


def test_load_config_rejects_pack_table_whose_section_caps_exceed_hard_cap(tmp_path):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "[[embedding]]\n"
        'id = "model-a"\n'
        'endpoint = "http://127.0.0.1:8081/v1"\n'
        "\n"
        "[pinned]\n"
        'id = ""\n'
        "\n"
        "[pack]\n"
        "hard_cap_tokens = 3000\n",
    )

    with pytest.raises(ValueError) as excinfo:
        load_config(path=config_path)

    assert "3000" in str(excinfo.value)


def test_load_config_accepts_pack_table_where_section_caps_sum_exactly_to_hard_cap(
    tmp_path,
):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "[[embedding]]\n"
        'id = "model-a"\n'
        'endpoint = "http://127.0.0.1:8081/v1"\n'
        "\n"
        "[pinned]\n"
        'id = ""\n'
        "\n"
        "[pack]\n"
        "hard_cap_tokens = 2000\n"
        "similar_cap_tokens = 500\n"
        "reuse_cap_tokens = 500\n"
        "findings_cap_tokens = 500\n"
        "prose_cap_tokens = 400\n",
    )

    config = load_config(path=config_path)  # must not raise: sum == hard cap exactly

    assert config.pack_budget.hard_cap_tokens == 2000
    assert config.pack_budget.similar_cap_tokens == 500
    assert config.pack_budget.reuse_cap_tokens == 500
    assert config.pack_budget.findings_cap_tokens == 500
    assert config.pack_budget.prose_cap_tokens == 400

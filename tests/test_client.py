import email.message
import http.server
import io
import json
import os
import socket
import threading
import time
import tomllib
import urllib.request
from pathlib import Path

import pytest

from engram import client
from engram.client import (
    EMBED_BATCH_SIZE,
    EMBED_MAX_CHARS,
    EmbeddingEntry,
    EmbeddingModelIdentityError,
    EmbeddingPreflightError,
    EmbeddingServerError,
    EngramConfig,
    ServerLease,
    Vector,
    embed,
    ensure_served,
    load_config,
    preflight,
    resolve_pinned_entry,
    stop_served,
)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _free_port_v6() -> int:
    with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as s:
        s.bind(("::1", 0))
        return s.getsockname()[1]


def _input_list(payload: dict) -> list:
    inputs = payload.get("input", [])
    return [inputs] if isinstance(inputs, str) else inputs


class _MockEmbeddingServer:
    """In-process stand-in for llama-server's /v1/embeddings endpoint."""

    def __init__(self, port: int, model_id: str):
        self.port = port
        self.model_id = model_id
        self.requests: list[dict] = []
        self.responder = self._default_responder
        outer = self

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
                if self.path.rstrip("/") == "/v1/models":
                    body = json.dumps(
                        {"object": "list", "data": [{"id": outer.model_id, "object": "model"}]}
                    ).encode()
                    self._send(200, body)
                else:
                    self._send(404, b"{}")

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(n)
                if self.path.rstrip("/") != "/v1/embeddings":
                    self._send(404, b"{}")
                    return
                payload = json.loads(raw) if raw else {}
                outer.requests.append(payload)
                code, body = outer.responder(payload)
                self._send(code, body)

        self._server = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def _default_responder(self, payload: dict):
        inputs = _input_list(payload)
        data = [
            {"index": i, "embedding": [float(i)] * 4, "object": "embedding"}
            for i in range(len(inputs))
        ]
        body = json.dumps({"object": "list", "model": self.model_id, "data": data}).encode()
        return 200, body

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/v1"

    def start(self):
        self._thread.start()

    def stop(self):
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)


@pytest.fixture
def mock_server():
    port = _free_port()
    server = _MockEmbeddingServer(port, model_id="test-model")
    server.start()
    yield server
    server.stop()


def _responder_with_broken_batch(model_id: str, broken_data: list):
    def responder(payload):
        inputs = _input_list(payload)
        if len(inputs) == 1:
            data = [{"index": 0, "embedding": [0.1, 0.2, 0.3, 0.4], "object": "embedding"}]
            return 200, json.dumps({"object": "list", "model": model_id, "data": data}).encode()
        return 200, json.dumps({"object": "list", "model": model_id, "data": broken_data}).encode()

    return responder


_STUB_LLAMA_SERVER = '''#!/usr/bin/env python3
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
'''


def _write_stub_llama_server(bin_dir: Path) -> Path:
    stub_path = bin_dir / "llama-server"
    stub_path.write_text(_STUB_LLAMA_SERVER)
    stub_path.chmod(0o755)
    return stub_path


_STUB_LLAMA_SERVER_NEVER_READY = '''#!/usr/bin/env python3
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
'''


def _write_never_ready_stub_llama_server(bin_dir: Path) -> Path:
    stub_path = bin_dir / "llama-server"
    stub_path.write_text(_STUB_LLAMA_SERVER_NEVER_READY)
    stub_path.chmod(0o755)
    return stub_path


_STUB_LLAMA_SERVER_IGNORES_SIGTERM = '''#!/usr/bin/env python3
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
'''


def _write_stub_llama_server_ignoring_sigterm(bin_dir: Path) -> Path:
    stub_path = bin_dir / "llama-server"
    stub_path.write_text(_STUB_LLAMA_SERVER_IGNORES_SIGTERM)
    stub_path.chmod(0o755)
    return stub_path


_STUB_LLAMA_SERVER_WRONG_MODEL_ID = '''#!/usr/bin/env python3
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
'''


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
        '[[embedding]]\n'
        'id = "remote-model"\n'
        'endpoint = "http://93.184.216.34:8081/v1"\n'
        "\n"
        "[pinned]\n"
        'id = ""\n'
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


def test_ensure_served_raises_when_llama_server_missing_from_path(tmp_path, monkeypatch):
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


def test_embed_raises_on_missing_index_in_response(mock_server):
    entry = EmbeddingEntry(id=mock_server.model_id, endpoint=mock_server.base_url)
    mock_server.responder = _responder_with_broken_batch(
        mock_server.model_id,
        [{"index": 0, "embedding": [0.1, 0.2, 0.3, 0.4], "object": "embedding"}],
    )

    with pytest.raises(EmbeddingPreflightError):
        embed(["alpha", "beta"], entry)


def test_embed_raises_on_duplicate_index_in_response(mock_server):
    entry = EmbeddingEntry(id=mock_server.model_id, endpoint=mock_server.base_url)
    mock_server.responder = _responder_with_broken_batch(
        mock_server.model_id,
        [
            {"index": 0, "embedding": [0.1, 0.2, 0.3, 0.4], "object": "embedding"},
            {"index": 0, "embedding": [0.5, 0.6, 0.7, 0.8], "object": "embedding"},
        ],
    )

    with pytest.raises(EmbeddingPreflightError):
        embed(["alpha", "beta"], entry)


def test_embed_raises_on_mismatched_vector_dimension_in_response(mock_server):
    entry = EmbeddingEntry(id=mock_server.model_id, endpoint=mock_server.base_url)
    mock_server.responder = _responder_with_broken_batch(
        mock_server.model_id,
        [
            {"index": 0, "embedding": [0.1, 0.2, 0.3, 0.4], "object": "embedding"},
            {"index": 1, "embedding": [0.5, 0.6], "object": "embedding"},
        ],
    )

    with pytest.raises(EmbeddingPreflightError):
        embed(["alpha", "beta"], entry)


def test_embed_preserves_original_input_order_despite_out_of_order_response(mock_server):
    entry = EmbeddingEntry(id=mock_server.model_id, endpoint=mock_server.base_url)

    def shuffled_responder(payload):
        inputs = _input_list(payload)
        items = [
            {"index": i, "embedding": [float(i)] * 4, "object": "embedding"}
            for i in range(len(inputs))
        ]
        if len(items) > 1:
            items = list(reversed(items))
        body = json.dumps({"object": "list", "model": mock_server.model_id, "data": items}).encode()
        return 200, body

    mock_server.responder = shuffled_responder

    vectors = embed(["alpha", "beta", "gamma"], entry)

    assert all(isinstance(v, Vector) for v in vectors)
    assert [v.values for v in vectors] == [[0.0] * 4, [1.0] * 4, [2.0] * 4]
    assert all(v.dim == 4 for v in vectors)


def test_embed_truncates_long_text_only_in_outgoing_request(mock_server):
    entry = EmbeddingEntry(id=mock_server.model_id, endpoint=mock_server.base_url)
    long_text = "x" * 10000
    texts = [long_text, "short"]

    vectors = embed(texts, entry)

    assert len(vectors) == 2
    assert vectors[0].values == [0.0] * 4
    assert vectors[1].values == [1.0] * 4

    batch_payloads = [r for r in mock_server.requests if len(_input_list(r)) == 2]
    assert len(batch_payloads) == 1
    sent = _input_list(batch_payloads[0])
    assert len(sent[0]) == EMBED_MAX_CHARS
    assert sent[0] == long_text[:EMBED_MAX_CHARS]
    assert sent[1] == "short"


# --- regression: embed() rejects empty/non-finite embedding vectors ---


def test_embed_raises_on_empty_embedding_vector_in_response(mock_server):
    entry = EmbeddingEntry(id=mock_server.model_id, endpoint=mock_server.base_url)
    mock_server.responder = _responder_with_broken_batch(
        mock_server.model_id,
        [
            {"index": 0, "embedding": [], "object": "embedding"},
            {"index": 1, "embedding": [0.5, 0.6, 0.7, 0.8], "object": "embedding"},
        ],
    )

    with pytest.raises(EmbeddingPreflightError):
        embed(["alpha", "beta"], entry)


def test_embed_raises_on_non_finite_value_in_embedding_vector(mock_server):
    entry = EmbeddingEntry(id=mock_server.model_id, endpoint=mock_server.base_url)
    mock_server.responder = _responder_with_broken_batch(
        mock_server.model_id,
        [
            {"index": 0, "embedding": [0.1, float("nan"), 0.3, 0.4], "object": "embedding"},
            {"index": 1, "embedding": [0.5, float("inf"), 0.7, 0.8], "object": "embedding"},
        ],
    )

    with pytest.raises(EmbeddingPreflightError):
        embed(["alpha", "beta"], entry)


# --- regression: ensure_served() reaps the spawned process on readiness timeout ---


def test_ensure_served_terminates_orphaned_process_on_readiness_timeout(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_never_ready_stub_llama_server(bin_dir)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setattr(client, "EMBED_REQUEST_TIMEOUT_S", 0.5)

    port = _free_port()
    entry = EmbeddingEntry(id="never-ready-model", endpoint=f"http://127.0.0.1:{port}/v1")

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


def test_stop_served_escalates_to_sigkill_when_process_ignores_sigterm(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_stub_llama_server_ignoring_sigterm(bin_dir)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setattr(client, "STOP_WAIT_TIMEOUT_S", 0.5)

    port = _free_port()
    entry = EmbeddingEntry(
        id="stub-model-ignores-sigterm", endpoint=f"http://127.0.0.1:{port}/v1"
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


# --- regression: embed() names the failed batch's index range ---


def test_embed_names_batch_index_range_on_post_failure(mock_server):
    entry = EmbeddingEntry(id=mock_server.model_id, endpoint=mock_server.base_url)

    def responder(payload):
        inputs = _input_list(payload)
        if len(inputs) == 1:
            data = [{"index": 0, "embedding": [0.1, 0.2, 0.3, 0.4], "object": "embedding"}]
            body = json.dumps(
                {"object": "list", "model": mock_server.model_id, "data": data}
            ).encode()
            return 200, body
        return 500, b'{"error": "boom"}'

    mock_server.responder = responder

    with pytest.raises(EmbeddingPreflightError) as excinfo:
        embed(["alpha", "beta"], entry)

    message = str(excinfo.value)
    assert "0" in message
    assert "1" in message


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


def test_loopback_redirect_handler_refuses_off_machine_target():
    handler = client._LoopbackRedirectHandler()
    req = urllib.request.Request("http://127.0.0.1:8081/v1/embeddings")
    headers = email.message.Message()
    fp = io.BytesIO(b"")

    with pytest.raises(Exception):
        handler.redirect_request(req, fp, 302, "Found", headers, "http://93.184.216.34/evil")

    with pytest.raises(Exception):
        handler.redirect_request(req, fp, 302, "Found", headers, "http://127.0.0.2:9/x")


def test_post_embeddings_refuses_redirect_to_reachable_off_machine_loopback_host():
    """End-to-end: drives _post_embeddings's real HTTP call through _OPENER
    against a real 302 redirect, rather than calling the redirect handler
    directly.

    The redirect target (IPv6 loopback ::1, not in _LOOPBACK_HOSTS) is a
    genuinely reachable, listening server that would answer with a valid
    embedding if followed. This makes the assertion below bind to _OPENER
    being wired in: with _OPENER, _LoopbackRedirectHandler refuses the
    redirect and this raises EmbeddingPreflightError. If _post_embeddings
    ever stopped routing through _OPENER (e.g. plain urllib.request.urlopen),
    the default redirect handler would follow the redirect to the reachable
    stub below and the call would SUCCEED instead of raising, so this test
    would fail.
    """
    reachable_port = _free_port_v6()

    class ReachableHandler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _respond(self):
            body = json.dumps(
                {
                    "object": "list",
                    "model": "off-machine",
                    "data": [
                        {"index": 0, "embedding": [9.0, 9.0, 9.0, 9.0], "object": "embedding"}
                    ],
                }
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
    reachable_thread = threading.Thread(target=reachable_server.serve_forever, daemon=True)
    reachable_thread.start()

    redirect_target = f"http://[::1]:{reachable_port}/v1/embeddings"

    class RedirectHandler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            self.rfile.read(n)
            self.send_response(302, "Found")
            self.send_header("Location", redirect_target)
            self.send_header("Content-Length", "0")
            self.end_headers()

    redirect_port = _free_port()
    redirect_server = http.server.HTTPServer(("127.0.0.1", redirect_port), RedirectHandler)
    redirect_thread = threading.Thread(target=redirect_server.serve_forever, daemon=True)
    redirect_thread.start()

    try:
        entry = EmbeddingEntry(id="x", endpoint=f"http://127.0.0.1:{redirect_port}/v1")

        with pytest.raises(EmbeddingPreflightError):
            client._post_embeddings(entry, ["hello"])
    finally:
        redirect_server.shutdown()
        redirect_server.server_close()
        redirect_thread.join(timeout=5)
        reachable_server.shutdown()
        reachable_server.server_close()
        reachable_thread.join(timeout=5)


# --- regression: embed() fails loud on a null data field instead of raising TypeError ---


def test_embed_raises_on_null_data_field(mock_server):
    entry = EmbeddingEntry(id=mock_server.model_id, endpoint=mock_server.base_url)
    mock_server.responder = lambda payload: (
        200,
        json.dumps({"object": "list", "model": mock_server.model_id, "data": None}).encode(),
    )

    with pytest.raises(EmbeddingPreflightError):
        embed(["alpha"], entry)


def test_embed_raises_on_null_data_element(mock_server):
    entry = EmbeddingEntry(id=mock_server.model_id, endpoint=mock_server.base_url)
    mock_server.responder = lambda payload: (
        200,
        json.dumps({"object": "list", "model": mock_server.model_id, "data": [None]}).encode(),
    )

    with pytest.raises(EmbeddingPreflightError):
        embed(["alpha"], entry)


def test_embed_raises_on_scalar_data_element(mock_server):
    entry = EmbeddingEntry(id=mock_server.model_id, endpoint=mock_server.base_url)
    mock_server.responder = lambda payload: (
        200,
        json.dumps({"object": "list", "model": mock_server.model_id, "data": [1]}).encode(),
    )

    with pytest.raises(EmbeddingPreflightError):
        embed(["alpha"], entry)


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
        "[pinned]\n"
        'id = ""\n'
    )

    with pytest.raises(ValueError):
        load_config(path=config_path)


def test_load_config_rejects_pinned_id_absent_from_shortlist(tmp_path):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        '[[embedding]]\n'
        'id = "model-a"\n'
        'endpoint = "http://127.0.0.1:8081/v1"\n'
        "\n"
        "[pinned]\n"
        'id = "model-b"\n'
    )

    with pytest.raises(ValueError) as excinfo:
        load_config(path=config_path)

    assert "model-b" in str(excinfo.value)


# --- resolve_pinned_entry ---


def test_resolve_pinned_entry_returns_first_when_unpinned(tmp_path):
    e0 = EmbeddingEntry(id="m0", endpoint="http://127.0.0.1:8081/v1")
    e1 = EmbeddingEntry(id="m1", endpoint="http://127.0.0.1:8082/v1")
    config = EngramConfig(
        embeddings=[e0, e1], pinned_id=None, config_path=tmp_path / "config.toml"
    )

    entry = resolve_pinned_entry(config)

    assert entry == e0


def test_resolve_pinned_entry_returns_pinned_match(tmp_path):
    e0 = EmbeddingEntry(id="m0", endpoint="http://127.0.0.1:8081/v1")
    e1 = EmbeddingEntry(id="m1", endpoint="http://127.0.0.1:8082/v1")
    config = EngramConfig(
        embeddings=[e0, e1], pinned_id=e1.id, config_path=tmp_path / "config.toml"
    )

    entry = resolve_pinned_entry(config)

    assert entry == e1
    assert entry != e0


def test_resolve_pinned_entry_raises_on_empty_embeddings(tmp_path):
    config = EngramConfig(embeddings=[], pinned_id=None, config_path=tmp_path / "config.toml")

    with pytest.raises(ValueError):
        resolve_pinned_entry(config)


def test_resolve_pinned_entry_raises_on_unknown_pinned_id(tmp_path):
    e0 = EmbeddingEntry(id="m0", endpoint="http://127.0.0.1:8081/v1")
    config = EngramConfig(
        embeddings=[e0], pinned_id="ghost", config_path=tmp_path / "config.toml"
    )

    with pytest.raises(ValueError) as excinfo:
        resolve_pinned_entry(config)

    assert "ghost" in str(excinfo.value)

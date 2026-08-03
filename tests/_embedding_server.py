import http.server
import json
import socket
import threading


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
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
        # Set to a dict to serve llama.cpp's /props; left None the endpoint 404s
        # it, which is how a plain OpenAI-compatible server behaves.
        self.props: dict | None = None
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                """Suppress default request logging to stderr."""

            def _send(self, code, body):
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                if self.path.rstrip("/") == "/props" and outer.props is not None:
                    self._send(200, json.dumps(outer.props).encode())
                elif self.path.rstrip("/") == "/v1/models":
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


def _embed_payloads(server: "_MockEmbeddingServer") -> list[dict]:
    """Recorded requests minus preflight's single-string `ping` probe.

    `embed()` calls `ensure_served` -> `preflight` on every invocation, so the
    server records a probe ahead of the real batches; assertions about how
    `embed()` batched its input must not count it.
    """
    return [payload for payload in server.requests if payload.get("input") != "ping"]


def _responder_with_broken_batch(model_id: str, broken_data: list):
    def responder(payload):
        inputs = _input_list(payload)
        if len(inputs) == 1:
            data = [{"index": 0, "embedding": [0.1, 0.2, 0.3, 0.4], "object": "embedding"}]
            return 200, json.dumps({"object": "list", "model": model_id, "data": data}).encode()
        return 200, json.dumps({"object": "list", "model": model_id, "data": broken_data}).encode()

    return responder

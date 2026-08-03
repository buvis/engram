import json

import pytest
from _embedding_server import (
    _embed_payloads,
    _free_port,
    _input_list,
    _MockEmbeddingServer,
    _responder_with_broken_batch,
)

from engram import client
from engram.client import (
    EMBED_BATCH_MAX_CHARS,
    EMBED_BATCH_SIZE,
    EMBED_MAX_CHARS,
    EmbeddingDegradedError,
    EmbeddingEntry,
    EmbeddingPreflightError,
    ServerLease,
    Vector,
    embed,
)


@pytest.fixture
def mock_server():
    port = _free_port()
    server = _MockEmbeddingServer(port, model_id="test-model")
    server.start()
    yield server
    server.stop()


# --- embed(): response parsing / validation ---


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


def test_embed_preserves_original_input_order_despite_out_of_order_response(
    mock_server,
):
    entry = EmbeddingEntry(id=mock_server.model_id, endpoint=mock_server.base_url)

    def shuffled_responder(payload):
        inputs = _input_list(payload)
        items = [
            {"index": i, "embedding": [float(i)] * 4, "object": "embedding"}
            for i in range(len(inputs))
        ]
        if len(items) > 1:
            items = list(reversed(items))
        body = json.dumps(
            {"object": "list", "model": mock_server.model_id, "data": items},
        ).encode()
        return 200, body

    mock_server.responder = shuffled_responder

    vectors = embed(["alpha", "beta", "gamma"], entry)

    assert all(isinstance(v, Vector) for v in vectors)
    assert [v.values for v in vectors] == [[0.0] * 4, [1.0] * 4, [2.0] * 4]
    assert all(v.dim == 4 for v in vectors)


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
            {
                "index": 0,
                "embedding": [0.1, float("nan"), 0.3, 0.4],
                "object": "embedding",
            },
            {
                "index": 1,
                "embedding": [0.5, float("inf"), 0.7, 0.8],
                "object": "embedding",
            },
        ],
    )

    with pytest.raises(EmbeddingPreflightError):
        embed(["alpha", "beta"], entry)


# --- regression: embed() names the failed batch's index range ---


def test_embed_names_batch_index_range_on_post_failure(mock_server):
    entry = EmbeddingEntry(id=mock_server.model_id, endpoint=mock_server.base_url)

    def responder(payload):
        inputs = _input_list(payload)
        if len(inputs) == 1:
            data = [
                {"index": 0, "embedding": [0.1, 0.2, 0.3, 0.4], "object": "embedding"},
            ]
            body = json.dumps(
                {"object": "list", "model": mock_server.model_id, "data": data},
            ).encode()
            return 200, body
        return 500, b'{"error": "boom"}'

    mock_server.responder = responder

    with pytest.raises(EmbeddingPreflightError) as excinfo:
        embed(["alpha", "beta"], entry)

    message = str(excinfo.value)
    assert "0" in message
    assert "1" in message


# --- regression: embed() fails loud on a null data field instead of raising TypeError ---


def test_embed_raises_on_null_data_field(mock_server):
    entry = EmbeddingEntry(id=mock_server.model_id, endpoint=mock_server.base_url)
    mock_server.responder = lambda payload: (
        200,
        json.dumps(
            {"object": "list", "model": mock_server.model_id, "data": None},
        ).encode(),
    )

    with pytest.raises(EmbeddingPreflightError):
        embed(["alpha"], entry)


def test_embed_raises_on_null_data_element(mock_server):
    entry = EmbeddingEntry(id=mock_server.model_id, endpoint=mock_server.base_url)
    mock_server.responder = lambda payload: (
        200,
        json.dumps(
            {"object": "list", "model": mock_server.model_id, "data": [None]},
        ).encode(),
    )

    with pytest.raises(EmbeddingPreflightError):
        embed(["alpha"], entry)


def test_embed_raises_on_scalar_data_element(mock_server):
    entry = EmbeddingEntry(id=mock_server.model_id, endpoint=mock_server.base_url)
    mock_server.responder = lambda payload: (
        200,
        json.dumps(
            {"object": "list", "model": mock_server.model_id, "data": [1]},
        ).encode(),
    )

    with pytest.raises(EmbeddingPreflightError):
        embed(["alpha"], entry)


# --- regression: embed() budgets a request's total size, not just its count ---
# Batching by a fixed text count let long, token-dense chunks (transcript error
# turns, minified code) build a request far past what llama-server can hold; it
# closed the connection mid-batch and the whole index run died.


def test_embed_keeps_every_request_within_the_char_budget(mock_server):
    entry = EmbeddingEntry(id=mock_server.model_id, endpoint=mock_server.base_url)
    dense = ["x" * EMBED_MAX_CHARS] * 5

    vectors = embed(dense, entry)

    assert len(vectors) == 5
    payloads = _embed_payloads(mock_server)
    assert len(payloads) > 1
    for payload in payloads:
        assert sum(len(t) for t in _input_list(payload)) <= EMBED_BATCH_MAX_CHARS


def test_embed_sends_a_max_length_text_alone_rather_than_dropping_it(mock_server):
    entry = EmbeddingEntry(id=mock_server.model_id, endpoint=mock_server.base_url)

    vectors = embed(["short", "y" * EMBED_MAX_CHARS, "also short"], entry)

    assert len(vectors) == 3
    sent = [_input_list(payload) for payload in _embed_payloads(mock_server)]
    assert [len(batch) for batch in sent] == [1, 1, 1]


def test_embed_still_packs_short_texts_into_one_request(mock_server):
    entry = EmbeddingEntry(id=mock_server.model_id, endpoint=mock_server.base_url)
    short = ["alpha"] * EMBED_BATCH_SIZE

    vectors = embed(short, entry)

    assert len(vectors) == EMBED_BATCH_SIZE
    assert len(_embed_payloads(mock_server)) == 1


def test_embed_names_the_batch_index_range_of_a_later_budgeted_request(mock_server):
    entry = EmbeddingEntry(id=mock_server.model_id, endpoint=mock_server.base_url)

    def fail_after_first(payload):
        if len(_embed_payloads(mock_server)) > 1:
            return 500, b'{"error": "boom"}'
        data = [
            {"index": i, "embedding": [float(i)] * 4, "object": "embedding"}
            for i in range(len(_input_list(payload)))
        ]
        body = json.dumps(
            {"object": "list", "model": mock_server.model_id, "data": data},
        )
        return 200, body.encode()

    mock_server.responder = fail_after_first

    with pytest.raises(EmbeddingPreflightError) as excinfo:
        embed(["z" * EMBED_MAX_CHARS] * 3, entry)

    assert "batch indices 1..1" in str(excinfo.value)


# --- regression: embed() recycles a server that degrades mid-run ---
# Measured on llama-server --embedding under sustained real load: it starts
# answering HTTP 200 with an all-null embedding array, and once poisoned it can
# null every later request including "hello world". Engram spawns the server, so
# it owns its health: reap, respawn, retry the request once.


def _null_vector_body(model_id: str, count: int) -> bytes:
    data = [
        {"index": i, "embedding": [None] * 4, "object": "embedding"}
        for i in range(count)
    ]
    return json.dumps({"object": "list", "model": model_id, "data": data}).encode()


def _ok_body(model_id: str, count: int) -> bytes:
    data = [
        {"index": i, "embedding": [float(i)] * 4, "object": "embedding"}
        for i in range(count)
    ]
    return json.dumps({"object": "list", "model": model_id, "data": data}).encode()


def _fake_lifecycle(monkeypatch, *, spawned: bool) -> list[str]:
    """Replace spawn/stop with recorders and hand embed() the given lease kind."""
    calls: list[str] = []

    def fake_ensure_served(entry):
        calls.append("ensure")
        return ServerLease(entry=entry, spawned=spawned, pid=4242 if spawned else None)

    def fake_stop_served(lease):
        calls.append("stop")

    monkeypatch.setattr(client, "ensure_served", fake_ensure_served)
    monkeypatch.setattr(client, "stop_served", fake_stop_served)
    return calls


def test_embed_recycles_a_degraded_server_and_retries_the_request(
    mock_server,
    monkeypatch,
):
    entry = EmbeddingEntry(id=mock_server.model_id, endpoint=mock_server.base_url)
    calls = _fake_lifecycle(monkeypatch, spawned=True)

    def nulls_then_healthy(payload):
        count = len(_input_list(payload))
        if len(_embed_payloads(mock_server)) == 1:
            return 200, _null_vector_body(mock_server.model_id, count)
        return 200, _ok_body(mock_server.model_id, count)

    mock_server.responder = nulls_then_healthy

    vectors = embed(["alpha", "beta"], entry)

    assert [v.values for v in vectors] == [[0.0] * 4, [1.0] * 4]
    assert calls == ["ensure", "stop", "ensure"]


def test_embed_fails_loud_when_the_replacement_server_is_also_degraded(
    mock_server,
    monkeypatch,
):
    entry = EmbeddingEntry(id=mock_server.model_id, endpoint=mock_server.base_url)
    calls = _fake_lifecycle(monkeypatch, spawned=True)
    mock_server.responder = lambda payload: (
        200,
        _null_vector_body(mock_server.model_id, len(_input_list(payload))),
    )

    with pytest.raises(EmbeddingDegradedError):
        embed(["alpha"], entry)

    # Exactly one recycle: a server that stays sick must not loop forever.
    assert calls == ["ensure", "stop", "ensure"]


# --- regression: the char budget comes from the model's real context ---
# EMBED_MAX_CHARS was a single Qwen-derived constant applied to every model, so
# engram truncated an 8000-char chunk (~5225 dense tokens) and sent it to a
# 2048-context model, which rejected it: "input (5225 tokens) is larger than the
# max context size (2048 tokens)". The limit is a fixed property of the model and
# llama.cpp reports it on /props even when spawned with a larger -c.


def _longest_sent(mock_server) -> int:
    return max(
        len(t) for payload in _embed_payloads(mock_server) for t in _input_list(payload)
    )


def test_embed_truncates_to_the_context_the_server_reports(mock_server, monkeypatch):
    entry = EmbeddingEntry(id=mock_server.model_id, endpoint=mock_server.base_url)
    monkeypatch.setattr(client, "_max_chars_by_endpoint", {})
    mock_server.props = {"default_generation_settings": {"n_ctx": 2048}}

    embed(["x" * EMBED_MAX_CHARS], entry)

    assert _longest_sent(mock_server) == int(2048 / client.WORST_CASE_TOKENS_PER_CHAR)


def test_embed_keeps_the_full_ceiling_for_a_roomy_context(mock_server, monkeypatch):
    entry = EmbeddingEntry(id=mock_server.model_id, endpoint=mock_server.base_url)
    monkeypatch.setattr(client, "_max_chars_by_endpoint", {})
    mock_server.props = {"default_generation_settings": {"n_ctx": 8192}}

    embed(["x" * (EMBED_MAX_CHARS * 2)], entry)

    # 8192 / 0.75 exceeds the ceiling, so the corpus-wide cap still governs and
    # nothing changes for the model the live index was built with.
    assert _longest_sent(mock_server) == EMBED_MAX_CHARS


def test_embed_falls_back_to_the_ceiling_when_props_is_unavailable(
    mock_server, monkeypatch
):
    entry = EmbeddingEntry(id=mock_server.model_id, endpoint=mock_server.base_url)
    monkeypatch.setattr(client, "_max_chars_by_endpoint", {})
    mock_server.props = None  # a plain OpenAI-compatible server 404s /props

    embed(["x" * (EMBED_MAX_CHARS * 2)], entry)

    assert _longest_sent(mock_server) == EMBED_MAX_CHARS


def test_embed_never_restarts_a_server_it_did_not_spawn(mock_server, monkeypatch):
    entry = EmbeddingEntry(id=mock_server.model_id, endpoint=mock_server.base_url)
    calls = _fake_lifecycle(monkeypatch, spawned=False)
    mock_server.responder = lambda payload: (
        200,
        _null_vector_body(mock_server.model_id, len(_input_list(payload))),
    )

    with pytest.raises(EmbeddingDegradedError):
        embed(["alpha"], entry)

    assert calls == ["ensure"]


# --- regression: embed() treats a server-side HTTP 5xx as degradation too ---
# A llama-server under sustained load starts answering every embed with HTTP
# 500 while /v1/models still returns 200 - the same degradation as null
# vectors, just a different shape. Observed live: "HTTP Error 500" on batch
# indices 3..5 during a real eval-harness run, which killed the whole index.
# A 4xx is the request's fault, not the server's, so it must not recycle.


def test_embed_recycles_a_5xx_from_a_spawned_server_and_retries_the_request(
    mock_server,
    monkeypatch,
):
    entry = EmbeddingEntry(id=mock_server.model_id, endpoint=mock_server.base_url)
    calls = _fake_lifecycle(monkeypatch, spawned=True)

    def error_then_healthy(payload):
        count = len(_input_list(payload))
        if len(_embed_payloads(mock_server)) == 1:
            return 500, b'{"error": "boom"}'
        return 200, _ok_body(mock_server.model_id, count)

    mock_server.responder = error_then_healthy

    vectors = embed(["alpha", "beta"], entry)

    assert [v.values for v in vectors] == [[0.0] * 4, [1.0] * 4]
    assert calls == ["ensure", "stop", "ensure"]


def test_embed_treats_a_4xx_as_a_bad_request_not_a_degradation(
    mock_server, monkeypatch
):
    entry = EmbeddingEntry(id=mock_server.model_id, endpoint=mock_server.base_url)
    calls = _fake_lifecycle(monkeypatch, spawned=True)
    mock_server.responder = lambda payload: (400, b'{"error": "bad request"}')

    with pytest.raises(EmbeddingPreflightError) as excinfo:
        embed(["alpha"], entry)

    assert not isinstance(excinfo.value, EmbeddingDegradedError)
    assert calls == ["ensure"]


def test_embed_never_restarts_an_unspawned_server_on_a_5xx(mock_server, monkeypatch):
    entry = EmbeddingEntry(id=mock_server.model_id, endpoint=mock_server.base_url)
    calls = _fake_lifecycle(monkeypatch, spawned=False)
    mock_server.responder = lambda payload: (500, b'{"error": "boom"}')

    with pytest.raises(EmbeddingPreflightError):
        embed(["alpha"], entry)

    assert calls == ["ensure"]

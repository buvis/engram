import json

import pytest

from engram.client import (
    EMBED_BATCH_MAX_CHARS,
    EMBED_BATCH_SIZE,
    EMBED_MAX_CHARS,
    EmbeddingEntry,
    EmbeddingPreflightError,
    Vector,
    embed,
)

from _embedding_server import (
    _MockEmbeddingServer,
    _embed_payloads,
    _free_port,
    _input_list,
    _responder_with_broken_batch,
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
        body = json.dumps({"object": "list", "model": mock_server.model_id, "data": data})
        return 200, body.encode()

    mock_server.responder = fail_after_first

    with pytest.raises(EmbeddingPreflightError) as excinfo:
        embed(["z" * EMBED_MAX_CHARS] * 3, entry)

    assert "batch indices 1..1" in str(excinfo.value)

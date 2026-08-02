import json

import pytest

from engram.client import EmbeddingEntry, EmbeddingPreflightError, Vector, embed

from _embedding_server import (
    _MockEmbeddingServer,
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

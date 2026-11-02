"""Download integrity and interruption recovery without network access."""

import hashlib
import io
import json
from pathlib import Path
from urllib.request import Request

import pytest

from eval.fetch_models import fetch


def test_resume_cleans_redundant_part_after_successful_checksum(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = b"GGUFabcd"
    metadata = [
        {
            "path": "model-Q8_0.gguf",
            "size": len(payload),
            "lfs": {"oid": hashlib.sha256(payload).hexdigest()},
        }
    ]

    class Response(io.BytesIO):
        status = 206

        def __init__(self, data: bytes, content_range: str = "") -> None:
            super().__init__(data)
            self.headers = {"Content-Range": content_range}

    def open_response(req: str | Request, timeout: int) -> Response:
        if isinstance(req, str):
            return Response(json.dumps(metadata).encode())
        assert req.get_header("Range") == "bytes=4-7"
        return Response(payload[4:], "bytes 4-7/8")

    monkeypatch.setattr("eval.fetch_models.ASSETS", tmp_path)
    monkeypatch.setattr("eval.fetch_models.BLOCK", 4)
    monkeypatch.setattr("eval.fetch_models.urllib.request.urlopen", open_response)
    (tmp_path / "test.partial").write_bytes(payload[:4])
    parts = tmp_path / "test.parts"
    parts.mkdir()
    # Interrupt after flushing a complete block, before removing its temp copy.
    (parts / "0").write_bytes(payload[:4])
    fetch({"name": "test", "id": "author/model:Q8_0"})
    assert (tmp_path / "test.gguf").read_bytes() == payload
    assert not parts.exists()

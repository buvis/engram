"""Fetch public benchmark weights in verified, resumable HTTP ranges."""

import argparse
import hashlib
import json
import time
import tomllib
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from eval.compare_models import ROOT

ASSETS = Path.home() / ".cache/engram/models"
BLOCK = 32 * 1024 * 1024


def fetch(spec: dict[str, Any]) -> None:
    repo, quant = spec["id"].rsplit(":", 1)
    with urllib.request.urlopen(
        f"https://huggingface.co/api/models/{repo}/tree/main", timeout=30
    ) as response:
        files = json.load(response)
    matches = [f for f in files if f["path"].lower().endswith(f"{quant.lower()}.gguf")]
    if len(matches) != 1:
        raise ValueError(
            f"ambiguous quantization for {repo}: {[f['path'] for f in matches]}"
        )
    info = matches[0]
    size = info["size"]
    digest = info.get("lfs", {}).get("oid")
    if not digest:
        raise ValueError("model has no published SHA-256")
    ASSETS.mkdir(parents=True, exist_ok=True)
    target = ASSETS / f"{spec['name']}.gguf"
    manifest = target.with_suffix(".json")
    if target.exists() and manifest.exists():
        saved = json.loads(manifest.read_text())
        if target.stat().st_size == size and saved["sha256"] == digest:
            print(f"{spec['name']}: already verified", flush=True)
            return
    partial = target.with_suffix(".partial")
    parts = ASSETS / f"{spec['name']}.parts"
    parts.mkdir(exist_ok=True)
    offset = partial.stat().st_size if partial.exists() else 0
    if offset != size:
        offset = offset // BLOCK * BLOCK
    with partial.open("ab") as stream:
        stream.truncate(offset)
    blocks = list(range(offset, size, BLOCK))
    started = time.monotonic()

    def get(start: int) -> Path:
        end = min(start + BLOCK, size) - 1
        part = parts / str(start)
        if part.exists() and part.stat().st_size == end - start + 1:
            return part
        url = f"https://huggingface.co/{repo}/resolve/main/{info['path']}?download=true&part={start}"
        for attempt in range(3):
            try:
                req = urllib.request.Request(
                    url, headers={"Range": f"bytes={start}-{end}"}
                )
                with urllib.request.urlopen(req, timeout=60) as response:
                    expected = f"bytes {start}-{end}/{size}"
                    if (
                        response.status != 206
                        or response.headers.get("Content-Range") != expected
                    ):
                        raise ValueError(
                            "server did not honor the requested byte range"
                        )
                    with part.open("wb") as out:
                        while data := response.read(1024 * 1024):
                            out.write(data)
                if part.stat().st_size != end - start + 1:
                    raise ValueError("short model download")
                return part
            except (OSError, ValueError):
                if attempt == 2:
                    raise
                time.sleep(2)
        raise AssertionError("unreachable")

    with ThreadPoolExecutor(max_workers=8) as pool, partial.open("ab") as out:
        for part in pool.map(get, blocks):
            with part.open("rb") as stream:
                while data := stream.read(1024 * 1024):
                    out.write(data)
            out.flush()
            part.unlink()  # Only the redundant temporary copy of these bytes.
            done = out.tell()
            print(
                f"{spec['name']}: {done / 1e9:.2f}/{size / 1e9:.2f} GB ({time.monotonic() - started:.1f}s)",
                flush=True,
            )
    with partial.open("rb") as stream:
        actual = hashlib.file_digest(stream, "sha256").hexdigest()
    if partial.stat().st_size != size or actual != digest:
        raise ValueError(f"{spec['name']}: downloaded model failed SHA-256 validation")
    partial.replace(target)
    manifest.write_text(
        json.dumps(
            {"repo": repo, "file": info["path"], "sha256": actual, "size": size},
            indent=2,
        )
    )
    for redundant in parts.iterdir():
        if redundant.is_file() and redundant.name.isdigit():
            redundant.unlink()  # Full model already passed SHA-256 validation.
    parts.rmdir()
    print(f"{spec['name']}: VERIFIED {actual}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", nargs="+", required=True)
    parser.add_argument("--workers", type=int, choices=[1, 2, 3], default=2)
    args = parser.parse_args()
    config = tomllib.loads((ROOT / "models.toml").read_text())
    specs = {s["name"]: s for s in config["models"] + config["rerankers"]}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        list(pool.map(fetch, [specs[name] for name in dict.fromkeys(args.models)]))


if __name__ == "__main__":
    main()

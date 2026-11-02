"""Evaluate Jina's official listwise wrapper using its required llama.cpp fork.

Requires numpy, torch, tokenizers, safetensors and prepared assets described in
eval/README.md. No remote model Python code is loaded by Transformers.
"""

import argparse
import importlib.util
import json
import math
from pathlib import Path
from typing import Any

from eval.compare_models import CACHE
from eval.compare_rerankers import rerank

ASSETS = Path.home() / ".cache/engram/jina-v35"


class JinaServer:
    peak_rss_kib = None
    memory_sampling_error = (
        "Peak RSS unavailable; official CLI wrapper reloads weights for each block."
    )

    def __init__(
        self, spec: dict[str, Any], directory: Path, reranking: bool = True
    ) -> None:
        self.directory = directory
        self.spec = spec

    def __enter__(self) -> "JinaServer":
        spec = importlib.util.spec_from_file_location(
            "jina_official_rerank", ASSETS / "rerank.py"
        )
        if spec is None or spec.loader is None:
            raise RuntimeError("prepare Jina v3.5 assets first; see eval/README.md")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.model = module.GGUFReranker(
            model_path=str(ASSETS / "jina-reranker-v3.5-Q8_0.gguf"),
            projector_path=str(ASSETS / "projector.safetensors"),
            tokenizer_path=str(ASSETS / "tokenizer.json"),
            llama_embedding_path=str(ASSETS / "llama.cpp/build/bin/llama-embedding"),
            max_length=self.spec.get("max_length", 32768),
            tokens_per_batch=self.spec.get("max_length", 32768),
            max_ctx_size=self.spec.get("max_ctx_size", 65536),
        )
        return self

    def __exit__(self, *args: object) -> None:
        del self.model

    def rerank(self, query: str, documents: list[str]) -> list[float]:
        rows = self.model.rerank(query, documents)
        if sorted(row["index"] for row in rows) != list(range(len(documents))):
            raise ValueError("Jina output has missing or duplicate indices")
        scores = [0.0] * len(documents)
        for row in rows:
            value = row["relevance_score"]
            if not math.isfinite(value):
                raise ValueError("Jina returned a non-finite score")
            scores[row["index"]] = value
        return scores

    def allocation_lines(self) -> list[str]:
        return [
            "Unavailable: the official Jina wrapper captures CLI stderr internally."
        ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", nargs="+", required=True)
    parser.add_argument("--full", action="store_true")
    parser.add_argument(
        "--block-tokens", type=int, choices=[32768, 65536], default=32768
    )
    args = parser.parse_args()
    directory = Path(
        (CACHE / ("full.txt" if args.full else "screen.txt")).read_text().strip()
    )
    snapshot = json.loads((directory / "snapshot.json").read_text())
    spec = {
        "name": "jina-reranker-v35-q8" + ("-64k" if args.block_tokens == 65536 else ""),
        "id": "jinaai/jina-reranker-v3.5-GGUF:Q8_0",
        "backend": "littlewine/llama.cpp",
        "max_length": args.block_tokens,
        "max_ctx_size": 65536,
    }
    for name in args.models:
        paths = sorted(
            directory.glob(f"{name}-*/result.json"), key=lambda p: p.stat().st_mtime
        )
        if not paths:
            raise ValueError(f"no embedding results for {name}")
        rerank(spec, paths[-1], directory, snapshot, server_type=JinaServer)


if __name__ == "__main__":
    main()

"""
Minimal OpenAI-compatible embedding proxy backed by Qwen3-Embedding-4B (local).

Run:
    conda run -n quantaalpha python scripts/embed_proxy.py   # default port 8009

Then in .env:
    EMBEDDING_MODEL=litellm_proxy/Qwen3-Embedding-4B
    LITELLM_PROXY_API_KEY=local
    LITELLM_PROXY_API_BASE=http://localhost:8009/v1
"""
from __future__ import annotations

import time
import uuid
from typing import Union

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

_model = None


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer("Qwen/Qwen3-Embedding-4B", trust_remote_code=True)
    return _model


app = FastAPI(title="Embedding Proxy", version="1.0.0")


class EmbeddingRequest(BaseModel):
    model: str = "Qwen3-Embedding-4B"
    input: Union[str, list[str]]
    encoding_format: str = "float"


@app.post("/v1/embeddings")
async def create_embeddings(req: EmbeddingRequest):
    texts = [req.input] if isinstance(req.input, str) else req.input
    try:
        vectors = _get_model().encode(texts, convert_to_numpy=True).tolist()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return JSONResponse({
        "object": "list",
        "data": [{"object": "embedding", "embedding": vec, "index": i} for i, vec in enumerate(vectors)],
        "model": req.model,
        "usage": {"prompt_tokens": 0, "total_tokens": 0},
    })


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/v1/models")
async def list_models():
    return {
        "object": "list",
        "data": [{"id": "Qwen3-Embedding-4B", "object": "model", "created": int(time.time()), "owned_by": "local"}],
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8009)
    args = parser.parse_args()
    print(f"Embedding proxy on http://{args.host}:{args.port}/v1")
    uvicorn.run(app, host=args.host, port=args.port)

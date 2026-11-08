"""Sentence embedding generation.

Each text is converted into a 384-dimensional vector that represents its
meaning. Vectors are L2-normalised, so the cosine similarity of two vectors
equals their dot product.

An in-process cache keyed by the exact text avoids repeating model inference
for texts that were already encoded (for example the same question asked
twice, or knowledge base entries re-imported without changes).
"""

import hashlib
import threading
from collections import OrderedDict

import numpy as np
from django.conf import settings

from .model_loader import get_model

EMBEDDING_DIMENSION = 384
_CACHE_SIZE = 5000
_cache: "OrderedDict[str, np.ndarray]" = OrderedDict()
_cache_lock = threading.Lock()


def text_fingerprint(text: str) -> str:
    """Stable hash of the text and model name, used to detect stale stored embeddings."""
    return hashlib.sha256(f"{settings.NLP_MODEL_NAME}::{text}".encode("utf-8")).hexdigest()


def encode(texts: list[str]) -> np.ndarray:
    """Encode a list of texts into an (n, 384) float32 matrix of normalised embeddings."""
    if not texts:
        return np.zeros((0, EMBEDDING_DIMENSION), dtype=np.float32)

    results: list[np.ndarray | None] = [None] * len(texts)
    missing: dict[str, list[int]] = {}
    with _cache_lock:
        for index, text in enumerate(texts):
            cached = _cache.get(text)
            if cached is not None:
                _cache.move_to_end(text)
                results[index] = cached
            else:
                missing.setdefault(text, []).append(index)

    if missing:
        unique_texts = list(missing)
        vectors = get_model().encode(
            unique_texts,
            batch_size=settings.NLP_BATCH_SIZE,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        ).astype(np.float32)
        with _cache_lock:
            for text, vector in zip(unique_texts, vectors):
                for index in missing[text]:
                    results[index] = vector
                _cache[text] = vector
                _cache.move_to_end(text)
            while len(_cache) > _CACHE_SIZE:
                _cache.popitem(last=False)

    return np.vstack(results)


def encode_one(text: str) -> np.ndarray:
    return encode([text])[0]


def to_storage(vector: np.ndarray) -> list[float]:
    """Convert a vector to a JSON-serialisable list for PostgreSQL JSONField storage."""
    return [round(float(value), 7) for value in vector]


def from_storage(values) -> np.ndarray:
    return np.asarray(values, dtype=np.float32)


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()

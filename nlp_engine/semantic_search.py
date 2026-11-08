"""Semantic search over pre-computed sentence embeddings.

A ``SemanticIndex`` holds one row per searchable text (for example an FAQ's
main question and each of its alternative formulations). Several rows can
belong to the same knowledge record (``key``); search results are grouped so
that each record appears once, scored by its best-matching formulation.

For the prototype's small knowledge base an exhaustive cosine similarity
comparison is fast (well under a millisecond for a few hundred rows), so no
vector database is required.
"""

from dataclasses import dataclass

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity


@dataclass(frozen=True)
class IndexEntry:
    key: int
    text: str
    source: str  # e.g. "question" or "alternative"


@dataclass(frozen=True)
class SearchHit:
    key: int
    score: float
    matched_text: str
    matched_source: str


class SemanticIndex:
    def __init__(self, entries: list[IndexEntry], matrix: np.ndarray):
        if len(entries) != matrix.shape[0]:
            raise ValueError("Number of entries must match the number of embedding rows.")
        self.entries = entries
        self.matrix = matrix.astype(np.float32) if len(entries) else matrix

    def __len__(self):
        return len(self.entries)

    def similarities(self, query_embedding: np.ndarray) -> np.ndarray:
        if not self.entries:
            return np.zeros(0, dtype=np.float32)
        return cosine_similarity(query_embedding.reshape(1, -1), self.matrix)[0]

    def search(self, query_embedding: np.ndarray, top_k: int = 5) -> list[SearchHit]:
        """Return up to ``top_k`` records ranked by their best cosine similarity."""
        scores = self.similarities(query_embedding)
        best: dict[int, SearchHit] = {}
        for row in np.argsort(-scores):
            entry = self.entries[row]
            if entry.key in best:
                continue
            best[entry.key] = SearchHit(entry.key, float(scores[row]), entry.text, entry.source)
            if len(best) >= top_k:
                break
        return list(best.values())


@dataclass(frozen=True)
class RetrievalDecision:
    """Outcome of applying the confidence threshold and ambiguity check to ranked hits."""

    outcome: str  # "answer", "clarification" or "no_match"
    best: SearchHit | None
    candidates: list[SearchHit]


def decide(hits: list[SearchHit], threshold: float, clarification_margin: float, high_confidence: float,
           preferred_keys: set[int] | None = None) -> RetrievalDecision:
    """Apply the similarity threshold and clarification rules.

    * best score below ``threshold`` -> no_match (fallback response)
    * best score at or above ``high_confidence`` -> answer
    * otherwise, if other records score within ``clarification_margin`` of the
      best one, the match is ambiguous. If exactly one of those close candidates
      belongs to the detected intent (``preferred_keys``) it is chosen;
      otherwise the user is asked to clarify.
    """
    if not hits or hits[0].score < threshold:
        return RetrievalDecision("no_match", hits[0] if hits else None, hits[:3])

    best = hits[0]
    if best.score >= high_confidence:
        return RetrievalDecision("answer", best, [best])

    close = [hit for hit in hits if hit.score >= threshold and best.score - hit.score <= clarification_margin]
    if len(close) <= 1:
        return RetrievalDecision("answer", best, [best])

    if preferred_keys:
        preferred = [hit for hit in close if hit.key in preferred_keys]
        if len(preferred) == 1:
            return RetrievalDecision("answer", preferred[0], [preferred[0]])

    return RetrievalDecision("clarification", best, close[:3])

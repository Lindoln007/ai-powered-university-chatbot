"""Cosine similarity with NumPy.

Equivalent to ``sklearn.metrics.pairwise.cosine_similarity`` for dense
vectors, without importing scikit-learn (which pulls in SciPy and pandas and
adds seconds, or on a cold Windows file cache tens of seconds, to start-up).
"""

import numpy as np


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Return the (len(a), len(b)) matrix of cosine similarities between the rows of a and b."""
    a = np.atleast_2d(np.asarray(a, dtype=np.float32))
    b = np.atleast_2d(np.asarray(b, dtype=np.float32))
    a_norm = a / np.clip(np.linalg.norm(a, axis=1, keepdims=True), 1e-12, None)
    b_norm = b / np.clip(np.linalg.norm(b, axis=1, keepdims=True), 1e-12, None)
    return a_norm @ b_norm.T

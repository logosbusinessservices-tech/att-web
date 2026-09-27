"""1:1 face verification for field attendance.

We already know who the employee claims to be (they are logged in), so this is a
1:1 check against THEIR OWN enrolled embedding — stronger and faster than a 1:N
gallery search. Cosine similarity = dot product of two L2-normalized vectors.
"""

import numpy as np

from app.config import settings


def blob_to_embedding(blob: bytes) -> np.ndarray:
    """Deserialize a stored float32 BLOB into a 1-D numpy array (same as pipeline)."""
    return np.frombuffer(blob, dtype=np.float32)


def embedding_to_blob(embedding: np.ndarray) -> bytes:
    """Serialize a 512-d embedding to raw float32 bytes for storage."""
    return np.asarray(embedding, dtype=np.float32).reshape(-1).tobytes()


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity. Inputs are expected L2-normalized (ArcFace normed_embedding),
    but we normalize defensively so the score is always in [-1, 1]."""
    a = np.asarray(a, dtype=np.float32).reshape(-1)
    b = np.asarray(b, dtype=np.float32).reshape(-1)
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def verify(live_embedding: np.ndarray, enrolled_blob: bytes) -> tuple[bool, float]:
    """Return (passed, similarity) for a 1:1 field verification.

    passed = similarity >= FIELD_MATCH_THRESHOLD (stricter than the camera's 0.4).
    """
    enrolled = blob_to_embedding(enrolled_blob)
    sim = cosine_similarity(live_embedding, enrolled)
    return sim >= settings.field_match_threshold, sim

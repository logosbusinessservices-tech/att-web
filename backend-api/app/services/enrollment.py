"""Enrollment: turn a handful of supervisor-taken photos into ONE embedding.

Mirrors how the pipeline enrolls from multiple photos: embed the largest face in
each usable photo, average the (L2-normalized) vectors, then re-normalize. The
average is more robust to lighting/angle than any single shot. Low-quality photos
(blurry/off-angle) are skipped so they don't poison the template.

The stored embedding is byte-for-byte comparable with the camera pipeline's, so
the same person recognized at a gate and enrolled here will match.
"""

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import FaceEmbedding, Person
from app.face.model import decode_image_bytes, embed_largest_face
from app.face.verify import embedding_to_blob


class EnrollmentError(Exception):
    """Raised when no usable face could be enrolled from the given photos."""


def build_embedding(images: list[bytes]) -> tuple[np.ndarray, int, list[str]]:
    """Embed each photo, keep the good ones, return (mean_embedding, used, notes).

    Raises EnrollmentError if nothing usable remains.
    """
    if not images:
        raise EnrollmentError("No photos were provided.")

    vectors: list[np.ndarray] = []
    notes: list[str] = []
    for i, data in enumerate(images, start=1):
        img = decode_image_bytes(data)
        if img is None:
            notes.append(f"Photo {i}: not a readable image.")
            continue
        emb, quality = embed_largest_face(img)
        if emb is None:
            notes.append(f"Photo {i}: no face detected.")
            continue
        if quality < settings.enroll_min_quality:
            notes.append(f"Photo {i}: too blurry/off-angle (quality {quality:.2f}).")
            continue
        vectors.append(emb)

    if not vectors:
        raise EnrollmentError(
            "No usable face found. " + (" ".join(notes) or "Try clearer, front-facing photos.")
        )

    mean = np.mean(np.stack(vectors, axis=0), axis=0).astype(np.float32)
    norm = np.linalg.norm(mean)
    if norm == 0:
        raise EnrollmentError("Could not build a valid template from these photos.")
    mean = mean / norm
    return mean, len(vectors), notes


def enroll_person(db: Session, person: Person, images: list[bytes]) -> dict:
    """Build and store (or replace) the person's face template. Commits nothing —
    the caller commits. Returns a small summary."""
    if len(images) > settings.enroll_max_photos:
        raise EnrollmentError(f"At most {settings.enroll_max_photos} photos allowed.")

    embedding, used, notes = build_embedding(images)
    blob = embedding_to_blob(embedding)

    existing = db.execute(
        select(FaceEmbedding).where(FaceEmbedding.person_id == person.id)
    ).scalar_one_or_none()
    if existing is None:
        db.add(FaceEmbedding(person_id=person.id, embedding=blob, num_photos=used))
    else:
        existing.embedding = blob
        existing.num_photos = used
    db.flush()
    return {"photos_used": used, "photos_submitted": len(images), "notes": notes}

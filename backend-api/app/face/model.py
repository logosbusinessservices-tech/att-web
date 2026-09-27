"""Face model wrapper — MUST produce embeddings identical to the pipeline.

This mirrors the pipeline's face_model.py so an employee's camera-enrolled
embedding and their live field-scan embedding are directly comparable:
  - insightface FaceAnalysis(name=buffalo_s), CPU, det_size=(320,320), det_thresh=0.5
  - takes a BGR image, uses face.normed_embedding (already L2-normalized), float32, 512-d
  - picks the largest face for single-image (enrollment / field selfie) use

If you later switch the pipeline to buffalo_l, set FACE_MODEL_NAME=buffalo_l here
AND re-enroll everyone; the code does not change.

The model is loaded once (lazily) and kept warm in memory — the reason the backend
runs on a persistent container (Render), not serverless.
"""

import warnings

import cv2
import numpy as np

warnings.filterwarnings("ignore", category=FutureWarning, module="skimage")
warnings.filterwarnings("ignore", category=FutureWarning, module="insightface")

from insightface.app import FaceAnalysis

from app.config import settings

EMBEDDING_DIM = 512

_app: FaceAnalysis | None = None


def get_face_app() -> FaceAnalysis:
    """Lazily load and cache the insightface model stack (SCRFD + ArcFace)."""
    global _app
    if _app is None:
        app = FaceAnalysis(
            name=settings.face_model_name,
            providers=["CPUExecutionProvider"],
        )
        app.prepare(
            ctx_id=-1,
            det_size=(settings.face_det_size, settings.face_det_size),
            det_thresh=settings.face_det_threshold,
        )
        _app = app
    return _app


def _quality(det_score: float, kps, crop_bgr) -> float:
    """Composite quality in [0,1], same weighting spirit as the pipeline.

    Used to reject blurry/off-angle field selfies before they are matched.
    """
    frontality = 1.0
    if kps is not None and len(kps) >= 3:
        le, re, nose = kps[0], kps[1], kps[2]
        face_width = max(float(re[0] - le[0]), 1.0)
        eye_mid_x = (float(le[0]) + float(re[0])) / 2.0
        lateral = abs(float(nose[0]) - eye_mid_x) / face_width
        tilt = abs(float(le[1]) - float(re[1])) / face_width
        frontality = max(0.0, 1.0 - lateral * 1.5 - tilt * 1.5)

    sharpness = 1.0
    if crop_bgr is not None and crop_bgr.size > 0:
        gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
        sharpness = min(cv2.Laplacian(gray, cv2.CV_64F).var() / 150.0, 1.0)

    factor = 0.4 + 0.35 * frontality + 0.25 * sharpness
    return float(det_score) * factor


def embed_largest_face(image_bgr: np.ndarray) -> tuple[np.ndarray | None, float]:
    """Embed the single largest face in a BGR image.

    Returns (embedding_512_float32_L2normalized, quality) or (None, 0.0) if no
    face is found. Use for both enrollment and field-scan verification.
    """
    app = get_face_app()
    faces = app.get(image_bgr)
    if not faces:
        return None, 0.0
    largest = max(
        faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1])
    )
    x1, y1, x2, y2 = (int(v) for v in largest.bbox)
    x1, y1 = max(0, x1), max(0, y1)
    x2 = min(image_bgr.shape[1], x2)
    y2 = min(image_bgr.shape[0], y2)
    crop = image_bgr[y1:y2, x1:x2]
    quality = _quality(float(largest.det_score), getattr(largest, "kps", None), crop)
    emb = np.asarray(largest.normed_embedding, dtype=np.float32)
    return emb, quality


def decode_image_bytes(data: bytes) -> np.ndarray | None:
    """Decode uploaded image bytes (JPEG/PNG) to a BGR numpy array."""
    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)  # returns BGR, like the pipeline
    return img

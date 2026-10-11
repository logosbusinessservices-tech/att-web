"""Central settings, loaded from environment / .env.

Every tunable lives here so the rest of the code has no magic numbers, mirroring
the pipeline's config.py philosophy. Values are read once at import time.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

# Public placeholder secrets; the app refuses to start on Postgres while either is in use.
DEFAULT_JWT_SECRET = "change-me-to-a-long-random-string"
DEFAULT_EDGE_API_KEY = "change-me-edge-key"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # App
    app_name: str = "att-web API"
    environment: str = "dev"

    # Database — one switch drives SQLite (dev) vs Postgres (prod).
    database_url: str = "sqlite:///./attendance.db"

    # Auth
    jwt_secret: str = DEFAULT_JWT_SECRET
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440

    # Face model (must match the pipeline for embeddings to be comparable).
    face_model_name: str = "buffalo_s"
    face_det_size: int = 320
    face_det_threshold: float = 0.5
    # Stricter than the camera pipeline's 0.4: a field selfie is static/self-service.
    field_match_threshold: float = 0.45

    # Geofence
    gps_max_accuracy_m: float = 100.0

    # ── Enrollment (supervisor onboarding: photos -> embedding) ──────────────
    # Reject a photo whose detected face quality is below this (blurry/off-angle).
    enroll_min_quality: float = 0.35
    enroll_min_photos: int = 1
    enroll_max_photos: int = 10
    # Days after activation before employee/supervisor are nagged that the
    # employee's attendance photos still haven't been enrolled.
    enroll_reminder_days: int = 3
    # Local folder for profile avatars; used only when Azure storage isn't configured.
    avatar_dir: str = "./data/avatars"
    # Max avatar upload size (bytes).
    avatar_max_bytes: int = 5 * 1024 * 1024

    # ── Field attendance (face + GPS) ────────────────────────────────────────
    # Default geofence radius for a station (metres). Per-station radius_m on the
    # Station row overrides this; tweakable manually per station.
    field_default_radius_m: float = 1000.0
    # Reject a field selfie below this face quality (a touch looser than enroll).
    field_min_quality: float = 0.30
    # Min seconds between two same-direction field scans (anti double-punch).
    field_duplicate_window_s: int = 120
    # Keep the audit selfie this many days, then purge (metadata is kept).
    field_selfie_retention_days: int = 30
    # Debug only: include the match similarity in the check-in response.
    field_debug_return_similarity: bool = False
    # Local folder for audit selfies; used only when Azure storage isn't configured.
    field_selfie_dir: str = "./data/field_selfies"

    # ── Photo storage ─────────────────────────────────────────────────────────────────────────
    # When set, photos go to Azure Blob Storage (survives restarts/redeploys);
    # when empty, they go to the local folders (dev + tests).
    azure_storage_connection_string: str = ""
    storage_container_avatars: str = "avatars"
    storage_container_field_selfies: str = "field-selfies"
    storage_container_employee_photos: str = "employee-photos"
    # Local folder for onboarding photos; used only when Azure storage isn't configured.
    employee_photo_dir: str = "./data/employee_photos"

    # ── OTP login ────────────────────────────────────────────────────────────────────────────
    # Off until SMS delivery is set up: every OTP endpoint answers 404 and
    # password changes need the current password.
    otp_enabled: bool = False
    otp_length: int = 6
    otp_ttl_minutes: int = 5
    otp_max_attempts: int = 5
    # Min seconds between two OTP requests for the same phone (anti-spam).
    otp_resend_cooldown_s: int = 30
    # SMS provider: "console" (dev — logs the code) or "twilio" (prod).
    sms_provider: str = "console"
    # Email OTP channel (2FA for password change): "console" (dev) or "smtp".
    email_provider: str = "console"
    email_from: str = "no-reply@att-web.local"
    # Debug only: include the OTP code in the API response (never in production).
    otp_debug_return_code: bool = False
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""
    # Days after onboarding before the supervisor is notified about an unchanged
    # default password.
    password_reminder_days: int = 3

    # Edge ingestion shared secret
    edge_api_key: str = DEFAULT_EDGE_API_KEY

    # ── Gate-monitor announcements (EA-managed message board) ────────────────
    display_message_max_chars: int = 150
    display_message_max_count: int = 8

    # Display timezone (storage is always UTC). Attendance days + late checks
    # are computed in THIS timezone.
    display_timezone: str = "Asia/Kolkata"

    # ── Attendance policy (all editable here / in .env) ──────────────────────
    # Comma-separated weekday keys that are working days (others => weekend).
    working_days: str = "mon,tue,wed,thu,fri,sat"
    # Map each camera_label to a direction, so hours + entry/exit counts are
    # exact. Format: "label:entry|exit" pairs, comma-separated. The edge also
    # sends `direction` per event; this map is the fallback when it doesn't.
    camera_directions: str = (
        "gate-in-1:entry,gate-in-2:entry,gate-out-1:exit,gate-out-2:exit"
    )

    # CORS
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def working_day_set(self) -> set[str]:
        return {d.strip().lower() for d in self.working_days.split(",") if d.strip()}

    @property
    def camera_direction_map(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for pair in self.camera_directions.split(","):
            pair = pair.strip()
            if not pair or ":" not in pair:
                continue
            label, direction = pair.rsplit(":", 1)
            out[label.strip()] = direction.strip().lower()
        return out


@lru_cache
def get_settings() -> Settings:
    return Settings()


def assert_production_secrets(s: Settings) -> None:
    """Refuse to run on Postgres (production) while a public placeholder secret is set."""
    if s.is_sqlite:
        return
    weak = [
        name
        for name, value, default in (
            ("JWT_SECRET", s.jwt_secret, DEFAULT_JWT_SECRET),
            ("EDGE_API_KEY", s.edge_api_key, DEFAULT_EDGE_API_KEY),
        )
        if not value or value == default
    ]
    if weak:
        raise RuntimeError(
            "Refusing to start: set a long random value for " + ", ".join(weak)
        )


settings = get_settings()

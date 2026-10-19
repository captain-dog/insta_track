"""Application settings loaded from environment variables and the .env file.

All secrets live exclusively in .env; nothing sensitive is written anywhere else.
"""

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


def load_env_file(path: Path = ENV_FILE) -> None:
    """Populate os.environ from a KEY=VALUE file without overriding existing variables."""
    if not path.exists():
        return
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ConfigError(f"{name} is not set in .env")
    return value


@dataclass(frozen=True)
class Settings:
    instagram_username: str
    instagram_session_id: str | None
    instagram_csrf_token: str | None
    instagram_password: str | None
    track_usernames: tuple[str, ...]
    telegram_bot_token: str
    telegram_chat_id: str
    database_url: str
    log_file: Path

    @classmethod
    def from_env(cls) -> "Settings":
        load_env_file()
        instagram_username = _require("IG_USERNAME")
        session_id = os.environ.get("IG_SESSION_ID", "").strip() or None
        password = os.environ.get("IG_PASSWORD", "").strip() or None
        if not session_id and not password:
            raise ConfigError("Either IG_SESSION_ID or IG_PASSWORD must be set in .env")

        raw_targets = os.environ.get("TRACK_USERNAMES", "") or instagram_username
        track_usernames = tuple(
            name.strip().lstrip("@") for name in raw_targets.split(",") if name.strip()
        )

        return cls(
            instagram_username=instagram_username,
            instagram_session_id=session_id,
            instagram_csrf_token=os.environ.get("IG_CSRF_TOKEN", "").strip() or None,
            instagram_password=password,
            track_usernames=track_usernames,
            telegram_bot_token=_require("TG_BOT_TOKEN"),
            telegram_chat_id=_require("TG_CHAT_ID"),
            database_url=os.environ.get(
                "DATABASE_URL", f"sqlite:///{PROJECT_ROOT / 'snapshots.db'}"
            ),
            log_file=PROJECT_ROOT / "track.log",
        )

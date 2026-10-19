import logging
import sys

from insta_track.bot import TrackerBot
from insta_track.config import ConfigError, Settings
from insta_track.database import create_session_factory, run_migrations
from insta_track.instagram import InstagramClient
from insta_track.logging_config import setup_logging
from insta_track.repository import SnapshotRepository
from insta_track.telegram import TelegramClient

logger = logging.getLogger(__name__)


def main() -> None:
    try:
        settings = Settings.from_env()
    except ConfigError as error:
        sys.exit(f"config error: {error}")

    setup_logging(settings.log_file)
    run_migrations(settings.database_url)

    instagram = InstagramClient.login(
        settings.instagram_username,
        session_id=settings.instagram_session_id,
        csrf_token=settings.instagram_csrf_token,
        password=settings.instagram_password,
    )
    bot = TrackerBot(
        instagram=instagram,
        telegram=TelegramClient(settings.telegram_bot_token, settings.telegram_chat_id),
        repository=SnapshotRepository(create_session_factory(settings.database_url)),
        targets=settings.track_usernames,
    )
    try:
        bot.run_forever()
    except KeyboardInterrupt:
        logger.info("stopped by user")

import logging
import time
from datetime import datetime, timezone

from insta_track.diff import compute_diff, format_diff
from insta_track.instagram import InstagramClient
from insta_track.models import RelationKind
from insta_track.repository import SnapshotRepository
from insta_track.telegram import TelegramClient

logger = logging.getLogger(__name__)

LONG_POLL_TIMEOUT_SECONDS = 30
DELAY_BETWEEN_FETCHES_SECONDS = 5
TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"

BUTTON_CHECK_FOLLOWERS = "Check followers"
BUTTON_CHECK_FOLLOWING = "Check following"
KEYBOARD = {
    "keyboard": [[{"text": BUTTON_CHECK_FOLLOWERS}, {"text": BUTTON_CHECK_FOLLOWING}]],
    "resize_keyboard": True,
}
COMMANDS: dict[str, tuple[RelationKind, ...]] = {
    BUTTON_CHECK_FOLLOWERS: (RelationKind.FOLLOWERS,),
    "/followers": (RelationKind.FOLLOWERS,),
    BUTTON_CHECK_FOLLOWING: (RelationKind.FOLLOWING,),
    "/following": (RelationKind.FOLLOWING,),
    "/check": (RelationKind.FOLLOWERS, RelationKind.FOLLOWING),
}


class TrackerBot:
    """Long-polls Telegram and runs a snapshot diff for each button press."""

    def __init__(
        self,
        instagram: InstagramClient,
        telegram: TelegramClient,
        repository: SnapshotRepository,
        targets: tuple[str, ...],
    ):
        self._instagram = instagram
        self._telegram = telegram
        self._repository = repository
        self._targets = targets
        self._update_offset: int | None = None

    def run_forever(self) -> None:
        logger.info("bot started, targets: %s", ", ".join(self._targets))
        self._notify("Bot started. Use the buttons to check followers / following")
        while True:
            requested_kinds = self._poll_commands()
            if requested_kinds:
                self._check_targets(requested_kinds)

    def _poll_commands(self) -> tuple[RelationKind, ...]:
        """Return the relation kinds requested since the previous poll."""
        try:
            updates = self._telegram.get_updates(
                self._update_offset, timeout=LONG_POLL_TIMEOUT_SECONDS
            )
        except Exception as error:
            logger.error("telegram getUpdates failed: %s", error)
            time.sleep(LONG_POLL_TIMEOUT_SECONDS)
            return ()

        requested: set[RelationKind] = set()
        for update in updates:
            self._update_offset = update["update_id"] + 1
            message = update.get("message") or {}
            if str(message.get("chat", {}).get("id")) != self._telegram.chat_id:
                continue
            text = message.get("text", "")
            if text in COMMANDS:
                logger.info("command received: %s", text)
                requested.update(COMMANDS[text])
            elif text == "/start":
                self._notify("Use the buttons to diff followers / following against the last snapshot")
        return tuple(kind for kind in RelationKind if kind in requested)

    def _check_targets(self, kinds: tuple[RelationKind, ...]) -> None:
        for target in self._targets:
            try:
                self._check_target(target, kinds)
            except Exception as error:
                logger.exception("check failed for @%s", target)
                self._notify(f"Tracker error (@{target}): {error}")

    def _check_target(self, target: str, kinds: tuple[RelationKind, ...]) -> None:
        taken_at = datetime.now(timezone.utc).replace(tzinfo=None)
        current = {}
        for kind in kinds:
            current[kind] = self._instagram.fetch_accounts(target, kind)
            time.sleep(DELAY_BETWEEN_FETCHES_SECONDS)

        previous = {kind: self._repository.get_latest(target, kind) for kind in kinds}
        self._repository.save(target, taken_at, current)

        sections = []
        for kind in kinds:
            snapshot = previous[kind]
            diff = compute_diff(kind, snapshot.accounts if snapshot else None, current[kind])
            previous_at = f"{snapshot.taken_at:{TIMESTAMP_FORMAT}} UTC" if snapshot else "none"
            sections.append(f"{format_diff(diff)}\nprev: {previous_at}")

        header = f"@{target}\nnow: {taken_at:{TIMESTAMP_FORMAT}} UTC"
        self._notify(header + "\n\n" + "\n\n".join(sections))

    def _notify(self, text: str) -> None:
        logger.info("notify: %s", text.replace("\n", " | "))
        try:
            self._telegram.send_message(text, reply_markup=KEYBOARD)
        except Exception as error:
            logger.error("telegram sendMessage failed: %s", error)

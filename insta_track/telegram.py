import json
import logging
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

API_URL = "https://api.telegram.org/bot{token}/{method}"
REQUEST_TIMEOUT_SECONDS = 60
# Telegram rejects messages longer than 4096 characters; keep a safety margin.
MAX_MESSAGE_LENGTH = 4000


def split_message(text: str, limit: int = MAX_MESSAGE_LENGTH) -> list[str]:
    """Split text on line boundaries into chunks no longer than `limit`."""
    chunks: list[str] = []
    current = ""
    for line in text.split("\n"):
        if current and len(current) + len(line) + 1 > limit:
            chunks.append(current)
            current = ""
        current += ("\n" if current else "") + line
    return chunks + [current]


class TelegramClient:
    def __init__(self, token: str, chat_id: str):
        self._token = token
        self.chat_id = str(chat_id)

    def _call(self, method: str, **params) -> object:
        url = API_URL.format(token=self._token, method=method)
        data = urllib.parse.urlencode(params).encode()
        with urllib.request.urlopen(url, data, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return json.load(response)["result"]

    def send_message(self, text: str, reply_markup: dict | None = None) -> None:
        params = {"chat_id": self.chat_id}
        if reply_markup:
            params["reply_markup"] = json.dumps(reply_markup)
        for chunk in split_message(text):
            self._call("sendMessage", text=chunk, **params)

    def get_updates(self, offset: int | None, timeout: int) -> list[dict]:
        return self._call("getUpdates", offset=offset, timeout=timeout)

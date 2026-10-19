import logging
import secrets
import time
from urllib.parse import unquote

import instaloader

from insta_track.models import RelationKind
from insta_track.repository import Accounts

logger = logging.getLogger(__name__)

PAGE_SIZE = 100
PAGE_DELAY_SECONDS = 2
ENDPOINTS = {
    RelationKind.FOLLOWERS: "followers",
    RelationKind.FOLLOWING: "following",
}


class InstagramError(RuntimeError):
    pass


class InstagramClient:
    def __init__(self, loader: instaloader.Instaloader):
        self._loader = loader

    @classmethod
    def login(
        cls,
        username: str,
        session_id: str | None = None,
        csrf_token: str | None = None,
        password: str | None = None,
    ) -> "InstagramClient":
        """Authenticate with a browser sessionid cookie (preferred) or a password.

        Nothing is persisted to disk: credentials come from .env only.
        """
        loader = instaloader.Instaloader(quiet=True)
        if session_id:
            user_id = unquote(session_id).split(":", 1)[0]
            # Read-only GET endpoints don't validate the CSRF token, so a random one is enough.
            cookies = {
                "sessionid": session_id,
                "ds_user_id": user_id,
                "csrftoken": csrf_token or secrets.token_urlsafe(24),
            }
            loader.load_session(username, cookies)
            logged_in_as = loader.test_login()
            if not logged_in_as:
                raise InstagramError("IG_SESSION_ID is invalid or expired")
            logger.info("authenticated via session cookie as %s", logged_in_as)
        else:
            loader.login(username, password)
            logger.info("authenticated via password as %s", username)
        return cls(loader)

    def fetch_accounts(self, target: str, kind: RelationKind) -> Accounts:
        """Return every account in the target's followers/following list."""
        logger.info("@%s: fetching %s", target, kind)
        profile = instaloader.Profile.from_username(self._loader.context, target)
        expected_count = profile.followers if kind is RelationKind.FOLLOWERS else profile.followees

        accounts: Accounts = {}
        next_max_id = None
        while True:
            params = {"count": PAGE_SIZE}
            if next_max_id:
                params["max_id"] = next_max_id
            response = self._loader.context.get_json(
                f"api/v1/friendships/{profile.userid}/{ENDPOINTS[kind]}/",
                params=params,
                host="www.instagram.com",
            )
            for user in response.get("users", []):
                accounts[int(user["pk"])] = user["username"]
            logger.info("@%s: %s %d/%d", target, kind, len(accounts), expected_count)

            next_max_id = response.get("next_max_id")
            if not next_max_id or not response.get("has_more", True):
                break
            time.sleep(PAGE_DELAY_SECONDS)

        if expected_count and not accounts:
            raise InstagramError(
                f"{kind}: API returned 0 entries but profile counter is {expected_count}"
            )
        return accounts

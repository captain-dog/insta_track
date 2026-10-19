import json
import logging
import logging.handlers
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
import urllib.parse
import urllib.request
from pathlib import Path

import instaloader

BASE = Path(__file__).parent
DB_PATH = BASE / "snapshots.db"
BTN_FOLLOWERS = "Check followers"
BTN_FOLLOWING = "Check following"
COMMANDS = {
    BTN_FOLLOWERS: ("followers",),
    "/followers": ("followers",),
    BTN_FOLLOWING: ("followees",),
    "/following": ("followees",),
    "/check": ("followers", "followees"),
}
POLL_SECONDS = 30

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.handlers.RotatingFileHandler(
            BASE / "track.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"),
    ],
)
log = logging.getLogger("track")


def load_env(path=BASE / ".env"):
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip("\"'"))


def get_loader(username):
    L = instaloader.Instaloader(quiet=True)
    session_file = BASE / f"session-{username}"
    if session_file.exists():
        L.load_session_from_file(username, str(session_file))
    else:
        password = os.environ.get("IG_PASSWORD")
        if not password:
            sys.exit("No session file and IG_PASSWORD is not set in .env")
        L.login(username, password)
        L.save_session_to_file(str(session_file))
    return L


def fetch(L, username, kind):
    log.info("@%s: fetching %s", username, kind)
    profile = instaloader.Profile.from_username(L.context, username)
    expected = profile.followers if kind == "followers" else profile.followees
    endpoint = "followers" if kind == "followers" else "following"
    result, max_id = {}, None
    while True:
        params = {"count": 100}
        if max_id:
            params["max_id"] = max_id
        r = L.context.get_json(
            f"api/v1/friendships/{profile.userid}/{endpoint}/",
            params=params, host="www.instagram.com")
        for u in r.get("users", []):
            result[int(u["pk"])] = u["username"]
        max_id = r.get("next_max_id")
        log.info("@%s: %s %d/%d", username, kind, len(result), expected)
        if not max_id or not r.get("has_more", True):
            break
        time.sleep(2)
    if expected and not result:
        raise RuntimeError(f"{kind}: API returned 0 entries but profile counter is {expected}")
    return result


def init_db(db):
    db.executescript("""
    CREATE TABLE IF NOT EXISTS snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        taken_at TEXT NOT NULL DEFAULT (datetime('now')),
        target TEXT NOT NULL,
        kind TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS snapshot_users (
        snapshot_id INTEGER NOT NULL REFERENCES snapshots(id),
        user_id INTEGER NOT NULL,
        username TEXT NOT NULL,
        PRIMARY KEY (snapshot_id, user_id)
    );
    """)


def last_snapshot(db, target, kind):
    """Return (taken_at, {user_id: username}) of the newest snapshot, or None."""
    row = db.execute(
        "SELECT id, taken_at FROM snapshots WHERE target=? AND kind=? ORDER BY id DESC LIMIT 1",
        (target, kind),
    ).fetchone()
    if not row:
        return None
    users = {uid: name for uid, name in db.execute(
        "SELECT user_id, username FROM snapshot_users WHERE snapshot_id=?", (row[0],))}
    return row[1], users


def save_snapshots(db, target, taken_at, snapshots):
    """Persist all kinds of one check atomically with a shared timestamp."""
    with db:
        for kind, users in snapshots.items():
            cur = db.execute(
                "INSERT INTO snapshots(taken_at, target, kind) VALUES (?, ?, ?)",
                (taken_at, target, kind))
            db.executemany(
                "INSERT INTO snapshot_users VALUES (?,?,?)",
                [(cur.lastrowid, uid, name) for uid, name in users.items()],
            )


def diff_text(kind, old, new):
    """Return (text, changed). old=None means first snapshot: everything is new."""
    if kind == "followers":
        label, plus, minus = "Followers", "New followers", "Lost followers"
    else:
        label, plus, minus = "Following", "Newly followed", "Unfollowed"
    first = old is None
    old = old or {}
    gained = sorted(n for u, n in new.items() if u not in old)
    lost = sorted(n for u, n in old.items() if u not in new)
    if not gained and not lost:
        return f"{label}: {len(new)} (no changes)", False
    head = f"{label}: {len(old)} → {len(new)}" + (" (initial snapshot)" if first else "")
    lines = [head]
    if gained:
        lines += [f"{plus}:"] + [f"  + {n}" for n in gained]
    if lost:
        lines += [f"{minus}:"] + [f"  - {n}" for n in lost]
    return "\n".join(lines), True


def tg(method, **params):
    token = os.environ["TG_BOT_TOKEN"]
    data = urllib.parse.urlencode(params).encode()
    with urllib.request.urlopen(
        f"https://api.telegram.org/bot{token}/{method}", data, timeout=60
    ) as r:
        return json.load(r)["result"]


def chunks(text, limit=4000):
    """Split on line boundaries to stay under Telegram's 4096-char message limit."""
    out, cur = [], ""
    for line in text.split("\n"):
        if cur and len(cur) + len(line) + 1 > limit:
            out.append(cur)
            cur = ""
        cur += ("\n" if cur else "") + line
    return out + [cur]


def notify(text):
    log.info("notify: %s", text.replace("\n", " | "))
    if not os.environ.get("TG_BOT_TOKEN") or not os.environ.get("TG_CHAT_ID"):
        return
    keyboard = {"keyboard": [[{"text": BTN_FOLLOWERS}, {"text": BTN_FOLLOWING}]],
                "resize_keyboard": True}
    for part in chunks(text):
        try:
            tg("sendMessage", chat_id=os.environ["TG_CHAT_ID"], text=part,
               reply_markup=json.dumps(keyboard))
        except Exception as e:
            log.error("telegram error: %s", e)


def run_target(L, db, username, kinds):
    taken_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    new = {}
    for kind in kinds:
        new[kind] = fetch(L, username, kind)
        time.sleep(5)
    prev = {kind: last_snapshot(db, username, kind) for kind in kinds}
    save_snapshots(db, username, taken_at, new)
    parts = []
    for kind in kinds:
        text, _ = diff_text(kind, prev[kind][1] if prev[kind] else None, new[kind])
        prev_at = f"{prev[kind][0]} UTC" if prev[kind] else "none"
        parts.append(f"{text}\nprev: {prev_at}")
    notify(f"@{username}\nnow: {taken_at} UTC\n\n" + "\n\n".join(parts))


def run_once(L, db, targets, kinds):
    for username in targets:
        try:
            run_target(L, db, username, kinds)
        except Exception as e:
            log.exception("check failed for @%s", username)
            notify(f"Tracker error (@{username}): {e}")


def poll_commands(offset):
    """Return (new_offset, kinds requested since the last poll, in canonical order)."""
    chat_id = str(os.environ["TG_CHAT_ID"])
    requested = set()
    try:
        updates = tg("getUpdates", offset=offset, timeout=POLL_SECONDS)
    except Exception as e:
        log.error("telegram error: %s", e)
        time.sleep(POLL_SECONDS)
        return offset, ()
    for u in updates:
        offset = u["update_id"] + 1
        msg = u.get("message") or {}
        if str(msg.get("chat", {}).get("id")) != chat_id:
            continue
        text = msg.get("text", "")
        if text in COMMANDS:
            log.info("command received: %s", text)
            requested.update(COMMANDS[text])
        elif text == "/start":
            notify("Use the buttons to diff followers / following against the last snapshot")
    return offset, tuple(k for k in ("followers", "followees") if k in requested)


def main():
    load_env()
    username = os.environ.get("IG_USERNAME")
    if not username:
        sys.exit("IG_USERNAME is not set")
    use_tg = bool(os.environ.get("TG_BOT_TOKEN") and os.environ.get("TG_CHAT_ID"))
    if not use_tg:
        sys.exit("TG_BOT_TOKEN and TG_CHAT_ID are required: checks are triggered via the bot buttons")
    targets = [
        t.strip().lstrip("@")
        for t in os.environ.get("TRACK_USERNAMES", username).split(",")
        if t.strip()
    ]
    log.info("logged in as %s, targets: %s", username, ", ".join(targets))
    L = get_loader(username)
    db = sqlite3.connect(DB_PATH)
    init_db(db)
    offset = None
    notify("Bot started. Use the buttons to check followers / following")
    while True:
        offset, kinds = poll_commands(offset)
        if kinds:
            run_once(L, db, targets, kinds)


if __name__ == "__main__":
    main()

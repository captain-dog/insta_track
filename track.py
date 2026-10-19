import json
import os
import sqlite3
import sys
import time
import traceback
import urllib.parse
import urllib.request
from pathlib import Path

import instaloader

BASE = Path(__file__).parent
DB_PATH = BASE / "snapshots.db"
CHECK_BUTTON = "Чек"
POLL_SECONDS = 30


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
            sys.exit("Нет сессии и IG_PASSWORD не задан в .env")
        L.login(username, password)
        L.save_session_to_file(str(session_file))
    return L


def fetch(L, username, kind):
    profile = instaloader.Profile.from_username(L.context, username)
    users = profile.get_followers() if kind == "followers" else profile.get_followees()
    return {u.userid: u.username for u in users}


def init_db(db):
    db.executescript("""
    CREATE TABLE IF NOT EXISTS snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        taken_at TEXT NOT NULL DEFAULT (datetime('now')),
        kind TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS snapshot_users (
        snapshot_id INTEGER NOT NULL REFERENCES snapshots(id),
        user_id INTEGER NOT NULL,
        username TEXT NOT NULL,
        PRIMARY KEY (snapshot_id, user_id)
    );
    """)


def last_snapshot(db, kind):
    row = db.execute(
        "SELECT id FROM snapshots WHERE kind=? ORDER BY id DESC LIMIT 1", (kind,)
    ).fetchone()
    if not row:
        return None
    return {uid: name for uid, name in db.execute(
        "SELECT user_id, username FROM snapshot_users WHERE snapshot_id=?", (row[0],))}


def save_snapshot(db, kind, users):
    cur = db.execute("INSERT INTO snapshots(kind) VALUES (?)", (kind,))
    db.executemany(
        "INSERT INTO snapshot_users VALUES (?,?,?)",
        [(cur.lastrowid, uid, name) for uid, name in users.items()],
    )
    db.commit()


def diff_text(kind, old, new):
    label = "Подписчики" if kind == "followers" else "Подписки"
    if old is None:
        return f"{label}: первый снапшот, {len(new)}"
    gained = [n for u, n in new.items() if u not in old]
    lost = [n for u, n in old.items() if u not in new]
    if not gained and not lost:
        return None
    lines = [f"{label}: {len(old)} → {len(new)}"]
    lines += [f"+ {n}" for n in gained]
    lines += [f"- {n}" for n in lost]
    return "\n".join(lines)


def tg(method, **params):
    token = os.environ["TG_BOT_TOKEN"]
    data = urllib.parse.urlencode(params).encode()
    with urllib.request.urlopen(
        f"https://api.telegram.org/bot{token}/{method}", data, timeout=60
    ) as r:
        return json.load(r)["result"]


def notify(text):
    print(text)
    if not os.environ.get("TG_BOT_TOKEN") or not os.environ.get("TG_CHAT_ID"):
        return
    keyboard = {"keyboard": [[{"text": CHECK_BUTTON}]], "resize_keyboard": True}
    try:
        tg("sendMessage", chat_id=os.environ["TG_CHAT_ID"], text=text,
           reply_markup=json.dumps(keyboard))
    except Exception as e:
        print(f"telegram error: {e}")


def run_once(L, db, username, manual=False):
    parts = []
    for kind in ("followers", "followees"):
        new = fetch(L, username, kind)
        old = last_snapshot(db, kind)
        text = diff_text(kind, old, new)
        if text:
            parts.append(text)
        save_snapshot(db, kind, new)
        time.sleep(5)
    if parts:
        notify(f"@{username}\n\n" + "\n\n".join(parts))
    elif manual:
        notify("Без изменений с последнего снапшота")
    else:
        print("без изменений")


def poll_commands(offset):
    """Return (new_offset, whether a check was requested)."""
    chat_id = str(os.environ["TG_CHAT_ID"])
    requested = False
    try:
        updates = tg("getUpdates", offset=offset, timeout=POLL_SECONDS)
    except Exception as e:
        print(f"telegram error: {e}")
        time.sleep(POLL_SECONDS)
        return offset, False
    for u in updates:
        offset = u["update_id"] + 1
        msg = u.get("message") or {}
        if str(msg.get("chat", {}).get("id")) != chat_id:
            continue
        text = msg.get("text", "")
        if text in (CHECK_BUTTON, "/check"):
            requested = True
        elif text == "/start":
            notify("Жми «Чек», чтобы сравнить с последним снапшотом")
    return offset, requested


def main():
    load_env()
    username = os.environ.get("IG_USERNAME")
    if not username:
        sys.exit("IG_USERNAME не задан")
    interval = float(os.environ.get("INTERVAL_MINUTES", "60")) * 60
    use_tg = bool(os.environ.get("TG_BOT_TOKEN") and os.environ.get("TG_CHAT_ID"))
    L = get_loader(username)
    db = sqlite3.connect(DB_PATH)
    init_db(db)
    offset, next_run = None, 0
    while True:
        manual = False
        if use_tg:
            offset, manual = poll_commands(offset)
        else:
            time.sleep(max(0, next_run - time.time()))
        if manual or time.time() >= next_run:
            try:
                run_once(L, db, username, manual)
            except Exception as e:
                traceback.print_exc()
                notify(f"Ошибка трекера: {e}")
            next_run = time.time() + interval


if __name__ == "__main__":
    main()

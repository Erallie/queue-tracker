from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .catalog import parse_song_text, remove_new_marker, split_name


def now() -> str:
    return datetime.now(UTC).isoformat()


def alphabetical_key(value: str) -> str:
    folded = value.casefold()
    for article in ("a ", "an ", "the "):
        if folded.startswith(article):
            return folded[len(article):]
    return folded


SEED_SONGLIST = (Path(__file__).resolve().parent.parent / "seed_songlist.md").read_text(encoding="utf-8")

DEFAULT_SETTINGS = {
    "song_text": SEED_SONGLIST,
    "new_play_threshold": 2,
    "new_min_days": 14,
    "recently_graduated_days": 7,
    "last_played_history_limit": 10,
    "default_artist": "Erallie",
    "queue_websocket_url": "wss://sikorsky.mustardmine.com/ws",
    "queue_group": "#275206561",
}


class Store:
    def __init__(self, path: str) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(target)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.migrate()

    def migrate(self) -> None:
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS identities(
          user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          provider TEXT NOT NULL, provider_user_id TEXT NOT NULL, display_name TEXT NOT NULL,
          avatar_url TEXT NOT NULL DEFAULT '', access_token TEXT NOT NULL DEFAULT '',
          refresh_token TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL,
          PRIMARY KEY(provider, provider_user_id), UNIQUE(user_id, provider));
        CREATE TABLE IF NOT EXISTS sessions(
          token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          expires_at TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS oauth_states(
          state TEXT PRIMARY KEY, provider TEXT NOT NULL, mode TEXT NOT NULL, user_id TEXT,
          return_to TEXT NOT NULL, expires_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS songs(
          id TEXT PRIMARY KEY, raw_title TEXT NOT NULL UNIQUE, title TEXT NOT NULL,
          parenthetical TEXT NOT NULL DEFAULT '', section TEXT NOT NULL DEFAULT '',
          is_new INTEGER NOT NULL DEFAULT 0, new_since TEXT, graduated_at TEXT,
          play_count INTEGER NOT NULL DEFAULT 0, last_played TEXT, active INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS song_groups(
          id TEXT PRIMARY KEY, display_name TEXT NOT NULL, position INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS group_members(
          group_id TEXT NOT NULL REFERENCES song_groups(id) ON DELETE CASCADE,
          raw_title TEXT NOT NULL, position INTEGER NOT NULL, PRIMARY KEY(group_id, raw_title));
        CREATE TABLE IF NOT EXISTS tags(
          name TEXT PRIMARY KEY, points INTEGER NOT NULL DEFAULT 0,
          color TEXT NOT NULL DEFAULT '#ab212a', position INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS song_tags(
          raw_title TEXT NOT NULL REFERENCES songs(raw_title) ON DELETE CASCADE,
          tag_name TEXT NOT NULL REFERENCES tags(name) ON DELETE CASCADE,
          PRIMARY KEY(raw_title, tag_name));
        CREATE TABLE IF NOT EXISTS requests(
          id TEXT PRIMARY KEY, user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
          raw_title TEXT NOT NULL, request_name TEXT NOT NULL, requested_at TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'queued');
        CREATE TABLE IF NOT EXISTS play_events(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          raw_title TEXT NOT NULL REFERENCES songs(raw_title) ON DELETE CASCADE,
          played_at TEXT);
        CREATE INDEX IF NOT EXISTS idx_songs_active_new ON songs(active, is_new);
        CREATE INDEX IF NOT EXISTS idx_group_members_title ON group_members(raw_title);
        CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
        CREATE INDEX IF NOT EXISTS idx_play_events_song_time ON play_events(raw_title, played_at);
        """)
        tag_columns = {row["name"] for row in self.db.execute("PRAGMA table_info(tags)")}
        if "position" not in tag_columns:
            self.db.execute("ALTER TABLE tags ADD COLUMN position INTEGER NOT NULL DEFAULT 0")
            existing_tags = self.db.execute("SELECT name FROM tags ORDER BY name='New' DESC, name").fetchall()
            for position, tag in enumerate(existing_tags):
                self.db.execute("UPDATE tags SET position=? WHERE name=?", (position, tag["name"]))
        for key, value in DEFAULT_SETTINGS.items():
            self.db.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (key, json.dumps(value)))
        self.db.execute("INSERT OR IGNORE INTO tags(name,points,color,position) VALUES('New',0,'#d33355',0)")
        self.db.execute("UPDATE tags SET points=0 WHERE name='New'")
        self.db.commit()
        if not self.db.execute("SELECT 1 FROM songs LIMIT 1").fetchone():
            self.sync_songs(str(self.settings()["song_text"]))
            self.db.commit()
        # Preserve the one legacy date that is known without inventing dates for
        # older plays. The aggregate play_count remains authoritative.
        for song in self.db.execute("SELECT raw_title,play_count,last_played FROM songs WHERE play_count>0"):
            if song["last_played"] and not self.db.execute("SELECT 1 FROM play_events WHERE raw_title=? LIMIT 1", (song["raw_title"],)).fetchone():
                self.db.execute(
                    "INSERT INTO play_events(raw_title,played_at) VALUES(?,?)",
                    (song["raw_title"], song["last_played"]),
                )
        self.db.commit()
        if not self.db.execute("SELECT 1 FROM song_groups LIMIT 1").fetchone():
            self.save_groups([
                {"display_name": "Somewhere Over the Rainbow (Judy Garland)", "members": ["Somewhere Over the Rainbow - Jazz Cover (The Wizard of Oz)", "Somewhere Over the Rainbow (Judy Garland)"]},
                {"display_name": "Crossing the Line (Rapunzel's Tangled Adventure)", "members": ["Crossing the Line (Rapunzel's Tangled Adventure)", "Crossing the Line (Tangled the Series)"]},
            ])
        self._trim_all_play_history()
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    def settings(self) -> dict[str, Any]:
        values = {row["key"]: json.loads(row["value"]) for row in self.db.execute("SELECT * FROM settings")}
        return {**DEFAULT_SETTINGS, **values}

    def save_settings(self, values: dict[str, Any]) -> None:
        allowed = DEFAULT_SETTINGS.keys()
        for key in allowed:
            if key in values:
                if key == "last_played_history_limit":
                    value = max(1, int(values[key]))
                elif key == "default_artist":
                    value = str(values[key]).strip() or DEFAULT_SETTINGS["default_artist"]
                else:
                    value = values[key]
                self.db.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, json.dumps(value)))
        if "song_text" in values:
            self.sync_songs(str(values["song_text"]))
        if "last_played_history_limit" in values:
            self._trim_all_play_history()
        self.db.commit()

    def sync_songs(self, text: str) -> None:
        parsed = parse_song_text(text)
        active = {song.raw_title for song in parsed}
        self.db.execute("UPDATE songs SET active=0")
        for song in parsed:
            existing = self.db.execute("SELECT is_new,new_since FROM songs WHERE raw_title=?", (song.raw_title,)).fetchone()
            new_since = existing["new_since"] if existing and existing["new_since"] else (now() if song.is_new else None)
            graduated = None if song.is_new else (now() if existing and existing["is_new"] else None)
            self.db.execute("""INSERT INTO songs(id,raw_title,title,parenthetical,section,is_new,new_since,graduated_at,active)
              VALUES(?,?,?,?,?,?,?,?,1)
              ON CONFLICT(raw_title) DO UPDATE SET title=excluded.title,parenthetical=excluded.parenthetical,
              section=excluded.section,is_new=excluded.is_new,new_since=excluded.new_since,
              graduated_at=COALESCE(excluded.graduated_at,songs.graduated_at),active=1""",
              (str(uuid.uuid4()), song.raw_title, song.title, song.parenthetical, song.section, int(song.is_new), new_since, graduated))
            if song.is_new:
                self.db.execute("INSERT OR IGNORE INTO song_tags VALUES(?, 'New')", (song.raw_title,))
            else:
                self.db.execute("DELETE FROM song_tags WHERE raw_title=? AND tag_name='New'", (song.raw_title,))
        if active:
            placeholders = ",".join("?" for _ in active)
            self.db.execute(f"DELETE FROM song_tags WHERE raw_title NOT IN ({placeholders})", tuple(active))

    def save_groups(self, groups: list[dict[str, Any]]) -> None:
        self.db.execute("DELETE FROM song_groups")
        for position, group in enumerate(groups):
            group_id = str(group.get("id") or uuid.uuid4())
            name = str(group.get("display_name") or "").strip()
            members = [str(x).strip() for x in group.get("members", []) if str(x).strip()]
            if not name or len(members) < 2:
                continue
            self.db.execute("INSERT INTO song_groups VALUES(?,?,?)", (group_id, name, position))
            self.db.executemany("INSERT INTO group_members VALUES(?,?,?)", ((group_id, member, index) for index, member in enumerate(members)))
        self._trim_all_play_history()
        self.db.commit()

    def groups(self) -> list[dict[str, Any]]:
        result = []
        for row in self.db.execute("SELECT * FROM song_groups ORDER BY position"):
            members = [item["raw_title"] for item in self.db.execute("SELECT raw_title FROM group_members WHERE group_id=? ORDER BY position", (row["id"],))]
            result.append({"id": row["id"], "display_name": row["display_name"], "members": members})
        return result

    def tags(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self.db.execute("SELECT name,points,color FROM tags ORDER BY position, name")]

    def save_tags(self, tags: list[dict[str, Any]]) -> None:
        keep = {"New"}
        for position, tag in enumerate(tags):
            name = str(tag.get("name") or "").strip()
            if not name:
                continue
            keep.add(name)
            points = 0 if name == "New" else int(tag.get("points") or 0)
            self.db.execute("""INSERT INTO tags(name,points,color,position) VALUES(?,?,?,?)
              ON CONFLICT(name) DO UPDATE SET points=excluded.points,color=excluded.color,position=excluded.position""",
              (name, points, str(tag.get("color") or "#ab212a"), position))
        placeholders = ",".join("?" for _ in keep)
        self.db.execute(f"DELETE FROM tags WHERE name NOT IN ({placeholders})", tuple(keep))
        self.db.commit()

    def catalog(self) -> dict[str, Any]:
        default_artist = str(self.settings()["default_artist"])
        member_to_group: dict[str, sqlite3.Row] = {}
        groups: dict[str, dict[str, Any]] = {}
        for group in self.db.execute("SELECT * FROM song_groups ORDER BY position"):
            members = [row["raw_title"] for row in self.db.execute("SELECT raw_title FROM group_members WHERE group_id=? ORDER BY position", (group["id"],))]
            groups[group["id"]] = {"row": group, "members": members}
            for member in members:
                member_to_group[member] = group
        output: list[dict[str, Any]] = []
        emitted: set[str] = set()
        for song in self.db.execute("SELECT * FROM songs WHERE active=1"):
            group = member_to_group.get(song["raw_title"])
            if group:
                if group["id"] in emitted:
                    continue
                emitted.add(group["id"])
                info = groups[group["id"]]
                rows = [self.db.execute("SELECT * FROM songs WHERE raw_title=?", (member,)).fetchone() for member in info["members"]]
                rows = [row for row in rows if row]
                title, parenthetical = split_name(group["display_name"])
                parenthetical = parenthetical or default_artist
                play_count = sum(row["play_count"] for row in rows)
                last_played = max((row["last_played"] for row in rows if row["last_played"]), default=None)
                is_new = any(row["is_new"] for row in rows)
                song_id = f"group:{group['id']}"
                tags = self._tags_for([row["raw_title"] for row in rows], is_new)
                output.append(self._song_json(song_id, title, parenthetical, tags, is_new, play_count, last_played))
            else:
                parenthetical = song["parenthetical"] or default_artist
                tags = self._tags_for([song["raw_title"]], bool(song["is_new"]))
                output.append(self._song_json(song["id"], song["title"], parenthetical, tags, bool(song["is_new"]), song["play_count"], song["last_played"]))
        output.sort(key=lambda song: (
            not song["is_new"],
            -song["tag_points"],
            bool(song["last_played"]),
            song["last_played"][:10] if song["last_played"] else "",
            song["play_count"],
            alphabetical_key(song["parenthetical"]),
            alphabetical_key(song["title"]),
        ))
        return {"songs": output, "tags": self.tags()}

    def _tags_for(self, raw_titles: list[str], is_new: bool) -> list[str]:
        if not raw_titles:
            return ["New"] if is_new else []
        placeholders = ",".join("?" for _ in raw_titles)
        tags = {row[0] for row in self.db.execute(f"SELECT tag_name FROM song_tags WHERE raw_title IN ({placeholders})", tuple(raw_titles))}
        if is_new: tags.add("New")
        else: tags.discard("New")
        positions = {row["name"]: row["position"] for row in self.db.execute("SELECT name,position FROM tags")}
        return sorted(tags, key=lambda value: (positions.get(value, 1_000_000), value.casefold()))

    def _song_json(self, song_id: str, title: str, parenthetical: str, tags: list[str], is_new: bool, play_count: int, last_played: str | None) -> dict[str, Any]:
        points = 0
        for tag in tags:
            row = self.db.execute("SELECT points FROM tags WHERE name=?", (tag,)).fetchone()
            points += row[0] if row else 0
        value = {"id": song_id, "title": title, "parenthetical": parenthetical, "tags": tags, "is_new": is_new, "tag_points": points, "play_count": play_count, "last_played": last_played}
        return value

    def request_title(self, song_id: str) -> str | None:
        if song_id.startswith("group:"):
            row = self.db.execute("SELECT raw_title FROM group_members WHERE group_id=? ORDER BY position LIMIT 1", (song_id[6:],)).fetchone()
        else:
            row = self.db.execute("SELECT raw_title FROM songs WHERE id=? AND active=1", (song_id,)).fetchone()
        return row[0] if row else None

    def record_play(self, raw_title: str, delta: int = 1) -> None:
        song = self.db.execute("SELECT play_count FROM songs WHERE raw_title=?", (raw_title,)).fetchone()
        if not song:
            return
        if delta > 0:
            played_at = now()
            self.db.execute("UPDATE songs SET play_count=play_count+? WHERE raw_title=?", (delta, raw_title))
            self.db.executemany(
                "INSERT INTO play_events(raw_title,played_at) VALUES(?,?)",
                ((raw_title, played_at) for _ in range(delta)),
            )
        elif delta < 0:
            decrement = min(-delta, song["play_count"])
            rows = self.db.execute(
                """SELECT id FROM play_events WHERE raw_title=?
                   ORDER BY played_at IS NULL, played_at DESC, id DESC LIMIT ?""",
                (raw_title, decrement),
            ).fetchall()
            self.db.executemany("DELETE FROM play_events WHERE id=?", ((row["id"],) for row in rows))
            self.db.execute("UPDATE songs SET play_count=MAX(0,play_count-?) WHERE raw_title=?", (decrement, raw_title))
        history_titles = self._history_titles_for_raw_title(raw_title)
        self._trim_play_history(history_titles)
        self._refresh_last_played(history_titles)
        self.db.commit()

    def _refresh_last_played(self, raw_titles: list[str]) -> None:
        if not raw_titles:
            return
        placeholders = ",".join("?" for _ in raw_titles)
        summary = self.db.execute(
            f"SELECT MAX(played_at) AS last_played FROM play_events WHERE raw_title IN ({placeholders})",
            tuple(raw_titles),
        ).fetchone()
        self.db.execute(
            f"UPDATE songs SET last_played=? WHERE raw_title IN ({placeholders})",
            (summary["last_played"], *raw_titles),
        )

    def _history_titles_for_raw_title(self, raw_title: str) -> list[str]:
        group = self.db.execute(
            "SELECT group_id FROM group_members WHERE raw_title=? LIMIT 1", (raw_title,)
        ).fetchone()
        if not group:
            return [raw_title]
        return [
            row["raw_title"]
            for row in self.db.execute(
                "SELECT raw_title FROM group_members WHERE group_id=? ORDER BY position",
                (group["group_id"],),
            )
        ]

    def _trim_play_history(self, raw_titles: list[str]) -> None:
        if not raw_titles:
            return
        limit = max(1, int(self.settings()["last_played_history_limit"]))
        placeholders = ",".join("?" for _ in raw_titles)
        rows = self.db.execute(
            f"""SELECT id FROM play_events WHERE raw_title IN ({placeholders})
                ORDER BY played_at IS NULL, played_at DESC, id DESC""",
            tuple(raw_titles),
        ).fetchall()
        self.db.executemany("DELETE FROM play_events WHERE id=?", ((row["id"],) for row in rows[limit:]))

    def _trim_all_play_history(self) -> None:
        grouped: set[str] = set()
        for group in self.db.execute("SELECT id FROM song_groups"):
            titles = [
                row["raw_title"]
                for row in self.db.execute("SELECT raw_title FROM group_members WHERE group_id=?", (group["id"],))
            ]
            grouped.update(titles)
            self._trim_play_history(titles)
            self._refresh_last_played(titles)
        for song in self.db.execute("SELECT raw_title FROM songs"):
            if song["raw_title"] not in grouped:
                self._trim_play_history([song["raw_title"]])
                self._refresh_last_played([song["raw_title"]])

    def _titles_for_song_id(self, song_id: str) -> list[str]:
        if song_id.startswith("group:"):
            return [
                row["raw_title"]
                for row in self.db.execute(
                    "SELECT raw_title FROM group_members WHERE group_id=? ORDER BY position",
                    (song_id[6:],),
                )
            ]
        row = self.db.execute("SELECT raw_title FROM songs WHERE id=? AND active=1", (song_id,)).fetchone()
        return [row["raw_title"]] if row else []

    def adjust_play(self, song_id: str, delta: int) -> None:
        titles = self._titles_for_song_id(song_id)
        if not titles or delta == 0:
            return
        if delta > 0:
            self.record_play(titles[0], delta)
            return
        placeholders = ",".join("?" for _ in titles)
        latest = self.db.execute(
            f"""SELECT raw_title FROM play_events WHERE raw_title IN ({placeholders})
                ORDER BY played_at IS NULL, played_at DESC, id DESC LIMIT 1""",
            tuple(titles),
        ).fetchone()
        if latest:
            target = latest["raw_title"]
        else:
            target_row = self.db.execute(
                f"SELECT raw_title FROM songs WHERE raw_title IN ({placeholders}) AND play_count>0 ORDER BY last_played DESC LIMIT 1",
                tuple(titles),
            ).fetchone()
            target = target_row["raw_title"] if target_row else None
        if target:
            self.record_play(target, delta)

    def remove_new_tag(self, song_id: str) -> bool:
        if song_id.startswith("group:"):
            rows = self.db.execute(
                "SELECT raw_title FROM group_members WHERE group_id=? ORDER BY position",
                (song_id[6:],),
            ).fetchall()
            raw_titles = {row["raw_title"] for row in rows}
        else:
            row = self.db.execute(
                "SELECT raw_title FROM songs WHERE id=? AND active=1", (song_id,)
            ).fetchone()
            raw_titles = {row["raw_title"]} if row else set()
        if not raw_titles:
            return False
        text = str(self.settings()["song_text"])
        self.save_settings({"song_text": remove_new_marker(text, raw_titles)})
        return True

    def record_request(self, user_id: str, raw_title: str, request_name: str) -> None:
        self.db.execute("INSERT INTO requests(id,user_id,raw_title,request_name,requested_at) VALUES(?,?,?,?,?)", (str(uuid.uuid4()), user_id, raw_title, request_name, now()))
        self.db.commit()

    def save_song_tags(self, raw_title: str, tags: list[str]) -> None:
        self.db.execute("DELETE FROM song_tags WHERE raw_title=? AND tag_name!='New'", (raw_title,))
        for tag in tags:
            if tag != "New":
                self.db.execute("INSERT OR IGNORE INTO song_tags VALUES(?,?)", (raw_title, tag))
        self.db.commit()

    def hourly_maintenance(self) -> list[str]:
        settings = self.settings()
        threshold = int(settings["new_play_threshold"])
        minimum = timedelta(days=int(settings["new_min_days"]))
        graduated: set[str] = set()
        current = datetime.now(UTC)
        for row in self.db.execute("SELECT raw_title,play_count,new_since FROM songs WHERE active=1 AND is_new=1"):
            since = datetime.fromisoformat(row["new_since"]) if row["new_since"] else current
            if row["play_count"] >= threshold and current - since >= minimum:
                graduated.add(row["raw_title"])
        if graduated:
            text = remove_new_marker(str(settings["song_text"]), graduated)
            self.save_settings({"song_text": text})
        return sorted(graduated)

    def create_user(self) -> str:
        user_id = str(uuid.uuid4()); self.db.execute("INSERT INTO users VALUES(?,?)", (user_id, now())); self.db.commit(); return user_id

    def identity_user(self, provider: str, provider_user_id: str) -> str | None:
        row = self.db.execute("SELECT user_id FROM identities WHERE provider=? AND provider_user_id=?", (provider, provider_user_id)).fetchone(); return row[0] if row else None

    def identities(self, user_id: str, tokens: bool = False) -> list[dict[str, Any]]:
        columns = "provider,provider_user_id,display_name,avatar_url" + (",access_token,refresh_token" if tokens else "")
        return [dict(row) for row in self.db.execute(f"SELECT {columns} FROM identities WHERE user_id=? ORDER BY provider", (user_id,))]

    def save_identity(self, user_id: str, provider: str, provider_user_id: str, display_name: str, avatar_url: str, access_token: str, refresh_token: str) -> None:
        self.db.execute("""INSERT INTO identities VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(provider,provider_user_id) DO UPDATE SET display_name=excluded.display_name,avatar_url=excluded.avatar_url,access_token=excluded.access_token,refresh_token=CASE WHEN excluded.refresh_token='' THEN identities.refresh_token ELSE excluded.refresh_token END,updated_at=excluded.updated_at""", (user_id,provider,provider_user_id,display_name,avatar_url,access_token,refresh_token,now())); self.db.commit()

    def unlink_identity(self, user_id: str, provider: str) -> bool:
        count = self.db.execute("SELECT COUNT(*) FROM identities WHERE user_id=?", (user_id,)).fetchone()[0]
        if count <= 1:
            self.db.execute("DELETE FROM users WHERE id=?", (user_id,)); deleted = True
        else:
            self.db.execute("DELETE FROM identities WHERE user_id=? AND provider=?", (user_id, provider)); deleted = False
        self.db.commit(); return deleted

    def save_session(self, token_hash: str, user_id: str, expires_at: str) -> None:
        self.db.execute("INSERT INTO sessions VALUES(?,?,?,?)", (token_hash,user_id,expires_at,now())); self.db.commit()

    def session_user(self, token_hash: str) -> str | None:
        self.db.execute("DELETE FROM sessions WHERE expires_at<?", (now(),)); row = self.db.execute("SELECT user_id FROM sessions WHERE token_hash=? AND expires_at>=?", (token_hash,now())).fetchone(); self.db.commit(); return row[0] if row else None

    def delete_session(self, token_hash: str) -> None:
        self.db.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash,)); self.db.commit()

    def save_oauth_state(self, state: str, provider: str, mode: str, user_id: str | None, return_to: str) -> None:
        expires = (datetime.now(UTC)+timedelta(minutes=10)).isoformat(); self.db.execute("INSERT INTO oauth_states VALUES(?,?,?,?,?,?)", (state,provider,mode,user_id,return_to,expires)); self.db.commit()

    def pop_oauth_state(self, state: str) -> dict[str, Any] | None:
        row = self.db.execute("SELECT * FROM oauth_states WHERE state=? AND expires_at>=?", (state,now())).fetchone(); self.db.execute("DELETE FROM oauth_states WHERE state=? OR expires_at<?", (state,now())); self.db.commit(); return dict(row) if row else None

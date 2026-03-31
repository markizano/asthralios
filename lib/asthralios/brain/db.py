"""
SQLite-backed inbox log for the 2nd Brain.

Schema (inbox_log table):
  id                INTEGER PRIMARY KEY AUTOINCREMENT
  received_at       TEXT    (ISO 8601 UTC)
  source_platform   TEXT    slack | discord
  source_user       TEXT
  source_channel    TEXT
  raw_message       TEXT
  category          TEXT    nullable
  name              TEXT    nullable
  confidence        REAL    nullable
  filed_path        TEXT    nullable — absolute path to the Markdown file
  status            TEXT    filed | needs_review | fix_applied
  clarification_q   TEXT    nullable — question sent back to user
  fix_original_cat  TEXT    nullable — original category before a fix was applied

The digest_log table tracks when digests were last sent:
  id                INTEGER PRIMARY KEY AUTOINCREMENT
  sent_at           TEXT    (ISO 8601 UTC)
  digest_type       TEXT    daily | weekly
  message_count     INTEGER — how many inbox entries were included

The users table stores resolved identity and role:
  id                INTEGER PRIMARY KEY AUTOINCREMENT
  platform          TEXT    slack | discord
  platform_user_id  TEXT    raw API user ID
  display_name      TEXT    nullable — best-effort from platform
  role              TEXT    admin | user | blocked
  first_seen        TEXT    (ISO 8601 UTC)
  last_seen         TEXT    (ISO 8601 UTC)

The access_log table is the append-only audit trail:
  id                INTEGER PRIMARY KEY AUTOINCREMENT
  logged_at         TEXT    (ISO 8601 UTC)
  platform          TEXT
  platform_user_id  TEXT
  display_name      TEXT    nullable
  role_at_time      TEXT
  channel           TEXT
  message_preview   TEXT    nullable (truncated to 200 chars)
  action            TEXT
  outcome           TEXT
  detail            TEXT    nullable
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from asthralios.brain.schema import InboxLogRecord
import asthralios

log = asthralios.getLogger(__name__)

CREATE_INBOX_LOG = """
CREATE TABLE IF NOT EXISTS inbox_log (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    received_at      TEXT NOT NULL,
    source_platform  TEXT NOT NULL,
    source_user      TEXT NOT NULL,
    source_channel   TEXT NOT NULL,
    raw_message      TEXT NOT NULL,
    category         TEXT,
    name             TEXT,
    confidence       REAL,
    filed_path       TEXT,
    status           TEXT NOT NULL DEFAULT 'filed',
    clarification_q  TEXT,
    fix_original_cat TEXT
);
"""

CREATE_DIGEST_LOG = """
CREATE TABLE IF NOT EXISTS digest_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    sent_at       TEXT NOT NULL,
    digest_type   TEXT NOT NULL,
    message_count INTEGER NOT NULL DEFAULT 0
);
"""

CREATE_USERS = """
CREATE TABLE IF NOT EXISTS users (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    platform         TEXT NOT NULL,
    platform_user_id TEXT NOT NULL,
    display_name     TEXT,
    role             TEXT NOT NULL DEFAULT 'user',
    first_seen       TEXT NOT NULL,
    last_seen        TEXT NOT NULL,
    UNIQUE(platform, platform_user_id)
);
"""

CREATE_ACCESS_LOG = """
CREATE TABLE IF NOT EXISTS access_log (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    logged_at        TEXT NOT NULL,
    platform         TEXT NOT NULL,
    platform_user_id TEXT NOT NULL,
    display_name     TEXT,
    role_at_time     TEXT NOT NULL,
    channel          TEXT NOT NULL,
    message_preview  TEXT,
    action           TEXT NOT NULL,
    outcome          TEXT NOT NULL,
    detail           TEXT
);
"""


class BrainDB:

    def __init__(self, db_path: str):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self):
        with self._connect() as conn:
            conn.execute(CREATE_INBOX_LOG)
            conn.execute(CREATE_DIGEST_LOG)
            conn.execute(CREATE_USERS)
            conn.execute(CREATE_ACCESS_LOG)
            conn.commit()

    # ── Inbox log ─────────────────────────────────────────────────────────────

    def log_entry(self, record: InboxLogRecord) -> int:
        """Insert a new inbox log record. Returns the row id."""
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO inbox_log
                   (received_at, source_platform, source_user, source_channel,
                    raw_message, category, name, confidence, filed_path,
                    status, clarification_q, fix_original_cat)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    record.received_at.isoformat(),
                    record.source_platform,
                    record.source_user,
                    record.source_channel,
                    record.raw_message,
                    record.category,
                    record.name,
                    record.confidence,
                    record.filed_path,
                    record.status,
                    record.clarification_question,
                    record.fix_original_category,
                )
            )
            conn.commit()
            return cur.lastrowid

    def update_status(self, row_id: int, status: str, fix_original_cat: Optional[str] = None):
        with self._connect() as conn:
            conn.execute(
                "UPDATE inbox_log SET status=?, fix_original_cat=? WHERE id=?",
                (status, fix_original_cat, row_id)
            )
            conn.commit()

    def get_entry(self, row_id: int) -> Optional[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                "SELECT * FROM inbox_log WHERE id=?", (row_id,)
            ).fetchone()

    def get_latest_for_user(self, source_user: str, statuses: list) -> Optional[sqlite3.Row]:
        """Return the most recent inbox_log row for a user with a given status."""
        placeholders = ','.join('?' * len(statuses))
        with self._connect() as conn:
            return conn.execute(
                f"SELECT * FROM inbox_log WHERE source_user=? AND status IN ({placeholders}) ORDER BY received_at DESC LIMIT 1",
                [source_user] + list(statuses)
            ).fetchone()

    def update_filed_path(self, row_id: int, filed_path: str):
        with self._connect() as conn:
            conn.execute(
                "UPDATE inbox_log SET filed_path=? WHERE id=?",
                (filed_path, row_id)
            )
            conn.commit()

    def get_active_projects(self) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                "SELECT * FROM inbox_log WHERE category='projects' AND status != 'fix_applied' ORDER BY received_at DESC LIMIT 30"
            ).fetchall()

    def get_pending_people(self) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                "SELECT * FROM inbox_log WHERE category='people' ORDER BY received_at DESC LIMIT 20"
            ).fetchall()

    def get_open_admin(self) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                "SELECT * FROM inbox_log WHERE category='admin' AND status='filed' ORDER BY received_at DESC LIMIT 20"
            ).fetchall()

    def get_past_week(self) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                """SELECT * FROM inbox_log
                   WHERE received_at >= datetime('now', '-7 days')
                   ORDER BY received_at DESC"""
            ).fetchall()

    # ── Digest log ────────────────────────────────────────────────────────────

    def log_digest(self, digest_type: str, message_count: int):
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO digest_log (sent_at, digest_type, message_count) VALUES (?,?,?)",
                (datetime.now(timezone.utc).isoformat(), digest_type, message_count)
            )
            conn.commit()

    def get_last_digest(self, digest_type: str) -> Optional[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                "SELECT * FROM digest_log WHERE digest_type=? ORDER BY sent_at DESC LIMIT 1",
                (digest_type,)
            ).fetchone()

    # ── Users ─────────────────────────────────────────────────────────────────

    def get_or_create_user(
        self,
        platform: str,
        platform_user_id: str,
        display_name: str,
        default_role: str = 'user',
    ) -> str:
        """
        Look up the user. If not found, insert with default_role.
        Always update last_seen and display_name.
        Returns the resolved role string.
        """
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT role FROM users WHERE platform=? AND platform_user_id=?",
                (platform, platform_user_id)
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE users SET last_seen=?, display_name=? WHERE platform=? AND platform_user_id=?",
                    (now, display_name, platform, platform_user_id)
                )
                conn.commit()
                return row['role']
            else:
                conn.execute(
                    """INSERT INTO users
                       (platform, platform_user_id, display_name, role, first_seen, last_seen)
                       VALUES (?,?,?,?,?,?)""",
                    (platform, platform_user_id, display_name, default_role, now, now)
                )
                conn.commit()
                return default_role

    def upsert_user(
        self,
        platform: str,
        platform_user_id: str,
        display_name: str,
        role: str,
        force_role: bool = False,
    ):
        """
        Insert or update a user record. If force_role=True, overwrite the role
        even if the user already exists (used for admin seeding from config).
        """
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, role FROM users WHERE platform=? AND platform_user_id=?",
                (platform, platform_user_id)
            ).fetchone()
            if row:
                if force_role:
                    conn.execute(
                        "UPDATE users SET role=?, display_name=?, last_seen=? WHERE id=?",
                        (role, display_name, now, row['id'])
                    )
                else:
                    conn.execute(
                        "UPDATE users SET display_name=?, last_seen=? WHERE id=?",
                        (display_name, now, row['id'])
                    )
            else:
                conn.execute(
                    """INSERT INTO users
                       (platform, platform_user_id, display_name, role, first_seen, last_seen)
                       VALUES (?,?,?,?,?,?)""",
                    (platform, platform_user_id, display_name, role, now, now)
                )
            conn.commit()

    def set_user_role(self, platform: str, platform_user_id: str, role: str):
        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET role=? WHERE platform=? AND platform_user_id=?",
                (role, platform, platform_user_id)
            )
            conn.commit()

    def list_users(self) -> list:
        with self._connect() as conn:
            return conn.execute(
                "SELECT * FROM users ORDER BY last_seen DESC"
            ).fetchall()

    # ── Access log ────────────────────────────────────────────────────────────

    def log_access(
        self,
        platform: str,
        platform_user_id: str,
        display_name: str,
        role_at_time: str,
        channel: str,
        message_preview: str,
        action: str,
        outcome: str,
        detail: Optional[str] = None,
    ):
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO access_log
                   (logged_at, platform, platform_user_id, display_name, role_at_time,
                    channel, message_preview, action, outcome, detail)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (now, platform, platform_user_id, display_name, role_at_time,
                 channel, message_preview, action, outcome, detail)
            )
            conn.commit()

    def get_access_log(
        self,
        limit: int = 50,
        platform_user_id: Optional[str] = None,
    ) -> list:
        with self._connect() as conn:
            if platform_user_id:
                return conn.execute(
                    "SELECT * FROM access_log WHERE platform_user_id=? ORDER BY logged_at DESC LIMIT ?",
                    (platform_user_id, limit)
                ).fetchall()
            return conn.execute(
                "SELECT * FROM access_log ORDER BY logged_at DESC LIMIT ?",
                (limit,)
            ).fetchall()

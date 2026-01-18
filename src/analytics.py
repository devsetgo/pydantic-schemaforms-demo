"""Minimal self-hosted analytics + error capture.

Goals:
- Zero external services
- Minimal dependencies (stdlib only)
- Reasonable behavior behind a reverse proxy (e.g., Traefik)

Storage:
- SQLite file (path configurable via env var)
- Short retention window (configurable via env var)

This is intentionally lightweight: it is *not* a full observability stack.
"""

from __future__ import annotations

import os
import re
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_int(value: str | None, default: int) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def get_db_path() -> str:
    # Default to /tmp so it works in containers without extra volumes.
    return os.environ.get("ANALYTICS_DB_PATH", "/tmp/schemaforms_analytics.sqlite")


def get_retention_days() -> int:
    return max(1, _parse_int(os.environ.get("ANALYTICS_RETENTION_DAYS"), 7))


def get_max_rows() -> int:
    # Additional safety valve: if traffic spikes, keep DB bounded.
    return max(1_000, _parse_int(os.environ.get("ANALYTICS_MAX_ROWS"), 200_000))


def _connect() -> sqlite3.Connection:
    db_path = get_db_path()
    parent = os.path.dirname(db_path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    conn = sqlite3.connect(db_path, timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    # Improve concurrency with multiple workers.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS request_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                method TEXT NOT NULL,
                path TEXT NOT NULL,
                status_code INTEGER NOT NULL,
                duration_ms INTEGER NOT NULL,
                client_ip TEXT,
                country TEXT,
                user_agent TEXT,
                browser TEXT,
                referer TEXT
            )
            """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_request_log_ts ON request_log(ts)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_request_log_path ON request_log(path)")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_request_log_status ON request_log(status_code)"
        )

        conn.execute("""
            CREATE TABLE IF NOT EXISTS error_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                kind TEXT NOT NULL,
                message TEXT NOT NULL,
                detail TEXT,
                path TEXT,
                method TEXT,
                status_code INTEGER,
                client_ip TEXT,
                user_agent TEXT
            )
            """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_error_log_ts ON error_log(ts)")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """)


def _browser_family(user_agent: str | None) -> str:
    ua = (user_agent or "").lower()
    if not ua:
        return "unknown"
    # Order matters.
    if "edg/" in ua or "edge/" in ua:
        return "edge"
    if "chrome/" in ua and "chromium" not in ua and "edg/" not in ua:
        return "chrome"
    if "firefox/" in ua:
        return "firefox"
    if "safari/" in ua and "chrome/" not in ua:
        return "safari"
    if "curl/" in ua or "wget/" in ua or "httpie" in ua:
        return "cli"
    return "other"


_ip_re = re.compile(r"^(\d{1,3}(?:\.\d{1,3}){3})$")


def extract_client_ip(headers: dict[str, str], fallback: str | None = None) -> str | None:
    # Prefer X-Forwarded-For (first IP is the original client).
    xff = headers.get("x-forwarded-for")
    if xff:
        first = xff.split(",")[0].strip()
        if first:
            return first

    xri = headers.get("x-real-ip")
    if xri:
        return xri.strip() or fallback

    return fallback


def extract_country(headers: dict[str, str]) -> str | None:
    # Optional: if you later configure Traefik / upstream to provide a country header.
    for key in ("cf-ipcountry", "x-country", "x-forwarded-country", "x-geo-country"):
        value = headers.get(key)
        if value:
            value = value.strip()
            if value:
                return value
    return None


def _iso(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).isoformat()


def _should_prune(conn: sqlite3.Connection) -> bool:
    row = conn.execute("SELECT value FROM meta WHERE key='last_prune_ts'").fetchone()
    if not row:
        return True
    try:
        last = datetime.fromisoformat(row["value"])
    except Exception:
        return True
    return (_utcnow() - last) > timedelta(minutes=10)


def _set_last_prune(conn: sqlite3.Connection) -> None:
    conn.execute(
        "INSERT INTO meta(key, value) VALUES('last_prune_ts', ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (_iso(_utcnow()),),
    )


def _prune(conn: sqlite3.Connection) -> None:
    cutoff = _utcnow() - timedelta(days=get_retention_days())
    cutoff_iso = _iso(cutoff)

    conn.execute("DELETE FROM request_log WHERE ts < ?", (cutoff_iso,))
    conn.execute("DELETE FROM error_log WHERE ts < ?", (cutoff_iso,))

    max_rows = get_max_rows()
    # If still too big, trim oldest rows.
    row = conn.execute("SELECT COUNT(*) AS c FROM request_log").fetchone()
    if row and int(row["c"]) > max_rows:
        to_delete = int(row["c"]) - max_rows
        conn.execute(
            "DELETE FROM request_log WHERE id IN (SELECT id FROM request_log ORDER BY id ASC LIMIT ?)",
            (to_delete,),
        )

    row = conn.execute("SELECT COUNT(*) AS c FROM error_log").fetchone()
    if row and int(row["c"]) > max_rows:
        to_delete = int(row["c"]) - max_rows
        conn.execute(
            "DELETE FROM error_log WHERE id IN (SELECT id FROM error_log ORDER BY id ASC LIMIT ?)",
            (to_delete,),
        )


def record_request(
    *,
    method: str,
    path: str,
    status_code: int,
    duration_ms: int,
    client_ip: str | None,
    country: str | None,
    user_agent: str | None,
    referer: str | None,
) -> None:
    try:
        with _connect() as conn:
            if _should_prune(conn):
                _prune(conn)
                _set_last_prune(conn)

            conn.execute(
                """
                INSERT INTO request_log(
                    ts, method, path, status_code, duration_ms,
                    client_ip, country, user_agent, browser, referer
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """.strip(),
                (
                    _iso(_utcnow()),
                    method,
                    path,
                    int(status_code),
                    int(duration_ms),
                    client_ip,
                    country,
                    user_agent,
                    _browser_family(user_agent),
                    referer,
                ),
            )
    except Exception:
        # Analytics must never break the app.
        return


def record_error(
    *,
    kind: str,
    message: str,
    detail: str | None = None,
    path: str | None = None,
    method: str | None = None,
    status_code: int | None = None,
    client_ip: str | None = None,
    user_agent: str | None = None,
) -> None:
    try:
        with _connect() as conn:
            if _should_prune(conn):
                _prune(conn)
                _set_last_prune(conn)

            conn.execute(
                """
                INSERT INTO error_log(
                    ts, kind, message, detail,
                    path, method, status_code, client_ip, user_agent
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """.strip(),
                (
                    _iso(_utcnow()),
                    kind,
                    message,
                    detail,
                    path,
                    method,
                    int(status_code) if status_code is not None else None,
                    client_ip,
                    user_agent,
                ),
            )
    except Exception:
        return


@dataclass(frozen=True)
class AnalyticsSummary:
    since_iso: str
    total_requests: int
    unique_ips: int
    avg_duration_ms: int
    top_paths: list[dict[str, Any]]
    status_counts: list[dict[str, Any]]
    browser_counts: list[dict[str, Any]]


def _since_iso(days: int) -> str:
    since = _utcnow() - timedelta(days=max(0, days))
    return _iso(since)


def get_summary(*, days: int = 1, top_n: int = 10) -> AnalyticsSummary:
    since = _since_iso(days)
    with _connect() as conn:
        total = conn.execute(
            "SELECT COUNT(*) AS c FROM request_log WHERE ts >= ?",
            (since,),
        ).fetchone()["c"]

        unique_ips = conn.execute(
            "SELECT COUNT(DISTINCT client_ip) AS c FROM request_log WHERE ts >= ? AND client_ip IS NOT NULL",
            (since,),
        ).fetchone()["c"]

        avg_dur = conn.execute(
            "SELECT COALESCE(AVG(duration_ms), 0) AS v FROM request_log WHERE ts >= ?",
            (since,),
        ).fetchone()["v"]

        top_paths = [
            dict(r)
            for r in conn.execute(
                """
                SELECT path, COUNT(*) AS count
                FROM request_log
                WHERE ts >= ?
                GROUP BY path
                ORDER BY count DESC
                LIMIT ?
                """.strip(),
                (since, int(top_n)),
            ).fetchall()
        ]

        status_counts = [
            dict(r)
            for r in conn.execute(
                """
                SELECT status_code, COUNT(*) AS count
                FROM request_log
                WHERE ts >= ?
                GROUP BY status_code
                ORDER BY count DESC
                """.strip(),
                (since,),
            ).fetchall()
        ]

        browser_counts = [
            dict(r)
            for r in conn.execute(
                """
                SELECT browser, COUNT(*) AS count
                FROM request_log
                WHERE ts >= ?
                GROUP BY browser
                ORDER BY count DESC
                """.strip(),
                (since,),
            ).fetchall()
        ]

    return AnalyticsSummary(
        since_iso=since,
        total_requests=int(total),
        unique_ips=int(unique_ips),
        avg_duration_ms=int(avg_dur or 0),
        top_paths=top_paths,
        status_counts=status_counts,
        browser_counts=browser_counts,
    )


def get_recent_requests(*, limit: int = 200) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT ts, method, path, status_code, duration_ms, client_ip, country, browser, referer
            FROM request_log
            ORDER BY id DESC
            LIMIT ?
            """.strip(),
            (int(limit),),
        ).fetchall()
    return [dict(r) for r in rows]


def get_recent_errors(*, limit: int = 200) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT ts, kind, message, detail, path, method, status_code, client_ip
            FROM error_log
            ORDER BY id DESC
            LIMIT ?
            """.strip(),
            (int(limit),),
        ).fetchall()
    return [dict(r) for r in rows]


def purge_all() -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM request_log")
        conn.execute("DELETE FROM error_log")
        conn.execute("DELETE FROM meta")

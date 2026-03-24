"""
PostgreSQL session and I/O logging for SuperBot.

Stores every user input, bot output, and agent execution metadata
in a local PostgreSQL database for analysis and improvement.

Uses asyncpg for async compatibility with the existing event loop.
Gracefully degrades -- if DB is unreachable, logs a warning and continues.
"""

import asyncio
import os
from datetime import datetime, timezone

import structlog

log = structlog.get_logger(__name__)

# Lazy import -- asyncpg is optional; bot runs without it
_pool = None

DATABASE_URL = os.environ.get(
    "SUPERBOT_DATABASE_URL",
    "postgresql://hanjing@localhost:5432/superbot",
)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
    id              SERIAL PRIMARY KEY,
    thread_ts       TEXT NOT NULL,
    channel_id      TEXT NOT NULL,
    user_id         TEXT NOT NULL,
    session_id      TEXT,
    task_subtype    TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (channel_id, thread_ts)
);

CREATE TABLE IF NOT EXISTS messages (
    id              SERIAL PRIMARY KEY,
    session_fk      INT REFERENCES sessions(id),
    direction       TEXT NOT NULL CHECK (direction IN ('user_input', 'bot_output')),
    content         TEXT NOT NULL,
    slack_ts        TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS agent_executions (
    id              SERIAL PRIMARY KEY,
    session_fk      INT REFERENCES sessions(id),
    prompt          TEXT,
    duration_secs   REAL,
    num_turns       INT,
    subtype         TEXT,
    result_text     TEXT,
    error           TEXT,
    git_commits     JSONB,
    pr_url          TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_fk);
CREATE INDEX IF NOT EXISTS idx_executions_session ON agent_executions(session_fk);
CREATE INDEX IF NOT EXISTS idx_sessions_created ON sessions(created_at);
"""


async def init() -> bool:
    """Initialize connection pool and create tables. Returns True on success."""
    global _pool
    try:
        import asyncpg
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=3)
        async with _pool.acquire() as conn:
            await conn.execute(SCHEMA_SQL)
        log.info("db.initialized", url=DATABASE_URL.split("@")[-1])
        return True
    except Exception as exc:
        log.warning("db.init_failed", error=str(exc))
        _pool = None
        return False


async def close():
    """Close the connection pool."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


async def upsert_session(
    channel_id: str,
    thread_ts: str,
    user_id: str,
    session_id: str | None = None,
    task_subtype: str | None = None,
) -> int | None:
    """Insert or update a session row. Returns the session PK or None on failure."""
    if not _pool:
        return None
    try:
        async with _pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO sessions (channel_id, thread_ts, user_id, session_id, task_subtype)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (channel_id, thread_ts)
                DO UPDATE SET
                    session_id = COALESCE(EXCLUDED.session_id, sessions.session_id),
                    task_subtype = COALESCE(EXCLUDED.task_subtype, sessions.task_subtype)
                RETURNING id
                """,
                channel_id, thread_ts, user_id, session_id, task_subtype,
            )
            return row["id"]
    except Exception as exc:
        log.warning("db.upsert_session_failed", error=str(exc))
        return None


async def log_message(
    session_fk: int | None,
    direction: str,
    content: str,
    slack_ts: str | None = None,
) -> None:
    """Log a user input or bot output message."""
    if not _pool or session_fk is None:
        return
    try:
        async with _pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO messages (session_fk, direction, content, slack_ts)
                VALUES ($1, $2, $3, $4)
                """,
                session_fk, direction, content, slack_ts,
            )
    except Exception as exc:
        log.warning("db.log_message_failed", error=str(exc))


async def log_execution(
    session_fk: int | None,
    prompt: str | None = None,
    duration_secs: float | None = None,
    num_turns: int | None = None,
    subtype: str | None = None,
    result_text: str | None = None,
    error: str | None = None,
    git_commits: list | None = None,
    pr_url: str | None = None,
) -> None:
    """Log an agent execution with metadata."""
    if not _pool or session_fk is None:
        return
    try:
        import json
        commits_json = json.dumps(git_commits) if git_commits else None
        async with _pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO agent_executions
                    (session_fk, prompt, duration_secs, num_turns, subtype,
                     result_text, error, git_commits, pr_url)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9)
                """,
                session_fk, prompt, duration_secs, num_turns, subtype,
                result_text, error, commits_json, pr_url,
            )
    except Exception as exc:
        log.warning("db.log_execution_failed", error=str(exc))

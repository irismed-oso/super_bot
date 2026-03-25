"""
SQLite memory storage for SuperBot with FTS5 full-text search.

Stores team knowledge (rules, facts, preferences) and enables
BM25-ranked search for auto-recall during conversations.

Uses aiosqlite for async compatibility with the existing event loop.
Gracefully degrades -- if DB is unreachable, logs a warning and continues.
"""

import re

import structlog

log = structlog.get_logger(__name__)

# Lazy import -- aiosqlite is optional; bot runs without it
_conn = None

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS memories (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    category    TEXT NOT NULL CHECK (category IN ('rule', 'fact', 'history', 'preference')),
    content     TEXT NOT NULL,
    source_user TEXT NOT NULL,
    source_channel TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    active      INTEGER NOT NULL DEFAULT 1
);

CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    content,
    content='memories',
    content_rowid='id',
    tokenize='porter unicode61'
);

CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
    INSERT INTO memories_fts(rowid, content) VALUES (new.id, new.content);
END;

CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, content) VALUES('delete', old.id, old.content);
END;

CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, content) VALUES('delete', old.id, old.content);
    INSERT INTO memories_fts(rowid, content) VALUES (new.id, new.content);
END;
"""

# Patterns for auto-categorization
_RULE_PATTERNS = re.compile(
    r"^(always |never |rule:|when .+ always |when .+ never )", re.IGNORECASE
)
_PREF_PATTERNS = re.compile(
    r"^(i prefer |use .+ instead|preference:)", re.IGNORECASE
)


def categorize(content: str) -> str:
    """Auto-categorize memory content based on keyword heuristics.

    Returns one of: 'rule', 'preference', 'fact'.
    ('history' is reserved for auto-capture in Phase 24.)
    """
    text = content.strip()
    if _RULE_PATTERNS.match(text):
        return "rule"
    if _PREF_PATTERNS.match(text):
        return "preference"
    return "fact"


async def init(db_path: str | None = None) -> bool:
    """Initialize SQLite connection, enable WAL mode, create schema.

    Returns True on success, False on failure.
    """
    global _conn
    if db_path is None:
        db_path = "./data/superbot_memory.db"

    try:
        import aiosqlite

        _conn = await aiosqlite.connect(db_path)
        _conn.row_factory = _dict_factory
        await _conn.execute("PRAGMA journal_mode=WAL")
        await _conn.execute("PRAGMA busy_timeout=5000")
        await _conn.executescript(SCHEMA_SQL)
        await _conn.commit()
        log.info("memory_store.initialized", db_path=db_path)
        return True
    except Exception as exc:
        log.warning("memory_store.init_failed", error=str(exc))
        _conn = None
        return False


def _dict_factory(cursor, row):
    """Convert sqlite3.Row to dict."""
    cols = [d[0] for d in cursor.description]
    return dict(zip(cols, row))


async def close():
    """Close the database connection."""
    global _conn
    if _conn:
        await _conn.close()
        _conn = None


async def store(
    content: str,
    category: str,
    source_user: str,
    source_channel: str | None = None,
) -> int | None:
    """Store a memory. Returns the row id or None on failure."""
    if _conn is None:
        return None
    try:
        cursor = await _conn.execute(
            "INSERT INTO memories (content, category, source_user, source_channel) "
            "VALUES (?, ?, ?, ?)",
            (content, category, source_user, source_channel),
        )
        await _conn.commit()
        return cursor.lastrowid
    except Exception as exc:
        log.warning("memory_store.store_failed", error=str(exc))
        return None


async def search(
    query: str, limit: int = 10, category: str | None = None
) -> list[dict]:
    """FTS5 search with BM25 ranking. Falls back to LIKE on FTS syntax errors."""
    if _conn is None:
        return []
    try:
        return await _fts_search(query, limit, category)
    except Exception:
        # FTS5 syntax error -- fall back to LIKE
        try:
            return await _like_search(query, limit, category)
        except Exception as exc:
            log.warning("memory_store.search_failed", error=str(exc))
            return []


async def _fts_search(
    query: str, limit: int, category: str | None
) -> list[dict]:
    """Execute FTS5 MATCH search."""
    if category:
        rows = await _conn.execute_fetchall(
            "SELECT m.id, m.category, m.content, m.source_user, m.created_at, rank "
            "FROM memories m "
            "JOIN memories_fts ON m.id = memories_fts.rowid "
            "WHERE memories_fts MATCH ? AND m.active = 1 AND m.category = ? "
            "ORDER BY rank LIMIT ?",
            (query, category, limit),
        )
    else:
        rows = await _conn.execute_fetchall(
            "SELECT m.id, m.category, m.content, m.source_user, m.created_at, rank "
            "FROM memories m "
            "JOIN memories_fts ON m.id = memories_fts.rowid "
            "WHERE memories_fts MATCH ? AND m.active = 1 "
            "ORDER BY rank LIMIT ?",
            (query, limit),
        )
    return rows


async def _like_search(
    query: str, limit: int, category: str | None
) -> list[dict]:
    """Fallback LIKE search when FTS5 query is malformed."""
    like_pattern = f"%{query}%"
    if category:
        rows = await _conn.execute_fetchall(
            "SELECT id, category, content, source_user, created_at, 0 as rank "
            "FROM memories "
            "WHERE content LIKE ? AND active = 1 AND category = ? "
            "ORDER BY created_at DESC LIMIT ?",
            (like_pattern, category, limit),
        )
    else:
        rows = await _conn.execute_fetchall(
            "SELECT id, category, content, source_user, created_at, 0 as rank "
            "FROM memories "
            "WHERE content LIKE ? AND active = 1 "
            "ORDER BY created_at DESC LIMIT ?",
            (like_pattern, limit),
        )
    return rows


async def deactivate(memory_id: int) -> bool:
    """Soft-delete a memory by setting active = 0. Returns True if a row was affected."""
    if _conn is None:
        return False
    try:
        cursor = await _conn.execute(
            "UPDATE memories SET active = 0 WHERE id = ? AND active = 1",
            (memory_id,),
        )
        await _conn.commit()
        return cursor.rowcount > 0
    except Exception as exc:
        log.warning("memory_store.deactivate_failed", error=str(exc))
        return False


async def list_all(
    category: str | None = None, limit: int = 50
) -> list[dict]:
    """List all active memories, optionally filtered by category."""
    if _conn is None:
        return []
    try:
        if category:
            rows = await _conn.execute_fetchall(
                "SELECT id, category, content, source_user, source_channel, created_at "
                "FROM memories WHERE active = 1 AND category = ? "
                "ORDER BY created_at DESC LIMIT ?",
                (category, limit),
            )
        else:
            rows = await _conn.execute_fetchall(
                "SELECT id, category, content, source_user, source_channel, created_at "
                "FROM memories WHERE active = 1 "
                "ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )
        return rows
    except Exception as exc:
        log.warning("memory_store.list_all_failed", error=str(exc))
        return []


async def get_by_id(memory_id: int) -> dict | None:
    """Get a single memory by id."""
    if _conn is None:
        return None
    try:
        rows = await _conn.execute_fetchall(
            "SELECT id, category, content, source_user, source_channel, created_at, active "
            "FROM memories WHERE id = ?",
            (memory_id,),
        )
        return rows[0] if rows else None
    except Exception as exc:
        log.warning("memory_store.get_by_id_failed", error=str(exc))
        return None

#!/usr/bin/env python3
"""
Dump a SuperBot agent session transcript from the `superbot` Postgres DB.

Usage:
    python scripts/query_agent_log.py --thread-ts 1712000000.123456 --channel C08QJGAN6US
    python scripts/query_agent_log.py --session <sdk_session_id>
    python scripts/query_agent_log.py --list-recent 10

Designed so another AI agent can be told:
    "check the SuperBot log for thread_ts=T channel=C, run
     python scripts/query_agent_log.py --thread-ts T --channel C"
and get a reconstructed trace of prompt, tool calls, tool results, and final reply.

Reads DATABASE_URL from SUPERBOT_DATABASE_URL env var, falling back to
postgresql://hanjing@localhost:5432/superbot (same default as bot/db.py).
"""

import argparse
import asyncio
import json
import os
import sys

DATABASE_URL = os.environ.get(
    "SUPERBOT_DATABASE_URL",
    "postgresql://hanjing@localhost:5432/superbot",
)


async def _connect():
    import asyncpg
    return await asyncpg.connect(DATABASE_URL)


async def _resolve_session(conn, *, thread_ts, channel, sdk_session):
    if sdk_session:
        row = await conn.fetchrow(
            "SELECT id, channel_id, thread_ts, user_id, session_id, created_at "
            "FROM sessions WHERE session_id = $1 ORDER BY created_at DESC LIMIT 1",
            sdk_session,
        )
    else:
        row = await conn.fetchrow(
            "SELECT id, channel_id, thread_ts, user_id, session_id, created_at "
            "FROM sessions WHERE channel_id = $1 AND thread_ts = $2",
            channel, thread_ts,
        )
    return row


async def _dump(conn, session_row):
    print(f"Session #{session_row['id']}")
    print(f"  channel    {session_row['channel_id']}")
    print(f"  thread_ts  {session_row['thread_ts']}")
    print(f"  user       {session_row['user_id']}")
    print(f"  sdk_id     {session_row['session_id']}")
    print(f"  created    {session_row['created_at']}")
    print()

    msgs = await conn.fetch(
        "SELECT direction, content, slack_ts, created_at FROM messages "
        "WHERE session_fk = $1 ORDER BY id",
        session_row["id"],
    )
    print(f"--- Messages ({len(msgs)}) ---")
    for m in msgs:
        label = "USER" if m["direction"] == "user_input" else "BOT "
        print(f"[{m['created_at']:%H:%M:%S}] {label}: {m['content'][:500]}")
    print()

    execs = await conn.fetch(
        "SELECT duration_secs, num_turns, subtype, error, pr_url, created_at "
        "FROM agent_executions WHERE session_fk = $1 ORDER BY id",
        session_row["id"],
    )
    print(f"--- Executions ({len(execs)}) ---")
    for e in execs:
        print(
            f"[{e['created_at']:%H:%M:%S}] subtype={e['subtype']} "
            f"turns={e['num_turns']} duration={e['duration_secs']}s"
            + (f" pr={e['pr_url']}" if e["pr_url"] else "")
            + (f" ERROR: {e['error'][:300]}" if e["error"] else "")
        )
    print()

    events = await conn.fetch(
        "SELECT turn_index, event_type, tool_name, tool_use_id, payload, created_at "
        "FROM agent_events WHERE session_fk = $1 ORDER BY id",
        session_row["id"],
    )
    print(f"--- Agent Events ({len(events)}) ---")
    for ev in events:
        payload = json.loads(ev["payload"]) if ev["payload"] else {}
        ts = ev["created_at"].strftime("%H:%M:%S")
        turn = ev["turn_index"]
        t = ev["event_type"]
        if t == "text":
            text = (payload.get("text") or "").strip()
            print(f"[{ts}] turn {turn} TEXT: {text[:800]}")
        elif t == "tool_use":
            inp = payload.get("input", {})
            preview = json.dumps(inp)[:300]
            print(f"[{ts}] turn {turn} TOOL_USE {ev['tool_name']}: {preview}")
        elif t == "tool_result":
            out = (payload.get("output") or "")[:500]
            err = " (is_error)" if payload.get("is_error") else ""
            print(f"[{ts}] turn {turn} TOOL_RESULT{err}: {out}")
        elif t == "result":
            print(
                f"[{ts}] turn {turn} RESULT subtype={payload.get('subtype')} "
                f"turns={payload.get('num_turns')}"
            )


async def _list_recent(conn, n):
    rows = await conn.fetch(
        """
        SELECT s.id, s.channel_id, s.thread_ts, s.user_id, s.created_at,
               (SELECT subtype FROM agent_executions
                WHERE session_fk = s.id ORDER BY id DESC LIMIT 1) AS last_subtype,
               (SELECT content FROM messages
                WHERE session_fk = s.id AND direction = 'user_input'
                ORDER BY id LIMIT 1) AS first_prompt
        FROM sessions s
        ORDER BY s.created_at DESC
        LIMIT $1
        """,
        n,
    )
    print(f"{'created':<20} {'channel':<12} {'thread_ts':<18} {'subtype':<16} prompt")
    for r in rows:
        prompt = (r["first_prompt"] or "").replace("\n", " ")[:60]
        print(
            f"{r['created_at']:%Y-%m-%d %H:%M:%S}  {r['channel_id']:<12} "
            f"{r['thread_ts']:<18} {str(r['last_subtype']):<16} {prompt}"
        )


async def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--thread-ts", help="Slack thread ts")
    p.add_argument("--channel", help="Slack channel id (required with --thread-ts)")
    p.add_argument("--session", help="Claude SDK session_id")
    p.add_argument("--list-recent", type=int, metavar="N", help="List N most recent sessions")
    args = p.parse_args()

    conn = await _connect()
    try:
        if args.list_recent:
            await _list_recent(conn, args.list_recent)
            return

        if args.session:
            row = await _resolve_session(conn, thread_ts=None, channel=None, sdk_session=args.session)
        elif args.thread_ts and args.channel:
            row = await _resolve_session(conn, thread_ts=args.thread_ts, channel=args.channel, sdk_session=None)
        else:
            p.error("pass --session, or --thread-ts + --channel, or --list-recent")

        if row is None:
            print("No session found.", file=sys.stderr)
            sys.exit(1)

        await _dump(conn, row)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())

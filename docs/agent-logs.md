# SuperBot Agent Logs — Guide for AI Agents

Every SuperBot run is persisted to a local Postgres DB so that other AI agents (or humans) can reconstruct what happened. Use this doc when you're asked to debug a SuperBot run, improve it, or hand off a run to another agent for analysis.

## TL;DR

```bash
# List the 10 most recent runs
python scripts/query_agent_log.py --list-recent 10

# Full transcript for one Slack thread
python scripts/query_agent_log.py --thread-ts 1712000000.123456 --channel C08QJGAN6US

# Look up by Claude SDK session id
python scripts/query_agent_log.py --session abc-123-def
```

**On `superbot-vm`**, run as the `bot` user with the VM's socket-based connection string:

```bash
sudo -u bot bash -c 'cd /home/bot/super_bot && SUPERBOT_DATABASE_URL=postgresql:///superbot .venv/bin/python scripts/query_agent_log.py --list-recent 5'
```

The script prints: session header, Slack-facing messages, per-run execution metadata, and the full per-turn event trail (text, tool_use, tool_result, result).

## How to pass a session to another agent

The **stable shared identifier** is the Slack `(channel, thread_ts)` pair. Send it like:

> Agent, investigate SuperBot thread `C08QJGAN6US / 1712000000.123456`. Run `python scripts/query_agent_log.py --thread-ts 1712000000.123456 --channel C08QJGAN6US` on the host where the `superbot` DB lives (localhost by default, see `SUPERBOT_DATABASE_URL`).

If you only have the Claude SDK `session_id` (printed in `agent.run_end` journalctl logs), use `--session` instead.

## Connection

- **Laptop default**: `postgresql://hanjing@localhost:5432/superbot` (TCP, role `hanjing`, no password — matches the local dev setup).
- **On `superbot-vm`**: the bot runs as user `bot` against a unix socket. `/home/bot/.env` sets `SUPERBOT_DATABASE_URL=postgresql:///superbot` and that's what you need to pass through when invoking the CLI — running `query_agent_log.py` without it will fail with `password authentication failed for user "hanjing"` because asyncpg falls back to the laptop default.
- Override anywhere with the `SUPERBOT_DATABASE_URL` env var.
- The DB is created lazily by `bot/db.py` at bot startup (`db.init`). If it's missing locally, run the bot once or create it manually: `createdb -U hanjing superbot`.

## Schema

Defined in `bot/db.py` (`SCHEMA_SQL`). Four tables, all keyed on `sessions.id`:

### `sessions` — one row per Slack thread
| Column | Notes |
|---|---|
| `id` | PK (used as `session_fk` everywhere else) |
| `channel_id`, `thread_ts` | Slack identifiers, UNIQUE together |
| `user_id` | Slack user who started the thread |
| `session_id` | Claude SDK session id (NULL until first run completes) |
| `created_at` | |

### `messages` — Slack-level I/O
| Column | Notes |
|---|---|
| `direction` | `'user_input'` or `'bot_output'` |
| `content` | Raw text (prompt after mention-strip, or final reply) |
| `slack_ts` | Source Slack message ts, when known |

### `agent_executions` — one row per agent run (roughly one per prompt)
| Column | Notes |
|---|---|
| `prompt`, `result_text`, `error` | |
| `duration_secs`, `num_turns`, `subtype` | `subtype ∈ {'success','error_timeout','error_internal','error_max_turns',...}` |
| `git_commits` JSONB, `pr_url` | From `bot.git_activity` |

### `agent_events` — per-turn trace (new, read this one first when debugging)
| Column | Notes |
|---|---|
| `turn_index` | Increments once per AssistantMessage (1-based) |
| `event_type` | `'text'`, `'tool_use'`, `'tool_result'`, `'result'` |
| `tool_name` | e.g. `Read`, `Bash`, `Edit` (tool_use rows only) |
| `tool_use_id` | Ties a `tool_use` to its matching `tool_result` |
| `payload` JSONB | `{"text": ...}` / `{"input": ...}` / `{"output": ..., "is_error": bool}` / `{"subtype": ..., "num_turns": ..., "result": ...}` |

Payload strings are truncated at 10_000 chars each (see `PAYLOAD_MAX_CHARS` in `bot/db.py`). A tool that dumps megabytes won't bloat the DB; you'll see a `...[truncated N chars]` suffix.

## Useful SQL

```sql
-- Runs that errored in the last 24h
SELECT s.channel_id, s.thread_ts, e.subtype, e.error, e.created_at
FROM agent_executions e
JOIN sessions s ON s.id = e.session_fk
WHERE e.subtype LIKE 'error%'
  AND e.created_at > now() - interval '1 day'
ORDER BY e.created_at DESC;

-- Tool usage histogram for a session
SELECT tool_name, count(*)
FROM agent_events
WHERE session_fk = $1 AND event_type = 'tool_use'
GROUP BY tool_name
ORDER BY 2 DESC;

-- Most recent failing tool_result across all runs
SELECT s.thread_ts, ev.turn_index, ev.tool_name, ev.payload->>'output' AS output
FROM agent_events ev
JOIN sessions s ON s.id = ev.session_fk
WHERE ev.event_type = 'tool_result'
  AND (ev.payload->>'is_error')::boolean = true
ORDER BY ev.created_at DESC
LIMIT 20;

-- Reconstruct one run's full trace in order
SELECT turn_index, event_type, tool_name, payload
FROM agent_events
WHERE session_fk = $1
ORDER BY id;
```

## Reading a trace — what to look for

When another agent hands you a failed run, walk the events in order and check:

1. **First `result` row** — `subtype` tells you *how* it ended. `error_internal` with empty `error` field usually means the underlying `claude` CLI died (auth, missing binary, MCP startup). Cross-reference `agent_executions.error` and journalctl (`agent.generic_error` / `agent.process_error`).
2. **Last few `tool_use` / `tool_result` pairs** — `is_error=true` rows are the concrete failures. Look for repeated `Read` on a non-existent path, `Bash` with non-zero stdout, etc.
3. **`text` rows** — the agent's own narration. If these stop abruptly, the run probably timed out mid-turn.
4. **`turn_index` jumps** — if execution ended at `turn_index=25` with no success result, you hit `MAX_TURNS` (see `bot/agent.py`).

## Graceful degradation

All `db.log_*` helpers swallow exceptions and log a warning. If the DB is down, the bot keeps running and you just lose the event trail for those runs. Check journalctl for `db.log_event_failed` or `db.init_failed` to see if logging is healthy.

## Where this wires up

- `bot/db.py` — schema, pool, `log_event` helper
- `bot/event_logger.py` — builds the per-message callback
- `bot/handlers.py` — chains event logger alongside the progress callback
- `bot/agent.py` — forwards `UserMessage` and `ResultMessage` to `on_message` so tool results and the final result reach the logger

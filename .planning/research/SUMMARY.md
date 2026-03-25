# Project Research Summary

**Project:** SuperBot v1.9 Persistent Memory
**Domain:** Persistent memory system for async Slack bot + Claude Agent SDK
**Researched:** 2026-03-25
**Confidence:** HIGH

## Executive Summary

SuperBot v1.9 adds a persistent memory layer to an existing production Slack bot that runs Claude Agent SDK on a resource-constrained GCP e2-small VM (2 GB RAM). The established approach for this class of system is a four-category memory taxonomy (rules, facts, history, preferences) with keyword-based retrieval and explicit user management commands. The recommended implementation is SQLite with FTS5 full-text search via a single `aiosqlite` connection — the only new dependency. This approach is correct given the scale (< 1,000 memories, team of 2-4 people) and VM constraints that rule out embedding models or vector databases entirely.

The core value of the system comes from two integration points: auto-recall, which injects the top 5-8 relevant memories into every agent prompt at session start; and post-session thread scanning, which uses a lightweight Claude call to extract memorable facts from completed threads automatically. Both integrate via existing hooks in `handlers.py` (`_build_prompt()` for recall, `result_cb()` for scanning), and neither requires changes to the agent pipeline, queue manager, or any other core component.

The primary risks are operational, not architectural. SQLite concurrent writes in an asyncio context require a single shared connection with WAL mode and a busy timeout — without this, memory writes silently fail under load. Auto-recall must be capped at 5-8 memories with a hard token budget, or prompt bloat will degrade agent quality as the store grows. Thread scanning must run as a fire-and-forget background task via `asyncio.create_task()`, not awaited inline, or it blocks the queue for 5-10 seconds per session. All three pitfalls have clear, simple prevention strategies.

## Key Findings

### Recommended Stack

The entire v1.9 memory system requires exactly **one new package**: `aiosqlite >= 0.21.0`. Everything else — SQLite FTS5, the Slack `conversations.replies` API, and the Claude agent SDK for extraction — is already installed or bundled with Python 3.10. This is deliberate: the VM's 2 GB RAM constraint eliminates sentence-transformers, PyTorch, vector databases (Chroma, LanceDB), and any embedding API that adds per-query latency. SQLite FTS5 with BM25 ranking is sufficient for the expected corpus size and has sub-millisecond query latency on up to 100K rows.

See [STACK.md](STACK.md) for the full technology decisions, alternatives considered, and schema design.

**Core technologies:**
- `aiosqlite >= 0.21.0`: Async SQLite access — wraps stdlib sqlite3 in a thread, compatible with existing asyncio event loop, zero compilation, MIT license
- SQLite FTS5 (bundled): Full-text search with BM25 ranking — built into Python 3.10's sqlite3, zero RAM overhead, no extensions to install
- Slack `conversations.replies` API (existing): Thread message retrieval — already available via `client.conversations_replies()`, no new OAuth scopes needed, internal app exempt from May 2025 rate limit restrictions
- Claude agent SDK (existing): Memory extraction — single lightweight prompt per thread, higher quality than any NLP library, no new dependency

**What NOT to add:** sentence-transformers, PyTorch, sqlite-vec, voyageai SDK, chromadb/lancedb, spaCy/NLTK, SQLAlchemy, or new Slack OAuth scopes.

### Expected Features

See [FEATURES.md](FEATURES.md) for the full feature inventory, dependency graph, prioritization matrix, and competitor analysis.

**Must have (table stakes — v1.9 launch):**
- SQLite schema with `memories` table + FTS5 virtual table — foundation everything depends on
- Memory CRUD module (`bot/memory_store.py`) — async store, search, deactivate, list
- "Remember X" explicit command — regex fast-path, auto-categorizes content as rule/fact/preference
- "What do you know about X" / "recall X" query command — FTS5 search, formatted Slack output
- "Forget X" command with confirmation on multi-match — soft-delete, ID-based or keyword-based
- "List memories" command with optional category filter — browsable team knowledge
- Auto-recall injection into `_build_prompt()` — top 5-8 relevant memories prepended to every agent prompt; this is the feature that makes the memory system visible and valuable

**Should have (v1.9.x, after core loop is validated by the team):**
- Automatic thread scanning — post-session Claude extraction of memorable facts; add after manual memory proves the store/recall loop works reliably
- Task history auto-capture — one-line session summary stored as `task_history` category
- Memory deduplication on insert — FTS5 near-duplicate check before storing; add once ~50+ memories exist

**Defer (v2+):**
- Embedding-based semantic search — only if FTS5 recall quality proves insufficient at scale
- Memory consolidation — only if memory count exceeds ~500 and retrieval quality degrades
- Cross-repo memory — requires multi-repo bot support first
- Web UI dashboard — out of scope; Slack is the interface per PROJECT.md

### Architecture Approach

The memory system adds 3 new modules and modifies 3 existing ones. It does not touch the agent pipeline, queue manager, heartbeat, progress, session map, or PostgreSQL logging. The build order is dependency-driven: `memory_store.py` first (foundation, testable in isolation), then fast command wiring and startup init, then `memory_recall.py` + prompt injection, then `thread_scanner.py` + result callback wiring. Each phase delivers testable, immediately useful functionality rather than requiring the entire system to be built before anything works.

See [ARCHITECTURE.md](ARCHITECTURE.md) for full data flow diagrams, component API surfaces, anti-patterns, and scalability analysis.

**Major components:**
1. `bot/memory_store.py` (NEW) — SQLite CRUD + FTS5 search via aiosqlite; single shared connection; WAL mode; graceful degradation matching `db.py` pattern
2. `bot/memory_recall.py` (NEW) — builds recall block from user prompt; always includes rules, fills remaining slots with FTS5 keyword matches; caps at 5-8 memories; compact bulleted format
3. `bot/thread_scanner.py` (NEW) — post-session hook; fetches thread via `conversations.replies`; lightweight Claude call for extraction; deduplicates before storing; runs as background task via `asyncio.create_task()`
4. `bot/fast_commands.py` (MODIFIED) — adds remember/recall/forget/list memory commands; placed BEFORE all existing patterns; anchored prefix regexes prevent collision
5. `bot/handlers.py` (MODIFIED) — wires recall into `_build_prompt()` and thread scan into `result_cb()`; recall runs only for agent sessions, never fast-path
6. `bot/app.py` (MODIFIED) — calls `memory_store.init()` at startup (1 line change)

### Critical Pitfalls

See [PITFALLS.md](PITFALLS.md) for the full pitfall inventory with detection signals and phase-specific warnings.

1. **SQLite database locked errors** — Use a single global `aiosqlite` connection shared across all coroutines. Enable `PRAGMA journal_mode=WAL` and `PRAGMA busy_timeout=5000` at init. Without this, concurrent writes from thread scanner and fast-path commands silently fail and users lose memories they confirmed were stored.

2. **Prompt bloat from uncapped auto-recall** — Hard cap at 5-8 memories per prompt with a 500-token budget. Always include all `rule` category memories, fill remaining slots by FTS5 rank. At 100+ memories, uncapped recall injects 2,000+ tokens per session and buries critical rules among trivia.

3. **Thread scanning extracts noise and contradictions** — Use a conservative extraction prompt that requires explicit directives only ("always/never/the rule is"). Deduplicate on insert via FTS5. Never extract from bot's own messages. The store becomes untrustworthy quickly if speculative or corrected statements are stored as facts.

4. **Thread scanning blocks the queue** — Run `thread_scanner.scan_thread()` via `asyncio.create_task()`, not awaited in `result_cb()`. A Slack API call + Claude API call takes 5-10 seconds; blocking the result callback delays the next queued task by that amount.

5. **Memory command regex collisions** — Place all memory commands BEFORE existing fast-path patterns in `FAST_COMMANDS`. Use anchored prefix regexes (`^\s*remember\b`, `^\s*forget\b`). Without this, "remember to crawl EyeMed" triggers the crawl handler, and "forget the crawl schedule" triggers a crawl.

## Implications for Roadmap

Based on research, the dependency graph and risk profile suggest four phases:

### Phase 1: SQLite Foundation + Manual Memory CRUD

**Rationale:** All other features depend on the database layer. Building memory CRUD commands first gives the team immediate ability to manually populate memories and verify the store/recall loop before any automation is added. This mirrors how `db.py` was built first as the foundation for PostgreSQL logging.

**Delivers:** Working memory database, explicit remember/recall/forget/list commands, team can start building institutional knowledge on day one.

**Addresses:** SQLite schema + FTS5, `memory_store.py` CRUD module, all four fast-path memory commands (must-have table stakes).

**Avoids:** SQLite database locked errors (Pitfall 1 — single connection, WAL mode, busy timeout established at foundation). Memory command regex collisions (Pitfall 5 — correct placement and anchored regexes built from the start). Ambiguous forget deletes (Pitfall 9 — confirmation on multi-match, soft-delete only).

**Research flag:** Standard patterns — aiosqlite module-level singleton matches `db.py` exactly. Fast-path commands match existing `fast_commands.py` pattern. No deeper research needed.

### Phase 2: Auto-Recall Injection

**Rationale:** This is the core value of persistent memory — memories stored in Phase 1 now automatically influence agent behavior. Builds on the `memory_store.py` retrieval API from Phase 1. Must be wired and validated before thread scanning (Phase 3) starts auto-populating the store.

**Delivers:** Agent sessions are enriched with relevant memories from the store without user intervention. The team can immediately verify whether stored memories improve agent behavior.

**Addresses:** Auto-recall fast-path integration, `memory_recall.py` module, `handlers.py` `_build_prompt()` modification, memory source attribution in formatted output.

**Avoids:** Prompt bloat (Pitfall 2 — hard cap and token budget built into `memory_recall.py` from the start). Fast-path latency regression (Pitfall 4 — recall runs AFTER fast-path check, never for fast-path commands). Irrelevant recall results (Pitfall 8 — category-weighted search, phrase queries, tested with real data from Phase 1's manually added memories).

**Research flag:** Standard patterns for FTS5 integration and prompt injection. Recall quality tuning may need iteration after deployment with real team data — treat initial cap and category weighting as configurable parameters rather than hardcoded values.

### Phase 3: Post-Session Thread Scanning

**Rationale:** Automatic extraction requires the storage layer (Phase 1) and a functioning recall system (Phase 2) to validate that what gets extracted is actually useful. Building this last means the team can judge extraction quality against a store that already has known-good manually-added memories for comparison. This is the highest-complexity feature and benefits from the base system being stable first.

**Delivers:** Memories accumulate organically from every bot thread without requiring users to explicitly "remember" things. Task history auto-capture as a side effect.

**Addresses:** `thread_scanner.py`, `result_cb()` hook in `handlers.py`, lightweight Claude extraction call, deduplication on insert, task history auto-capture.

**Avoids:** Thread scanning blocks queue (Pitfall 10 — `asyncio.create_task()` mandatory). Noise and contradictions extracted (Pitfall 3 — conservative extraction prompt, dedup, skip bot messages, skip fast-path threads). Slack rate limits (Pitfall 6 — lazy per-session scanning, not batch, with 429 backoff).

**Research flag:** The extraction prompt quality is the key unknown. No established template for conservative-vs-permissive memory extraction from Slack threads exists in the research. Plan to treat the extraction prompt as a tunable parameter. Consider running Phase 3 in shadow mode (extract but do not store, log what would have been stored) for the first week to validate quality before auto-storing.

### Phase 4: Hygiene + Operational Hardening

**Rationale:** Once the full memory loop (Phases 1-3) is running in production, operational concerns become primary. DB file size growth on a small VM, memory deduplication to prevent store pollution, and periodic VACUUM need scheduled maintenance hooks.

**Delivers:** Sustainable memory system that does not degrade over time. Task history TTL (90-day auto-delete). File size monitoring. Periodic VACUUM via daily digest loop. Staleness markers.

**Addresses:** Task history retention policy, periodic VACUUM, file size monitoring, memory deduplication on insert, startup integrity check, daily backup.

**Avoids:** DB file growth on 10 GB boot disk (Pitfall 7). Memory store pollution from duplicates (Pitfall 3 dedup component). SQLite WAL file corruption on unclean shutdown (Pitfall 12 — startup integrity check, daily backup).

**Research flag:** Standard patterns — SQLite maintenance is thoroughly documented. Daily digest loop already exists in the codebase as the scheduling hook. No deeper research needed.

### Phase Ordering Rationale

- Phase 1 before everything: database layer is the foundation; analogous to `db.py` ordering in v1.7 development. Gives the team something immediately useful.
- Phase 2 before Phase 3: auto-recall must be working and validated before the store starts growing via auto-extraction. Without Phase 2, there is no way to verify Phase 3 extraction quality produces actually-useful memories.
- Phase 3 before Phase 4: hygiene concerns (dedup, retention) only matter once the store has meaningful volume; optimizing before Phase 3 is premature.
- Deduplication split across phases: basic soft-delete in Phase 1, FTS5-based near-duplicate check in Phase 3 (insert path), dedup command and batch cleanup in Phase 4.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 3 (Thread Scanning):** Extraction prompt quality is the primary risk. The research identifies what to avoid (speculative statements, bot messages, corrections) but does not provide a proven prompt formula. Design the shadow-mode validation gate and treat the prompt as a configurable parameter from day one.

Phases with standard patterns (skip research-phase):
- **Phase 1:** aiosqlite + FTS5 schema is fully documented in STACK.md and ARCHITECTURE.md with exact schema and code samples. Fast-path command pattern matches existing `fast_commands.py` exactly.
- **Phase 2:** `_build_prompt()` injection point is identified. Recall logic and FTS5 query patterns are specified. Standard integration work.
- **Phase 4:** SQLite maintenance (VACUUM, integrity_check, WAL checkpointing) is thoroughly documented in SQLite official docs. Daily digest scheduling hook already exists.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | One new package (aiosqlite). All other decisions validated against existing codebase and official documentation. FTS5 availability on Python 3.10 verified via test script in STACK.md. VM constraint confirmed via terraform/variables.tf. |
| Features | HIGH | Feature taxonomy sourced from Mem0, OpenClaw, ZeroClaw. MVP vs v2 boundary is opinionated but defensible for a 2-4 person team at < 1,000 memory scale. |
| Architecture | HIGH | All integration points validated against actual codebase files (handlers.py, fast_commands.py, db.py, queue_manager.py). Component boundaries are precise, not speculative. Build order is dependency-driven and correct. |
| Pitfalls | HIGH | Top 5 pitfalls sourced from SQLite official docs, aiosqlite architecture, Slack API docs, and direct codebase analysis. Each has concrete, implementable prevention strategies with detection signals. |

**Overall confidence:** HIGH

### Gaps to Address

- **Extraction prompt formula (Phase 3):** No proven template for conservative Slack thread extraction exists in the research. The failure modes are documented but the optimal prompt content needs empirical iteration. Handle during Phase 3 planning by designing a shadow-mode validation gate before going live with auto-storage.
- **FTS5 recall quality on domain-specific jargon:** FTS5 may surface irrelevant results on short, jargon-heavy queries (e.g., "DME", "VSP 835"). Pitfall 8 documents a mitigation strategy (phrase queries, category weighting, recency) but quality will need measurement against real team data after Phase 2 deploys. The upgrade path to embeddings is documented in STACK.md and is non-breaking.
- **Memory count at which recall quality degrades:** Research conservatively estimates FTS5 is sufficient for < 1,000 entries but does not identify a precise quality threshold. Monitor via team feedback; trigger the embedding upgrade path if the team reports missing relevant memories despite them existing in the store.

## Sources

### Primary (HIGH confidence)
- Existing codebase: `bot/db.py`, `bot/handlers.py`, `bot/fast_commands.py`, `bot/agent.py`, `bot/queue_manager.py`, `bot/app.py` — primary integration point analysis and pattern verification
- [SQLite FTS5 Extension](https://sqlite.org/fts5.html) — schema, triggers, BM25 ranking, phrase queries, Porter tokenization
- [aiosqlite GitHub](https://github.com/omnilib/aiosqlite) — async SQLite, single-thread-per-connection architecture, v0.21.0
- [SQLite WAL mode](https://www.sqlite.org/wal.html) — concurrent read/write behavior, crash recovery
- [Slack conversations.replies API](https://api.slack.com/methods/conversations.replies) — rate limits, pagination, message structure
- [Slack rate limit changes for non-Marketplace apps (May 2025)](https://docs.slack.dev/changelog/2025/05/29/rate-limit-changes-for-non-marketplace-apps/) — internal app exemption confirmed
- `terraform/variables.tf` — e2-small VM specs (2 GB RAM) confirmed

### Secondary (MEDIUM confidence)
- [Mem0 Memory Types](https://docs.mem0.ai/core-concepts/memory-types) — four-layer taxonomy, ADD/UPDATE/DELETE/NOOP operations
- [Mem0 Architecture Paper](https://arxiv.org/abs/2504.19413) — fact extraction patterns, 91% latency reduction vs full-context
- [OpenClaw Memory Concepts](https://docs.openclaw.ai/concepts/memory) — BM25 + vector hybrid, pre-compaction flush pattern
- [ZeroClaw Documentation](https://zeroclaws.io/docs/) — SQLite + vector search, CLI memory management
- [SQLite FTS5 vs Vector Hybrid Search](https://alexgarcia.xyz/blog/2024/sqlite-vec-hybrid-search/index.html) — performance characteristics for small datasets
- [Piccolo ORM: SQLite and asyncio effectively](https://piccolo-orm.readthedocs.io/en/1.3.2/piccolo/tutorials/using_sqlite_and_asyncio_effectively.html) — WAL, busy_timeout, IMMEDIATE transactions
- [Memory Engineering for AI Agents (Medium)](https://medium.com/@mjgmario/memory-engineering-for-ai-agents-how-to-build-real-long-term-memory-and-avoid-production-1d4e5266595c) — context bloat, packaging vs ranking
- [sqlite-vec PyPI](https://pypi.org/project/sqlite-vec/) — v0.1.7, documented as upgrade path if FTS5 proves insufficient

### Tertiary (LOW confidence)
- [Memoria Framework](https://arxiv.org/html/2512.12686v1) — session summarization + knowledge graph (academic, not implemented)
- [SimpleMem](https://github.com/aiming-lab/SimpleMem) — three-stage compression/synthesis/retrieval pipeline (paper only)

---
*Research completed: 2026-03-25*
*Ready for roadmap: yes*

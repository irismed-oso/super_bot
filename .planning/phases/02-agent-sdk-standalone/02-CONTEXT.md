# Phase 2: Agent SDK Standalone - Context

**Gathered:** 2026-03-19
**Status:** Ready for planning

<domain>
## Phase Boundary

Build the Claude Agent SDK wrapper that can be invoked from a standalone Python script on the VM, with session resumption, concurrent request serialization (queue), and timeout/max-turns handling. Validated in isolation before Slack wires to it in Phase 3. No Slack integration in this phase — test with a CLI harness.

</domain>

<decisions>
## Implementation Decisions

### Session Continuity
- Sessions are keyed by Slack thread_ts — same thread = same Claude session
- Top-level @mention (no thread) always starts a new session
- Sessions never expire — resume anytime by replying in the thread
- On resume: pass summary of old context + full recent context (not full history) to manage token budget
- Session-to-thread mapping persisted to survive service restarts

### Safety Limits
- 10-minute wall-clock timeout per task — kill process if exceeded
- 25 max conversation turns per task — terminate cleanly if hit
- On timeout or max-turns: kill the session, post what was completed so far, offer "reply to continue where I left off"
- Full tool access — no --allowedTools or --disallowedTools restrictions. Full autonomy.
- Use --dangerously-skip-permissions or equivalent for non-interactive execution

### Concurrency Model
- FIFO task queue with max depth of 3
- When queue is full (3 pending): reject with status showing what's running and queued
- When a queued task starts running: notify the original Slack thread ("Your task is now running.")
- /cancel kills the running task only — queue advances to next. Does NOT clear pending tasks.
- No priority system — first come, first served

### Agent Output Format
- Post raw Claude output as-is — natural language, minimal post-processing
- Long output (>4000 chars): split into multiple Slack messages in the thread
- Code and diffs always wrapped in Slack code blocks (``` formatting)
- Errors: full context — error message, relevant stack trace, what was attempted
- No structured summary templates — trust Claude's natural output

### Claude's Discretion
- Session storage mechanism (file-based, SQLite, etc.)
- Queue implementation details (asyncio.Queue, etc.)
- How to extract and summarize prior session context for resumption
- Exact output splitting strategy for long messages
- How to detect and format code blocks in Claude's output

</decisions>

<specifics>
## Specific Ideas

- The standalone test harness should simulate the Slack interface: pass a prompt, get output, pass a follow-up with a "thread_ts" to test resumption
- The queue should be observable — /sb-status in Phase 3 will read queue state
- When a task is killed by timeout, any partial git changes (uncommitted) should be cleaned up or stashed, not left dirty

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 02-agent-sdk-standalone*
*Context gathered: 2026-03-19*

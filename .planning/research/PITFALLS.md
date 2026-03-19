# Pitfalls Research

**Domain:** Slack-to-Claude-Code autonomous agent on GCP VM
**Researched:** 2026-03-18
**Confidence:** HIGH (critical pitfalls verified across official docs and multiple community sources)

---

## Critical Pitfalls

### Pitfall 1: Slack 3-Second Timeout Kills Long-Running Agent Sessions

**What goes wrong:**
Slack requires an HTTP 200 acknowledgment within 3 seconds of receiving an event. Claude Code sessions running real tasks take 30 seconds to several minutes. If your bridge doesn't ack immediately and instead waits for Claude to finish, Slack times out and retries the event — triggering duplicate Claude Code sessions for the same request.

**Why it happens:**
Developers build the simplest path: receive event → run Claude → return result. This works for instant responses but not for operations lasting more than 3 seconds, which is every real Claude Code task.

**How to avoid:**
Implement the mandatory two-phase pattern:
1. Immediately call `ack()` (or return HTTP 200) within 1 second of receiving the event
2. Hand off the Claude Code invocation to a background worker/thread
3. Post results back to Slack via `chat.postMessage` using `response_url` or the channel ID once complete

With Slack Bolt Python, use the lazy listener pattern: one function calls `ack()`, a separate `lazy` function does the actual work.

**Warning signs:**
- Slack logs show `operation_timeout` errors
- Users see the bot respond twice to the same message
- Event processing logs show the same `event_id` appearing multiple times

**Phase to address:**
Phase 1 (Slack bridge foundation) — must be correct from day one, not retrofitted.

---

### Pitfall 2: Duplicate Event Processing (No Deduplication)

**What goes wrong:**
Slack retries events when it doesn't receive a timely ack. If your bridge processes an event before the retry window, you can end up with two Claude Code sessions running the same task simultaneously — committing code twice, running scripts twice, posting duplicate results to Slack.

**Why it happens:**
Slack's retry behavior is correct behavior on Slack's side. The bug is that the receiving application doesn't track which events have already been processed. In-memory deduplication fails after process restarts or if you ever scale to multiple workers.

**How to avoid:**
Track processed `event_id` values in a persistent store (Redis SET NX with TTL, or a simple SQLite/PostgreSQL table with a unique constraint on `event_id`). For a single-VM deployment, Redis with a 10-minute TTL per event_id is the minimal correct solution. Check before processing: if the event_id is already claimed, return 200 immediately and do nothing.

**Warning signs:**
- Bot posts duplicate replies to the same message
- Git history shows the same commit appearing twice
- Logs show two Claude sessions with identical prompts starting within seconds of each other

**Phase to address:**
Phase 1 (Slack bridge foundation) — implement with deduplication from the start.

---

### Pitfall 3: Running Claude Code as Root / Without Credential Isolation

**What goes wrong:**
Running the Claude Code process as root, or as a user whose home directory contains production credentials (SSH keys to other servers, `.aws/credentials`, GitLab deploy tokens), means Claude Code has unrestricted access to exfiltrate or destroy those credentials. A prompt injection attack in a malicious file in the repo can trigger credential theft. CVE-2025-59536 and CVE-2026-21852 demonstrated that malicious `.claude/settings.json` files can redirect API traffic to attacker-controlled servers and steal the Anthropic API key.

**Why it happens:**
It's easiest to SSH into the VM as your own user and run Claude Code there. That user naturally has all your credentials. Developers don't think of the Claude Code process as an untrusted execution environment.

**How to avoid:**
- Create a dedicated `bot` OS user with no SSH keys, no cloud credentials, no `.aws/` directory
- Store all secrets (Anthropic API key, Slack bot token, GitLab access token) in GCP Secret Manager; inject at runtime via environment variables only
- Never run Claude Code as root — it is explicitly documented as a security violation
- Scope the GitLab access token used on the VM to only the `mic_transformer` repo with push access to non-protected branches only
- Deny Claude Code access to sensitive files via `settings.json` denylist: `~/.ssh/`, `~/.aws/`, `.env`

**Warning signs:**
- Claude Code process running as a user with SSH keys in `~/.ssh/`
- Anthropic API key stored in a `.env` file inside the repo
- Claude Code process has write access outside the `mic_transformer` repo directory

**Phase to address:**
Phase 1 (VM provisioning and security hardening) — before any other work begins.

---

### Pitfall 4: Context Window Exhaustion Mid-Task

**What goes wrong:**
Claude Code's context window is 200K tokens. For a codebase like mic_transformer (Flask, Prefect, multiple services), a single complex investigation that reads many files can exhaust the context window before the task completes. The session fails mid-execution, potentially leaving the repo in a partially modified state. Bug documented in GitHub issue #4722: users report exhaustion errors at what appears to be ~2% of expected usage due to system prompt overhead, tool call history, and file contents accumulating.

**Why it happens:**
Each turn in a multi-step task accumulates: system prompt (~10K tokens), CLAUDE.md contents, every file read, every bash output, every tool call result. A task that reads 20 files averaging 5K lines each consumes the context before doing any real work. The "30-50% more tokens in multi-turn sessions" effect compounds this.

**How to avoid:**
- Set `--max-turns` explicitly to prevent runaway sessions (start with 30, tune from there)
- Break large tasks into focused, single-purpose Claude invocations rather than one mega-session
- Design the bridge to detect context exhaustion errors and report them clearly to Slack rather than silently failing
- Instruct Claude (via system prompt or task preamble) to use targeted file reads rather than reading entire files when possible

**Warning signs:**
- Claude stops mid-task with "prompt is too long" error
- Tasks involving large codebases or many file reads fail consistently
- Session token usage spikes unexpectedly for "simple" requests

**Phase to address:**
Phase 2 (Claude Code integration) — design session management with this constraint in mind.

---

### Pitfall 5: Bot Infinite Loop (Responding to Own Messages)

**What goes wrong:**
The Slack bot posts a result message to the channel. That message triggers another `app_mention` or `message` event. The bridge processes it, starts another Claude Code session, and the loop continues until rate limits or manual intervention stop it.

**Why it happens:**
Developers subscribe to `message` events rather than `app_mention` events, or they subscribe to `app_mention` without filtering out bot-authored messages. Slack's event payload includes a `bot_id` field on messages from bots — failing to check this field is the single root cause.

**How to avoid:**
- Subscribe only to `app_mention` events, not generic `message` events
- In every event handler, check `event.bot_id` — if present, return 200 immediately without processing
- Check `event.subtype` — if it equals `bot_message`, skip
- Never `@mention` the bot in the bot's own response messages

**Warning signs:**
- Bot starts responding to its own response messages
- Slack rate limit errors appear in logs
- Token usage spikes dramatically with no user activity

**Phase to address:**
Phase 1 (Slack bridge foundation) — a filter that must exist before any event processing logic.

---

### Pitfall 6: Concurrent Claude Sessions Corrupting the Shared Repo

**What goes wrong:**
Two team members send requests to the bot simultaneously. Two Claude Code sessions start concurrently, both working in the same `mic_transformer` working directory. They race on file edits — one session's writes are overwritten by the other, or both sessions attempt to commit to the same branch at the same time. Git history becomes corrupted or force-pushes happen.

**Why it happens:**
There is one repo on the VM. Claude Code's write scope is confined to the working directory it was started in. If both sessions share that working directory, they share all files.

**How to avoid:**
- Queue incoming requests: process one Claude session at a time using a simple job queue (even a threading.Lock or asyncio.Queue suffices for a small team)
- For parallel work, use git worktrees: each task gets its own worktree (`git worktree add /home/bot/tasks/<task-id> -b task/<task-id>`), isolating file operations
- When a task is queued, notify the requesting user in Slack that their request is queued and will run after the current task completes

**Warning signs:**
- Git log shows merge conflicts or force-push events
- Files have garbled content mixing two tasks' changes
- Two Claude processes visible in `ps aux` simultaneously

**Phase to address:**
Phase 2 (Claude Code integration) — the queue/worktree strategy must be decided before connecting the Slack trigger.

---

### Pitfall 7: Missing `--output-format stream-json` Causes Process Hang

**What goes wrong:**
When invoking Claude Code with `-p` (headless/programmatic mode), the process can hang indefinitely when reading from stdin if output format isn't explicitly set. Documented in GitHub issue #7497: "Process Hangs Indefinitely When Reading InputStream from Claude Code Headless Execution." The bridge waits forever for Claude to finish, holding the Slack response connection open, eventually timing out with no result.

**Why it happens:**
Without explicit output format flags, Claude Code's output behavior in non-interactive mode is ambiguous. The process may wait for input it will never receive, or the bridge code may block on stdout/stderr in a way that deadlocks.

**How to avoid:**
Always invoke Claude Code with explicit flags for non-interactive use:
```bash
claude -p "task" \
  --output-format stream-json \
  --allowedTools "Read,Edit,Bash" \
  --max-turns 30
```
Set a process-level timeout (e.g., 10 minutes) in the bridge code independent of Claude's own flags. Kill the subprocess and notify Slack if the timeout is exceeded.

**Warning signs:**
- Claude invocations never return; bridge worker threads accumulate
- No output or logs from Claude for minutes on end
- VM CPU is idle but the bridge is blocked waiting

**Phase to address:**
Phase 2 (Claude Code integration) — test headless invocation with explicit flags before wiring to Slack.

---

### Pitfall 8: Slack Webhook Signature Not Verified (Replay Attack / Spoofing)

**What goes wrong:**
Any HTTP client that knows your Slack event URL can send forged events to trigger Claude Code sessions. Without signature verification, an attacker sends a crafted payload that makes Claude push malicious code, delete files, or exfiltrate credentials.

**Why it happens:**
Developers focus on getting the bot working and treat the event URL as a secret. Slack's signature verification is an opt-in step that's easy to skip during development and forget to add in production.

**How to avoid:**
- Verify every incoming request using Slack's HMAC-SHA256 signature: `X-Slack-Signature` header against `X-Slack-Request-Timestamp` + raw body
- Use `hmac.compare_digest()` (Python) or `crypto.timingSafeEqual` (Node.js) — not `==` — to prevent timing attacks
- Reject requests where the timestamp is more than 5 minutes old (prevents replay attacks)
- Never log the raw request body in a way that exposes the signing secret

**Warning signs:**
- Event processing logs show requests from unexpected IP ranges
- Bot performs actions nobody on the team requested
- `X-Slack-Signature` header absent on some requests (they're forged)

**Phase to address:**
Phase 1 (Slack bridge foundation) — must exist before the endpoint is deployed.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| `--dangerously-skip-permissions` in non-containerized process | Avoid configuring `--allowedTools` list | Any prompt injection or misconfiguration becomes full system compromise; documented CVEs exploit this vector | Never in production; only in throwaway local dev |
| In-memory event deduplication (Python `set`) | Simple, no dependencies | Fails after process restart; duplicates resume | Only if you never restart the process — i.e., never |
| Single shared working directory for all tasks | Simple to set up | Concurrent sessions corrupt each other | Only if you enforce strict single-session-at-a-time with a lock |
| Hardcoded Anthropic API key in systemd unit file | Quick to deploy | Key is visible in `systemctl show`, `ps aux`, and process environment dumps | Never; use GCP Secret Manager |
| Polling Slack API for messages instead of events | No webhook infrastructure | Polling adds latency, hits rate limits, misses messages during downtime | Never; Events API is the correct approach |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Slack Events API | Subscribing to `message` events in addition to `app_mention`, triggering on all channel activity | Subscribe only to `app_mention`; check `bot_id` field before processing |
| Claude Code `-p` mode | Quoting the prompt incorrectly in shell, causing partial prompt interpretation | Always double-quote the prompt: `claude -p "full prompt here"` |
| Claude Code `-p` mode | Not setting `--allowedTools`, causing Claude to ask for permission mid-session (which hangs non-interactively) | Always specify `--allowedTools` explicitly for headless use |
| GitLab via bot user | Using a personal access token tied to a real user account — if that user is deactivated, the bot breaks | Create a dedicated GitLab bot user with scoped project access token |
| GCP VM → GitLab SSH | Using the bot user's personal SSH key stored as a file on the VM | Use GCP Secret Manager to inject the deploy key at startup; restrict key to read+write on `mic_transformer` only |
| Slack `response_url` | Using `response_url` to post long task outputs — it expires after 30 minutes and has a 5-response limit | Use `chat.postMessage` with the channel ID for all task result posts |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Reading entire large files into context | Context exhaustion on `mic_transformer`'s larger modules; session fails mid-task | Instruct Claude to use `grep` or targeted reads; set explicit line limits in task prompts | Any task reading 3+ large files simultaneously |
| No `--max-turns` limit | Runaway sessions consuming thousands of dollars of API credits on a misunderstood task | Always set `--max-turns 30` or lower; alert in Slack when limit is hit | Any open-ended task (investigate X, fix everything) |
| Synchronous Slack event handler waiting for Claude | VM thread pool exhausted under concurrent requests; bot becomes unresponsive | Async hand-off to background worker immediately on event receipt | Second concurrent request when first is still running |
| Streaming Claude output line-by-line to Slack | Slack rate limits (1 message/second per channel); bot gets throttled or banned | Buffer output, post summary + file attachment for long outputs; post updates every 30 seconds not every line | Any Claude output longer than ~10 lines |

---

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Anthropic API key on the VM as a plaintext file or env var in systemd | Key scraped from VM metadata, process environment, or leaked logs; attacker runs unlimited API calls billed to you | Store in GCP Secret Manager; inject via `secretmanager.versions.access` at startup only |
| Bot accessible from all Slack users in the workspace | Any workspace member can trigger arbitrary code execution on the VM | Check `event.user` against an allowlist (Nicole, Han, named users) before processing; reject with a message if not allowlisted |
| No access log for Claude Code actions | Impossible to audit what the bot did, investigate incidents, or recover from mistakes | Log every Claude invocation: who asked, what prompt, when, session ID, exit code; store logs in Cloud Logging |
| Prompt injection via repo content | Malicious content in `mic_transformer` files (comments, test fixtures, documentation) manipulates Claude into unintended actions | Scope Claude's working directory strictly; review critical file denylist in `settings.json`; run Claude as a low-privilege user |
| Bot token committed to the repo | Token exposure allows impersonating the bot from any machine | Use GCP Secret Manager; add `SLACK_BOT_TOKEN` to `.gitignore`; rotate immediately if ever committed |

---

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Silent failures — Claude errors logged but not reported to Slack | User thinks bot is working; actually nothing happened; they repeat the request triggering duplicates | Always post to Slack on both success and failure; include error summary and session ID for debugging |
| Bot starts task but never posts completion | User has no idea if the task is running, done, or failed; they re-send the request | Post "Starting task..." immediately after ack; post result (or error) when complete |
| Raw Claude output dumped as a 5000-character Slack message | Unreadable; Slack truncates at 40K characters; formatting is lost | Format output: post key result as message text, attach full output as a snippet/file |
| Bot ignores the thread context | User replies in the thread to clarify; bot doesn't see it | Use `--continue` with the session ID if replying in the same thread; or document that the bot only reads the triggering message |
| No acknowledgment of queued requests | User sends a second request while first is running; both requests vanish into silence | Post "Your request is queued (#2 in line, estimated wait: X min)" when a request is queued |

---

## "Looks Done But Isn't" Checklist

- [ ] **Slack verification:** Signature is actually verified on every request — not just during testing. Confirm by sending a forged request and watching it be rejected.
- [ ] **Deduplication:** Event IDs are tracked persistently (not in memory). Confirm by restarting the bridge process and re-sending an already-processed event ID.
- [ ] **Bot message filter:** Bot cannot respond to its own messages. Confirm by checking whether the bot's output messages trigger new events in the logs.
- [ ] **Process timeout:** Claude Code subprocess has an enforced wall-clock timeout. Confirm by asking the bot an unanswerable question and watching it time out and report to Slack rather than hang forever.
- [ ] **User allowlist:** Non-authorized users cannot trigger Claude. Confirm by mentioning the bot from a test account that is not on the allowlist.
- [ ] **Credential isolation:** Claude Code process cannot read `~/.ssh/`, `~/.aws/`, or any secret outside its working directory. Confirm by asking the bot to `cat ~/.ssh/id_rsa` and observing the deny.
- [ ] **Concurrent request safety:** Two simultaneous requests either queue properly or use isolated worktrees without corrupting each other. Confirm by sending two requests within 1 second.
- [ ] **Task result always posted:** Slack always receives a result (or explicit error) for every request. Confirm by triggering a task that intentionally fails and watching Slack receive the failure message.

---

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Anthropic API key leaked | HIGH | Rotate key immediately in Anthropic console; audit usage logs for unauthorized calls; rotate GCP Secret Manager secret |
| Bot infinite loop hit Slack rate limits | LOW | Delete or disable the event trigger; restart bridge with bot message filter in place; Slack rate limits reset within minutes |
| Concurrent sessions corrupted repo | MEDIUM | `git reset --hard` to last known good commit; force-push to VM clone; implement queue/lock before re-enabling |
| Context exhaustion left repo in partial state | MEDIUM | Check git status; revert uncommitted changes; break the original task into smaller chunks with explicit scope |
| Bot token committed to git | HIGH | Immediately rotate in Slack app settings; audit Slack audit logs for unauthorized usage; add pre-commit hook to block token patterns |
| Process hang — Claude never returns | LOW | Kill subprocess by PID; post error to Slack; restart bridge; investigate which task caused the hang |

---

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Slack 3-second timeout | Phase 1: Slack bridge | Send a long-running task; confirm Slack shows no timeout error |
| Duplicate event processing | Phase 1: Slack bridge | Manually replay an event_id; confirm single execution |
| Bot infinite loop | Phase 1: Slack bridge | Bot responds; confirm no second event fires from the response |
| Slack signature verification | Phase 1: Slack bridge | Send forged request; confirm 400 rejection |
| Credential isolation / running as root | Phase 1: VM provisioning | Ask bot to read `~/.ssh/`; confirm denial |
| Context window exhaustion | Phase 2: Claude integration | Run a large file investigation; confirm graceful failure message |
| Process hanging (headless mode) | Phase 2: Claude integration | Send unanswerable task; confirm timeout and Slack notification |
| Concurrent session corruption | Phase 2: Claude integration | Two simultaneous requests; confirm queue or worktree isolation |
| User allowlist enforcement | Phase 2: Claude integration | Unauthorized user mention; confirm rejection |
| Claude output formatting in Slack | Phase 3: UX polish | Run verbose task; confirm readable, non-truncated Slack output |

---

## Sources

- [Claude Code Security Docs](https://code.claude.com/docs/en/security) — official, HIGH confidence
- [Claude Code Headless/Programmatic Mode Docs](https://code.claude.com/docs/en/headless) — official, HIGH confidence
- [Verifying Requests from Slack (Official)](https://api.slack.com/authentication/verifying-requests-from-slack) — official, HIGH confidence
- [Slack Events API Documentation](https://api.slack.com/events-api) — official, HIGH confidence
- [Slack Bolt Python Lazy Listeners](https://docs.slack.dev/tools/bolt-python/concepts/lazy-listeners/) — official, HIGH confidence
- [Claude Code Best Practices Docs](https://code.claude.com/docs/en/best-practices) — official, HIGH confidence
- [GitHub Issue #7497: Process Hangs Indefinitely in Headless Mode](https://github.com/anthropics/claude-code/issues/7497) — official GitHub, HIGH confidence
- [GitHub Issue #4722: Context Window Exhaustion](https://github.com/anthropics/claude-code/issues/4722) — official GitHub, HIGH confidence
- [Check Point Research: CVE-2025-59536 / CVE-2026-21852](https://research.checkpoint.com/2026/rce-and-api-token-exfiltration-through-claude-code-project-files-cve-2025-59536/) — MEDIUM confidence (security research, verified CVEs)
- [--dangerously-skip-permissions Usage Guide](https://www.ksred.com/claude-code-dangerously-skip-permissions-when-to-use-it-and-when-you-absolutely-shouldnt/) — MEDIUM confidence (community, verified against official docs)
- [PromptArmor: Prompt Injection via .docx (Jan 2026)](https://blog.promptlayer.com/claude-dangerously-skip-permissions/) — MEDIUM confidence (community-reported, describes real attack)
- [Redis Distributed Locking for Slack Bots](https://redis.io/tutorials/chat-sdk-slackbot-distributed-locking/) — MEDIUM confidence (official Redis, describes correct deduplication pattern)
- [Git Worktrees for Parallel AI Agents](https://www.nrmitchi.com/2025/10/using-git-worktrees-for-multi-feature-development-with-ai-agents/) — MEDIUM confidence (community, widely corroborated)
- [GCP Secret Manager Guide](https://blog.gitguardian.com/how-to-handle-secrets-with-google-cloud-secret-manager/) — MEDIUM confidence (community, corroborated by GCP official docs)
- [SFEIR Institute: Claude Code Headless Mode Errors](https://institute.sfeir.com/en/claude-code/claude-code-headless-mode-and-ci-cd/errors/) — LOW confidence (third-party training material, statistics unverified)
- [OpenClaw Security Crisis Analysis](https://www.reco.ai/blog/openclaw-the-ai-agent-security-crisis-unfolding-right-now) — LOW confidence (vendor analysis of similar project's CVEs, directionally useful)

---
*Pitfalls research for: Slack-integrated Claude Code autonomous agent on GCP VM*
*Researched: 2026-03-18*

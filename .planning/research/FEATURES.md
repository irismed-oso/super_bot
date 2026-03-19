# Feature Research

**Domain:** Slack-integrated autonomous coding agent (GCP VM + Claude Code CLI)
**Researched:** 2026-03-18
**Confidence:** MEDIUM — based on public docs for Claude Code in Slack (HIGH), Kilo/Copilot/Devin feature sets (MEDIUM), and community implementations (LOW-MEDIUM)

---

## Feature Landscape

### Table Stakes (Users Expect These)

Features users assume exist. Missing these = product feels incomplete.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| @mention trigger in Slack channel | Every Slack bot works this way; it's the entry point | LOW | Must work in channel (not DM). Claude Code in Slack official docs confirm channel-only pattern. |
| Thread-scoped context | Users expect the bot to read the thread before acting, not just the @mention message | LOW | All major agents (Kilo, Copilot, Claude) pull full thread history. Critical for multi-turn tasks. |
| Streamed / incremental progress updates | Long-running tasks feel like a black box without updates; users assume the bot checks in | MEDIUM | Post "working on it" or step-by-step updates as Claude Code runs. Prevents users from retrying. |
| Completion notification with summary | Users expect to be @mentioned when the task is done with what happened | LOW | Standard pattern across Devin, Kilo, Copilot, Claude Code in Slack. |
| Git operations: branch, commit, push | This is a coding agent — version control is assumed | LOW | Claude Code CLI natively supports git. |
| PR creation from Slack | Users treat "do X and open a PR" as a single natural command | MEDIUM | All major agents (Kilo, Copilot, Claude Code in Slack) support this. |
| Code reading and Q&A about the repo | "What does X function do?" is the most common first use case | LOW | Claude Code CLI reads files natively; no extra work needed. |
| Script and command execution | Running Prefect flows, tests, operational scripts is core to this project's value | MEDIUM | VM shell access; Claude Code CLI handles subprocess execution. |
| Error reporting back to Slack | If the bot fails, the channel needs to see why — silently broken is worse than broken | LOW | Post error messages and stack traces as Slack replies. |
| Named-user access control | Small team means only Nicole/Han/named users should trigger the bot | LOW | Allowlist by Slack user ID checked before processing any message. |

### Differentiators (Competitive Advantage)

Features that set the product apart. Not required, but valued.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Persistent project memory (CLAUDE.md + git history) | Bot builds accumulated awareness of mic_transformer instead of starting cold each time | MEDIUM | Claude Code memory system + project CLAUDE.md. Far better than stateless agents. Devin Wiki is the commercial equivalent. |
| Mic_transformer-specific operational commands | "Run the VSP reconciliation flow" works without explaining what that means | LOW | Achieved naturally via Claude Code reading the codebase and CLAUDE.md. No extra code. |
| Isolated task workspaces per job | Each Slack task runs in its own git worktree so concurrent tasks don't stomp each other | HIGH | Sleepless-agent pattern. Requires task queue + workspace manager on the VM. Significant reliability win. |
| Task queue with status slash commands | `/status`, `/cancel` for in-flight tasks — know what's running without asking | MEDIUM | SQLite-backed queue. Sleepless-agent implements this. Prevents duplicate work. |
| Daily digest / activity report | "Here's what I did today" posted to channel on a schedule | LOW | Cron job reading git log + task history. Trust-building for autonomous agent. |
| Automatic test running after code changes | Bot runs tests before reporting done, surfaces failures in Slack | MEDIUM | Claude Code can invoke pytest; pass/fail posted to thread. Reduces review burden. |
| Deployment from Slack | "Deploy to staging" triggers actual deploy workflow from the VM | HIGH | Requires deploy scripts already in mic_transformer. High value but high blast radius. |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem good but create problems.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Approval gates for every destructive action | "Safety first" — humans want to confirm before the bot does anything risky | PROJECT.md explicitly rules this out; approval gates defeat the value of full autonomy for a trusted small team; adds latency and friction to every task | Trust the team + channel visibility. Everyone sees what was asked and done. Use git history as the audit trail. |
| DM-based interaction | Users may want private tasks | DMs hide what the bot is doing from teammates; kills team awareness, which is a core design goal | Channel mentions only. If privacy is needed, use a private channel. |
| Web UI / dashboard | Nice to visualize agent activity | Duplicates Slack; adds a whole new surface to build and maintain | Slack is the dashboard. Post status, results, and daily digests there. |
| Multi-repo support | Teams often work across repos | Dramatically increases complexity of repo selection, context, and security surface | mic_transformer only for v1. Pin scope. |
| Per-user sandboxed environments | Enterprise agents give each user their own environment | Unnecessary overhead for a 2-person team; one shared VM and repo is simpler and sufficient | Single shared VM with git worktrees for task isolation. |
| Real-time token-by-token streaming to Slack | "Show me Claude thinking live" | Slack rate limits will get the bot banned (60 messages/min per channel); streaming at token level is unusable in practice | Post milestone updates (started, tool calls, done). Update a single message via edit rather than spamming new messages. |
| Webhook-based retry loops | Automatically retry every failed task | Retries on bad prompts waste Claude tokens; retries on broken environments loop indefinitely | Report failures clearly. Let humans decide to retry or rephrase. |
| Full chat assistant mode (non-coding Q&A) | "Ask the bot anything" | Dilutes the product; users start treating it as a general chatbot instead of a coding agent; hard to distinguish from Slack's built-in Claude app | Scope to coding and operational tasks on mic_transformer. |

---

## Feature Dependencies

```
[Slack @mention listener]
    └──requires──> [Allowlist user check]
                       └──requires──> [Claude Code session launch]
                                          └──requires──> [VM shell + Claude Code CLI installed]

[Claude Code session launch]
    └──requires──> [mic_transformer repo cloned on VM]
    └──requires──> [CLAUDE.md + project memory configured]

[Progress updates to Slack]
    └──requires──> [Claude Code session launch]
    └──requires──> [Slack bot write permissions in channel]

[PR creation]
    └──requires──> [Git operations working]
    └──requires──> [GitLab credentials on VM]
    └──requires──> [Claude Code session launch]

[Script execution (Prefect flows)]
    └──requires──> [VM Python environment + mic_transformer deps installed]
    └──requires──> [Claude Code session launch]

[Isolated task workspaces]
    └──requires──> [Task queue]
    └──requires──> [Git worktree management]
    └──enhances──> [Claude Code session launch]

[Task queue + /status command]
    └──requires──> [SQLite or equivalent on VM]
    └──enhances──> [Isolated task workspaces]

[Automatic test running]
    └──requires──> [Script execution working]
    └──enhances──> [PR creation]

[Daily digest]
    └──requires──> [Task history stored]
    └──requires──> [Slack bot write permissions]

[Deployment from Slack]
    └──requires──> [Script execution working]
    └──requires──> [Deploy scripts in mic_transformer]
```

### Dependency Notes

- **Slack listener requires allowlist check**: Without user gating, anyone in the workspace can trigger the bot. Must happen before Claude Code is invoked.
- **Everything requires Claude Code CLI on VM**: This is the non-negotiable foundation. Nothing else works without it.
- **PR creation requires GitLab credentials**: Not just Claude Code. The VM needs SSH key or token to push and open MRs on GitLab.
- **Isolated workspaces enhance but don't block v1**: Tasks can share the main working directory for v1 (with serialization), add isolation later.
- **Deployment conflicts with isolated workspaces**: Deployments must touch the real repo state, not a worktree. Needs special handling.

---

## MVP Definition

### Launch With (v1)

Minimum viable product — what's needed to validate the concept.

- [ ] Slack @mention listener that checks allowlist — without this, nothing starts
- [ ] Bridge: @mention triggers Claude Code session on the VM — core mechanic
- [ ] Thread context passed to Claude Code — without this, bot is context-blind
- [ ] Progress updates posted to Slack thread (start + done at minimum) — prevents "is it running?" messages
- [ ] Completion summary with what was done posted back to channel — closes the loop
- [ ] Error reporting to Slack when Claude Code fails — silent failures destroy trust
- [ ] Git operations: commit and push from VM — table stakes for a coding agent
- [ ] PR creation on request — the most common "do something concrete" task

### Add After Validation (v1.x)

Features to add once core is working.

- [ ] Persistent CLAUDE.md project memory — add when users start repeating context they shouldn't need to repeat
- [ ] Script execution for Prefect flows and operational tasks — add when Nicole asks "can you run X" and it doesn't work
- [ ] Task serialization / basic queue — add when concurrent requests cause repo conflicts
- [ ] Automatic test running post-change — add when trust in bot output is high enough to want verification

### Future Consideration (v2+)

Features to defer until product-market fit is established.

- [ ] Isolated task workspaces (git worktrees per task) — significant complexity; add when concurrent tasks become a real problem
- [ ] Task queue with /status slash commands — add when team needs visibility into backlog
- [ ] Daily digest — add when team wants passive awareness of bot activity
- [ ] Deployment from Slack — high blast radius; add only after extensive trust is established

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Slack @mention → Claude Code session | HIGH | MEDIUM | P1 |
| Thread context passed to agent | HIGH | LOW | P1 |
| Progress updates in thread | HIGH | LOW | P1 |
| Completion summary to channel | HIGH | LOW | P1 |
| Error reporting to Slack | HIGH | LOW | P1 |
| Git commit + push | HIGH | LOW | P1 |
| PR creation | HIGH | LOW | P1 |
| Named-user allowlist | HIGH | LOW | P1 |
| Script execution (Prefect, etc.) | HIGH | MEDIUM | P2 |
| Persistent project memory (CLAUDE.md) | HIGH | LOW | P2 |
| Task serialization / basic queue | MEDIUM | MEDIUM | P2 |
| Automatic test running post-change | MEDIUM | MEDIUM | P2 |
| Isolated task workspaces | MEDIUM | HIGH | P3 |
| Daily digest / activity report | LOW | LOW | P3 |
| /status slash command | MEDIUM | MEDIUM | P3 |
| Deployment from Slack | HIGH | HIGH | P3 |

---

## Competitor Feature Analysis

| Feature | Claude Code in Slack (official) | Kilo for Slack | GitHub Copilot in Slack | Our Approach |
|---------|--------------------------------|----------------|-------------------------|--------------|
| @mention trigger | Yes, channel only | Yes | Yes (@GitHub) | Yes, channel only per PROJECT.md |
| Thread context reading | Yes | Yes, full thread | Yes, full thread | Yes |
| PR creation | Yes (one PR per session) | Yes | Yes | Yes |
| Progress updates | Yes, status updates in thread | Not described | Reply when PR ready | Yes |
| Multi-repo support | Yes (auto-selects) | Yes | Yes | No — mic_transformer only |
| Q&A about codebase | Yes | Yes | Yes | Yes (natural via Claude Code) |
| Script execution | Yes (via Claude Code CLI) | Not described | Limited | Yes (core use case) |
| User access control | Workspace admin + channel invite | Not described | GitHub Copilot plan | Named allowlist |
| Persistent memory | Yes (CLAUDE.md) | Not described | Not described | Yes (CLAUDE.md + git) |
| Full autonomy (no approval gates) | No — web UI oversight | No | No — opens draft PR for review | Yes — by design |
| DM support | No | Yes | Yes | No — channel only |
| Task queue | No | No | No | v2 |
| Isolated workspaces | No | No | Yes (ephemeral GitHub Actions) | v2 |

**Key insight:** Every commercial product requires a web UI fallback or approval step. Our bot is unique in that it runs entirely on VM infrastructure with no web dashboard, no per-user cloud accounts, and genuinely full autonomy — which is both the differentiator and the risk surface.

---

## Sources

- Claude Code in Slack official docs: https://code.claude.com/docs/en/slack (HIGH confidence — official Anthropic documentation, fetched 2026-03-18)
- Kilo for Slack feature page: https://kilo.ai/features/slack (MEDIUM confidence — official product page)
- Kilo for Slack VentureBeat launch: https://venturebeat.com/technology/kilo-launches-ai-powered-slack-bot-that-ships-code-from-a-chat-message (MEDIUM confidence)
- GitHub Copilot coding agent in Slack: https://docs.github.com/en/copilot/how-tos/use-copilot-agents/coding-agent/integrate-coding-agent-with-slack (HIGH confidence — official GitHub docs)
- Devin 2025 performance review: https://cognition.ai/blog/devin-annual-performance-review-2025 (MEDIUM confidence — official Cognition blog)
- Sleepless Agent (Claude Code + Slack task queue): https://github.com/context-machine-lab/sleepless-agent (LOW-MEDIUM confidence — community implementation)
- Mintlify Slack coding agent design: https://www.mintlify.com/blog/we-built-our-coding-agent-for-slack (MEDIUM confidence — engineering blog)
- Anthropic long-running agent harnesses: https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents (HIGH confidence — official Anthropic engineering)
- Slack developer security best practices: https://slack.dev/data-security-best-practices-for-agentic-slack-apps/ (HIGH confidence — official Slack developer docs)

---
*Feature research for: Slack-integrated autonomous coding agent (Super Bot)*
*Researched: 2026-03-18*

---
phase: 13-error-ux
verified: 2026-03-24T20:15:00Z
status: passed
score: 6/6 must-haves verified
re_verification: false
---

# Phase 13: Error UX Verification Report

**Phase Goal:** When something goes wrong or takes too long, Nicole sees a message that tells her what was attempted, what the current state is, and what to do next — never a bare timeout or generic error
**Verified:** 2026-03-24T20:15:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| #   | Truth                                                                                          | Status     | Evidence                                                                                                                                                             |
| --- | ---------------------------------------------------------------------------------------------- | ---------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | When a task times out, the error message names what was being attempted                        | VERIFIED   | `_format_error("error_timeout", ...)` includes "Was running: {task_label}" on second line; confirmed via live test: output contains `crawl eyemed DME 03.20`         |
| 2   | When a task times out, the error message suggests a concrete next action                       | VERIFIED   | `_timeout_suggestion()` scans `LOCATION_ALIASES` and returns `"Try checking the result: \`status on {canonical} eyemed today\`"`; falls back to `/sb-status` hint    |
| 3   | Timeout messages look visually different from hard failure messages                            | VERIFIED   | Three distinct prefixes: `:hourglass:` (timeout), `:no_entry_sign:` (cancelled), `:x:` (hard failure); live test confirmed no prefix overlap across three subtypes   |
| 4   | Nicole can tell at a glance if a task timed out, failed, or is still running                  | VERIFIED   | Visual prefix distinction + `_handle_bot_status()` returns gear/satellite/check-mark states; "are you broken?" resolves via fast-path without spawning agent          |
| 5   | Sending "are you broken?" returns actual task state instead of spawning an agent               | VERIFIED   | `_BOT_STATUS_RE` matches all plan-specified phrases; registered last in `FAST_COMMANDS`; calls `queue_manager.get_state()` + `background_monitor.get_active_monitors()` |
| 6   | Sending "are you still going?" returns actual task state instead of spawning an agent          | VERIFIED   | `are\s+you\s+still\s+(?:going|running|working|there)` branch in `_BOT_STATUS_RE`; live regex test passed                                                             |

**Score:** 6/6 truths verified

### Required Artifacts

| Artifact                    | Expected                                                            | Status     | Details                                                                                              |
| --------------------------- | ------------------------------------------------------------------- | ---------- | ---------------------------------------------------------------------------------------------------- |
| `bot/progress.py`           | Contextual error formatting with task name, visual distinction, next-action suggestions | VERIFIED   | `_format_error` has `task_text` param; three distinct emoji prefixes; `_timeout_suggestion` helper; contains `"was running:"` (case-insensitive: "Was running:") |
| `bot/fast_commands.py`      | Status query fast-path handler for "are you broken" style messages  | VERIFIED   | `_handle_bot_status` function exists; `_BOT_STATUS_RE` compiled regex present; registered in `FAST_COMMANDS` |
| `bot/background_monitor.py` | Public accessor for active background task state                    | VERIFIED   | `get_active_monitors()` returns `list[dict]` with `date_str`, `run_count`, `elapsed_s`; `_active_monitors` module-level list maintained via done-callback |

**Artifact level detail:**

- `bot/progress.py`: exists (203 lines), substantive, wired — `post_result` calls `_format_error` with `task_text=result.get("task_text", "")` at line 121
- `bot/fast_commands.py`: exists (411 lines), substantive, wired — `_BOT_STATUS_RE` registered as last entry in `FAST_COMMANDS` list; `_handle_bot_status` imports from `queue_manager` and `background_monitor` via top-level `from bot import prefect_api, queue_manager, background_monitor, task_state`
- `bot/background_monitor.py`: exists (262 lines), substantive, wired — `get_active_monitors()` at line 72; called from `fast_commands._handle_bot_status` at line 343

### Key Link Verification

| From                  | To                              | Via                                             | Status   | Details                                                                                                     |
| --------------------- | ------------------------------- | ----------------------------------------------- | -------- | ----------------------------------------------------------------------------------------------------------- |
| `bot/handlers.py`     | `bot/progress.py`               | `clean_text` passed through result dict to `_format_error` | WIRED    | `result["task_text"] = clean_text` at handlers.py:128; `post_result` reads `result.get("task_text", "")` at progress.py:121 |
| `bot/fast_commands.py` | `bot/queue_manager.py`          | `get_state()` call in status handler            | WIRED    | `queue_manager.get_state()` at fast_commands.py:342; `get_state()` returns `{current, queue_depth, is_full}` at queue_manager.py:75 |
| `bot/fast_commands.py` | `bot/background_monitor.py`     | `get_active_monitors()` call in status handler  | WIRED    | `background_monitor.get_active_monitors()` at fast_commands.py:343; function defined at background_monitor.py:72 |

**clean_text end-to-end trace:**

1. `handlers.py:49` — `clean_text = re.sub(r"<@[A-Z0-9]+>", "", text).strip()`
2. `handlers.py:158` — `QueuedTask(..., clean_text=clean_text, ...)`
3. `handlers.py:128` — `result["task_text"] = clean_text` (inside `result_cb`, before every `post_result` call)
4. `progress.py:121` — `task_text=result.get("task_text", "")` passed to `_format_error`
5. `progress.py:159` — `task_label = task_text or "(unknown task)"` used in all three error format branches

Note: `queue_manager.py` error paths (`CancelledError`, bare `Exception`) do NOT inject `task_text` into the result dict they pass to `result_callback`. However, because `result_cb` in handlers.py adds `result["task_text"] = clean_text` unconditionally before calling `progress.post_result`, the `task_text` is always present when `post_result` is invoked. The wiring is correct.

### Requirements Coverage

| Requirement | Source Plan  | Description                                                                                           | Status    | Evidence                                                                                                                   |
| ----------- | ------------ | ----------------------------------------------------------------------------------------------------- | --------- | -------------------------------------------------------------------------------------------------------------------------- |
| ERUX-01     | 13-01-PLAN   | Timeout messages include what was attempted and suggested next action                                  | SATISFIED | `_format_error("error_timeout")` outputs "Was running: {task}" + `_timeout_suggestion()` result; live test passed         |
| ERUX-02     | 13-01-PLAN   | Error messages distinguish timeout vs failure vs still-running-in-background                           | SATISFIED | `:hourglass:` for timeout, `:x:` for internal failure, `:no_entry_sign:` for cancelled; `_handle_bot_status` reports running/background states |
| ERUX-03     | 13-01-PLAN   | Bot responds to "are you broken?" / "are you still going?" with actual task status instead of spawning a new agent session | SATISFIED | `_BOT_STATUS_RE` fast-path handler registered in `FAST_COMMANDS`; calls `get_state()` and `get_active_monitors()` directly |

No orphaned requirements. All three ERUX IDs declared in PLAN frontmatter match REQUIREMENTS.md entries mapped to Phase 13.

### Anti-Patterns Found

None. Scan across all five modified files (`bot/progress.py`, `bot/handlers.py`, `bot/fast_commands.py`, `bot/queue_manager.py`, `bot/background_monitor.py`) returned no TODO, FIXME, XXX, HACK, PLACEHOLDER, or stub markers.

### Human Verification Required

#### 1. "are you broken?" in live Slack channel while bot is idle

**Test:** On the VM, @mention the bot with "are you broken?"
**Expected:** Bot edits the "Working on it." message in-place within a few seconds showing the idle status message (white checkmark, "Idle -- no tasks running, no background jobs. Uptime: Xh Ym")
**Why human:** Requires live Slack interaction and the VM bot process running; can't verify the edit-in-place behavior or Slack rendering of `:white_check_mark:` programmatically.

#### 2. Timeout error message rendering in Slack

**Test:** Trigger a real timeout (or simulate via a task that exceeds the timeout) for a task containing a known location like "DME"
**Expected:** Nicole sees a Slack message with hourglass icon, "Task timed out", "Was running: {original message}", partial output, and the suggestion "`status on DME eyemed today`"
**Why human:** Requires a live timeout event; the Slack mrkdwn rendering of emoji syntax (`:hourglass:`) needs visual confirmation.

#### 3. "are you broken?" does not interfere with eyemed commands

**Test:** Send "status on DME eyemed today" — should still route to `_handle_eyemed_status`, not `_handle_bot_status`
**Expected:** Returns eyemed scan status output, not the bot health summary
**Why human:** The ordering in `FAST_COMMANDS` is correct (eyemed status before bot status), but the regex non-collision should be confirmed with real messages to catch edge cases.

### Gaps Summary

No gaps. All six observable truths are verified. All three artifacts pass all three levels (exists, substantive, wired). All three key links are confirmed connected. All requirement IDs (ERUX-01, ERUX-02, ERUX-03) are satisfied. No blocker anti-patterns found.

---

_Verified: 2026-03-24T20:15:00Z_
_Verifier: Claude (gsd-verifier)_

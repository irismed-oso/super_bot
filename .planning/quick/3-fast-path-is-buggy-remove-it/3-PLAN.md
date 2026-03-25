---
phase: quick
plan: 3
type: execute
wave: 1
depends_on: []
files_modified:
  - bot/fast_commands.py
  - bot/handlers.py
  - bot/progress.py
autonomous: true
requirements: []
must_haves:
  truths:
    - "All user messages go through the full agent pipeline -- no fast-path shortcut"
    - "Bot still starts up and handles mentions/thread replies correctly"
    - "Timeout suggestion in progress.py still works without importing fast_commands"
  artifacts:
    - path: "bot/handlers.py"
      provides: "Message handling without fast-path bypass"
    - path: "bot/progress.py"
      provides: "Timeout suggestion without fast_commands dependency"
  key_links:
    - from: "bot/handlers.py"
      to: "bot/queue_manager.py"
      via: "all messages enqueue into agent pipeline"
      pattern: "enqueue\\(task\\)"
---

<objective>
Remove the fast-path command system entirely. The fast-path bypass in handlers.py
intercepts certain messages (eyemed crawl, eyemed status, bot status, batch crawl)
and handles them directly without the agent pipeline. This is buggy and should be
removed so all messages flow through the full agent pipeline.

Purpose: Eliminate buggy fast-path code that short-circuits the agent pipeline.
Output: Cleaned handlers.py, deleted or gutted fast_commands.py, fixed progress.py import.
</objective>

<execution_context>
@/Users/hanjing/.claude/get-shit-done/workflows/execute-plan.md
@/Users/hanjing/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@bot/handlers.py
@bot/fast_commands.py
@bot/progress.py
</context>

<tasks>

<task type="auto">
  <name>Task 1: Remove fast-path bypass from handlers and delete fast_commands module</name>
  <files>bot/handlers.py, bot/fast_commands.py, bot/progress.py</files>
  <action>
1. In `bot/handlers.py`:
   - Remove the import: `from bot.fast_commands import try_fast_command` (line 7)
   - Remove the entire fast-path block in `_run_agent_real` (lines 67-99): the call to
     `try_fast_command()`, the `if fast_result is not None:` branch, and all the Slack
     message posting logic inside it. After removing, the function should flow directly
     from the DB logging (line 65-66) into `session_id = session_map.get(...)` (line 101).

2. Delete `bot/fast_commands.py` entirely. The module is no longer imported anywhere
   after the handlers.py cleanup.

3. In `bot/progress.py` function `_timeout_suggestion` (lines 198-208):
   - Remove the `from bot.fast_commands import LOCATION_ALIASES` import (line 203)
   - Remove the for-loop that checks location aliases (lines 204-207)
   - Simplify the function to just return the default: `"Check /sb-status for current state."`
   - Keep the early return for empty task_text.
  </action>
  <verify>
    <automated>cd /Users/hanjing/Documents/Code/GitLab/claude_workspace/super_bot && python -c "from bot.handlers import register; from bot.progress import _timeout_suggestion; print('imports OK')"</automated>
    <manual>Confirm bot/fast_commands.py is deleted, handlers.py has no fast_command references, progress.py has no fast_commands import</manual>
  </verify>
  <done>
    - bot/fast_commands.py is deleted
    - bot/handlers.py has zero references to fast_commands or try_fast_command
    - bot/progress.py _timeout_suggestion works without fast_commands
    - All messages now flow through the agent pipeline (no fast-path shortcut)
  </done>
</task>

</tasks>

<verification>
- `grep -r "fast_command" bot/` returns no results
- `grep -r "fast_path" bot/` returns no results (except maybe db subtype strings if desired)
- `python -c "from bot.handlers import register"` succeeds
- `python -c "from bot.progress import _timeout_suggestion"` succeeds
</verification>

<success_criteria>
- fast_commands.py deleted
- No fast-path bypass in the message handling flow
- All user messages go through the full agent pipeline
- Bot module imports cleanly
</success_criteria>

<output>
After completion, create `.planning/quick/3-fast-path-is-buggy-remove-it/3-SUMMARY.md`
</output>

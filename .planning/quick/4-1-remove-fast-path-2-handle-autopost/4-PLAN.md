---
phase: quick-4
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - bot/fast_commands.py
  - bot/handlers.py
autonomous: true
requirements: [QUICK-4]
must_haves:
  truths:
    - "Memory commands (remember, recall, forget, list memories) still work as fast-path"
    - "Deploy guard still blocks deploys when agent task is running"
    - "Rollback guard still blocks rollbacks when agent task is running"
    - "Messages like 'autopost eyemed' flow through to the agent pipeline (no fast-path interception)"
    - "Messages like 'crawl eyemed DME 03.20.26' flow through to the agent pipeline"
    - "Messages like 'deploy status' flow through to the agent pipeline"
    - "Messages like 'bot status' flow through to the agent pipeline"
  artifacts:
    - path: "bot/fast_commands.py"
      provides: "Memory commands and deploy/rollback guards only"
      contains: "_handle_remember"
    - path: "bot/handlers.py"
      provides: "Fast command integration"
      contains: "try_fast_command"
  key_links:
    - from: "bot/handlers.py"
      to: "bot/fast_commands.py"
      via: "try_fast_command import"
      pattern: "from bot.fast_commands import try_fast_command"
---

<objective>
Strip bot/fast_commands.py down to only memory commands and deploy/rollback guards, removing all EyeMed crawl, deploy status/preview, bot status, and supporting infrastructure (LOCATION_ALIASES, _run_script, action-request detection, date parsing). This ensures messages like "autopost eyemed" flow through to the agent pipeline instead of being intercepted or blocked.

Purpose: The fast path was greedy -- it intercepted commands the agent should handle. Memory commands and guards are the only legitimate fast-path handlers (they need instant response without queueing). Everything else should go through the agent.
Output: Cleaned fast_commands.py (~120 lines), updated handlers.py comment
</objective>

<execution_context>
@/Users/hanjing/.claude/get-shit-done/workflows/execute-plan.md
@/Users/hanjing/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@bot/fast_commands.py
@bot/handlers.py
</context>

<tasks>

<task type="auto">
  <name>Task 1: Strip fast_commands.py to memory + guards only</name>
  <files>bot/fast_commands.py, bot/handlers.py</files>
  <action>
Rewrite bot/fast_commands.py keeping ONLY:

1. Module docstring (update to reflect reduced scope: "Fast-path handlers for memory commands and deploy/rollback guards")
2. Imports: keep only what's needed (re, structlog, bot.memory_store, bot.queue_manager)
3. Memory command section (lines 85-223): ALL of these stay unchanged:
   - _REMEMBER_RE, _RECALL_RE, _FORGET_RE, _LIST_MEMORIES_RE
   - _CATEGORY_NORMALIZE
   - _handle_remember, _handle_recall, _handle_forget, _handle_list_memories
4. Deploy guard (lines 344-373): _DEPLOY_GUARD_RE, _handle_deploy_guard -- stays unchanged
5. Rollback guard (lines 380-406): _ROLLBACK_GUARD_RE, _handle_rollback_guard -- stays unchanged
6. FAST_COMMANDS registry: update to only contain memory commands + deploy guard + rollback guard (6 entries total)
7. try_fast_command function: keep the loop but REMOVE the is_action_request check at line 719 since it was only needed for the removed greedy handlers

REMOVE entirely:
- Action-request detection: _ACTION_STEMS, _ACTION_RE, is_action_request (lines 35-51)
- MIC_TRANSFORMER_DIR, MIC_TRANSFORMER_PYTHON, FAST_CMD_TIMEOUT (lines 54-60)
- _run_script helper (lines 63-82)
- LOCATION_ALIASES and all location-related code (lines 229-269)
- _handle_deploy_status and _DEPLOY_STATUS_RE (lines 276-316)
- _handle_deploy_preview and _DEPLOY_PREVIEW_RE (lines 323-341)
- Batch crawl: _BATCH_CRAWL_RE, date parsing helpers, _handle_batch_crawl (lines 413-493)
- Single crawl: _EYEMED_CRAWL_RE, _handle_eyemed_crawl (lines 500-563)
- EyeMed status: _EYEMED_STATUS_RE, _handle_eyemed_status (lines 570-634)
- Bot status: _BOT_STATUS_RE, _handle_bot_status (lines 641-674)
- Imports no longer needed: asyncio, os, date, prefect_api, background_monitor, task_state, deploy_state (entire import line)

In bot/handlers.py line 87, update the comment from:
  "# Fast-path commands (deploy status, preview, guard, eyemed status/crawl)"
to:
  "# Fast-path commands (memory, deploy guard, rollback guard)"
  </action>
  <verify>
    <automated>cd /Users/hanjing/Documents/Code/GitLab/claude_workspace/super_bot && python -c "from bot.fast_commands import try_fast_command, FAST_COMMANDS; print(f'Commands: {len(FAST_COMMANDS)}'); assert len(FAST_COMMANDS) == 6, f'Expected 6, got {len(FAST_COMMANDS)}'; print('OK')" && python -c "import ast; tree = ast.parse(open('bot/fast_commands.py').read()); names = {n.id for node in ast.walk(tree) for n in [node] if isinstance(n, ast.Name)}; assert 'LOCATION_ALIASES' not in names, 'LOCATION_ALIASES still present'; assert '_run_script' not in names, '_run_script still present'; print('No removed symbols found')" && python -c "from bot.handlers import register; print('handlers import OK')"</automated>
  </verify>
  <done>
- bot/fast_commands.py contains only memory commands (4) + deploy guard (1) + rollback guard (1) = 6 entries in FAST_COMMANDS
- No LOCATION_ALIASES, _run_script, is_action_request, eyemed, crawl, bot_status code remains
- No unused imports remain
- bot/handlers.py imports and calls try_fast_command successfully
- "autopost eyemed" does NOT match any pattern in FAST_COMMANDS (verified by: none of the 6 regexes match it)
  </done>
</task>

</tasks>

<verification>
```bash
# Verify no removed code remains
cd /Users/hanjing/Documents/Code/GitLab/claude_workspace/super_bot
grep -c "LOCATION_ALIASES\|_run_script\|is_action_request\|_handle_eyemed\|_handle_batch_crawl\|_handle_bot_status\|_handle_deploy_status\|_handle_deploy_preview" bot/fast_commands.py
# Expected: 0

# Verify kept code exists
grep -c "_handle_remember\|_handle_recall\|_handle_forget\|_handle_list_memories\|_handle_deploy_guard\|_handle_rollback_guard" bot/fast_commands.py
# Expected: 6+ (function defs + registry entries)

# Verify "autopost eyemed" does not match any fast command
python -c "
from bot.fast_commands import FAST_COMMANDS
text = 'autopost eyemed'
for pattern, handler in FAST_COMMANDS:
    if pattern.search(text):
        print(f'FAIL: matched {pattern.pattern}')
        exit(1)
print('PASS: autopost eyemed falls through to agent')
"
```
</verification>

<success_criteria>
- fast_commands.py is ~120-150 lines (down from 740)
- Only 6 handlers in FAST_COMMANDS registry
- Memory commands work: remember, recall, forget, list memories
- Deploy/rollback guards work: block when task running, pass through otherwise
- "autopost eyemed", "crawl eyemed DME", "deploy status", "bot status" all fall through to agent pipeline
</success_criteria>

<output>
After completion, create `.planning/quick/4-1-remove-fast-path-2-handle-autopost/4-SUMMARY.md`
</output>

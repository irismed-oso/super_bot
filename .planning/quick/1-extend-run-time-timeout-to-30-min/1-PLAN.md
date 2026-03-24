---
phase: quick
plan: 1
type: execute
wave: 1
depends_on: []
files_modified:
  - bot/agent.py
  - scripts/test_agent.py
autonomous: true
requirements: [QUICK-1]
must_haves:
  truths:
    - "Agent tasks run for up to 30 minutes before timing out"
    - "Test script default timeout matches production timeout"
  artifacts:
    - path: "bot/agent.py"
      provides: "TIMEOUT_SECONDS = 1800"
      contains: "TIMEOUT_SECONDS = 1800"
    - path: "scripts/test_agent.py"
      provides: "Consistent test timeout default"
      contains: "default=1800"
  key_links: []
---

<objective>
Extend the agent run time timeout from 10 minutes (600s) to 30 minutes (1800s).

Purpose: Allow longer-running tasks (complex code changes, multi-step deployments) to complete without premature timeout.
Output: Updated timeout constant and matching test script default.
</objective>

<execution_context>
@/Users/hanjing/.claude/get-shit-done/workflows/execute-plan.md
@/Users/hanjing/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@bot/agent.py
@scripts/test_agent.py
</context>

<tasks>

<task type="auto">
  <name>Task 1: Update timeout constant and test script default</name>
  <files>bot/agent.py, scripts/test_agent.py</files>
  <action>
In bot/agent.py line 39, change:
  TIMEOUT_SECONDS = 600   # 10 minutes -- locked decision (CONTEXT.md Safety Limits)
to:
  TIMEOUT_SECONDS = 1800  # 30 minutes

In scripts/test_agent.py line 42, change:
  default=600,
to:
  default=1800,
And update the help text on line 43 to say "(default: 1800)".

No other files reference the timeout constant directly -- queue_manager.py uses the default parameter which pulls from TIMEOUT_SECONDS automatically.
  </action>
  <verify>
    <automated>grep -n "TIMEOUT_SECONDS = 1800" bot/agent.py && grep -n "default=1800" scripts/test_agent.py</automated>
  </verify>
  <done>TIMEOUT_SECONDS is 1800 in bot/agent.py; test_agent.py default timeout is 1800; both values are consistent at 30 minutes.</done>
</task>

</tasks>

<verification>
grep "1800" bot/agent.py scripts/test_agent.py confirms both files updated.
grep "600" bot/agent.py scripts/test_agent.py returns no timeout-related hits.
</verification>

<success_criteria>
- TIMEOUT_SECONDS = 1800 in bot/agent.py
- scripts/test_agent.py --timeout default is 1800
- No stale 600-second references remain in timeout-related code
</success_criteria>

<output>
After completion, create `.planning/quick/1-extend-run-time-timeout-to-30-min/1-SUMMARY.md`
</output>

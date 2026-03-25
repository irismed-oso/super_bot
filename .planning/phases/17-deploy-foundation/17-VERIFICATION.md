---
phase: 17-deploy-foundation
verified: 2026-03-25T19:00:00Z
status: gaps_found
score: 8/9 must-haves verified
re_verification: false
gaps:
  - truth: "User can type 'deploy status' and see current commit, branch, and pending change count for each repo"
    status: partial
    reason: "REQUIREMENTS.md SDPL-03 specifies 'last deploy time' as a required field, but get_repo_status() and _handle_deploy_status() do not track or display last deploy time. SHA, branch, and pending-change count are all present. The REQUIREMENTS.md checkbox for SDPL-03 is also still unchecked (line 151)."
    artifacts:
      - path: "bot/deploy_state.py"
        issue: "get_repo_status() returns {sha, branch, behind, dirty} -- no last_deploy_time field"
      - path: "bot/fast_commands.py"
        issue: "_handle_deploy_status() formats sha, branch, behind count -- no last deploy time displayed"
    missing:
      - "Track last deploy timestamp (e.g., write to deploy-state or a separate file after each successful deploy)"
      - "Surface last deploy time in _handle_deploy_status() output"
      - "Update REQUIREMENTS.md checkbox for SDPL-03 (line 151) to checked [x]"
human_verification:
  - test: "Verify deploy super_bot end-to-end on production VM"
    expected: "Bot posts pre-restart message with SHA details, restarts, posts 'I'm back, running commit <sha>' to original thread"
    why_human: "Requires live Prefect flow run and bot restart on production VM; cannot simulate programmatically"
  - test: "Verify deploy mic_transformer on production VM"
    expected: "Bot triggers Prefect flow, shows polling progress in-place, reports COMPLETED or FAILED"
    why_human: "Requires live Prefect flow for mic_transformer (deployment 'deploy-mic-transformer' may not yet exist on VM)"
  - test: "Verify VRFY-01 through VRFY-04 on production VM"
    expected: "Digest changelog fires, fast-path responds, background monitor tracks, heartbeat ticks"
    why_human: "Live VM behavior; Plan 03 summary claims checkpoint:human-verify was approved but no automated evidence exists"
---

# Phase 17: Deploy Foundation Verification Report

**Phase Goal:** The team can deploy super_bot and mic_transformer from Slack with a single command, see what would be deployed before deploying, and get blocked if an agent task is running -- with self-restart handling for super_bot deploys and live verification of v1.4-v1.6 features baked into the deploy workflow

**Verified:** 2026-03-25T19:00:00Z
**Status:** gaps_found
**Re-verification:** No -- initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | User can type 'deploy status' and see current commit, branch, and pending change count | PARTIAL | SHA/branch/behind-count wired. REQUIREMENTS.md SDPL-03 also requires last deploy time -- not implemented |
| 2 | User can type 'deploy preview super_bot' and see list of commits to be deployed | VERIFIED | `_handle_deploy_preview` calls `get_deploy_preview()` which runs `git fetch` + `git log HEAD..origin/main` |
| 3 | User typing 'deploy super_bot' while agent task running gets a warning | VERIFIED | `_handle_deploy_guard` calls `queue_manager.get_current_task()`, returns block message when non-None and "force" absent |
| 4 | User types 'deploy super_bot' and bot writes deploy-state, posts pre-restart message, triggers Prefect | VERIFIED | `_self_deploy()` in deploy.py: writes state, edits ack with pre-restart message, calls `prefect_api.create_flow_run` |
| 5 | After restart bot posts 'I'm back' to original thread | VERIFIED | `_check_deploy_recovery` in app.py reads state file on startup, posts message; scheduled via `_delayed_deploy_check` 5s after start |
| 6 | User types 'deploy mic_transformer' and bot triggers Prefect, polls completion, reports result | VERIFIED | `_external_deploy()` in deploy.py triggers Prefect, polls every 5s up to 600s, edits message in-place on state changes |
| 7 | If nothing to deploy (already on latest), bot aborts cleanly | VERIFIED | `handle_deploy()` checks `status["behind"] == 0` and returns "Already on latest (`sha`). Nothing to deploy." |
| 8 | DEPLOY.md has v1.8 section with deploy commands reference | VERIFIED | Lines 574+ in DEPLOY.md; `v1.8` appears 2 times; table of 5 commands present |
| 9 | v1.4-v1.6 features verified working on production VM | HUMAN NEEDED | Plan 03 human checkpoint was marked approved in summary; no automated evidence |

**Score:** 7/9 truths fully verified (1 partial gap, 1 human needed)

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `bot/deploy_state.py` | REPO_CONFIG, resolve_repo, deploy-state I/O, async git helpers | VERIFIED | 174 lines; exports all required names; substantive implementation |
| `bot/fast_commands.py` | Fast-path handlers for deploy status, preview, guard | VERIFIED | 11 commands registered; `_DEPLOY_STATUS_RE`, `_DEPLOY_PREVIEW_RE`, `_DEPLOY_GUARD_RE` all present |
| `bot/deploy.py` | handle_deploy() for both repos | VERIFIED | 297 lines; `handle_deploy`, `_self_deploy`, `_external_deploy`, `POLL_INTERVAL`, `MAX_POLL_DURATION`, `TERMINAL_STATES` all present |
| `bot/app.py` | Post-restart deploy-state recovery hook | VERIFIED | `_check_deploy_recovery` and `_delayed_deploy_check` present; scheduled before `handler.start_async()` |
| `bot/handlers.py` | Deploy command routing, fast-path dispatch | VERIFIED | `_DEPLOY_CMD_RE` present; `try_fast_command` called; `handle_deploy` called for deploy commands |
| `DEPLOY.md` | v1.8 section with deploy commands and verification checklist | VERIFIED | v1.8 section exists with commands table and SDPL/VRFY checklist |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `bot/fast_commands.py` | `bot/deploy_state.py` | `from bot.deploy_state import get_repo_status, get_deploy_preview, resolve_repo, REPO_CONFIG` | WIRED | Import at line 20-25; `get_repo_status` called in `_handle_deploy_status`, `get_deploy_preview` in `_handle_deploy_preview`, `resolve_repo` in guard handler |
| `bot/fast_commands.py` | `bot/queue_manager.py` | `queue_manager.get_current_task()` | WIRED | `queue_manager` in imports line 19; `queue_manager.get_current_task()` called at line 355 in `_handle_deploy_guard` |
| `bot/deploy.py` | `bot/prefect_api.py` | `prefect_api.find_deployment_id` + `create_flow_run` + `get_flow_run_status` | WIRED | `from bot import prefect_api` (line 14); called at lines 111, 184, 224, 259 |
| `bot/deploy.py` | `bot/deploy_state.py` | `write_deploy_state, get_repo_status, get_deploy_preview` | WIRED | `from bot.deploy_state import ...` (lines 15-19); all three used in `handle_deploy` |
| `bot/app.py` | `bot/deploy_state.py` | `read_and_clear_deploy_state` on startup | WIRED | Imported inside `_check_deploy_recovery` at line 22; called at line 24 |
| `bot/handlers.py` | `bot/deploy.py` | `handle_deploy` called for deploy commands | WIRED | `from bot.deploy import handle_deploy` (line 10); called at line 101 |
| `bot/handlers.py` | `bot/fast_commands.py` | `try_fast_command` called before agent queue | WIRED | `from bot.fast_commands import try_fast_command` (line 11); called at line 81, result checked at line 82 |
| `bot/deploy.py` | `prefect/deploy_superbot_flow.py` | Prefect API triggers `deploy-superbot` deployment | WIRED | `deploy_state.py` REPO_CONFIG has `"prefect_deployment": "deploy-superbot"` (line 28); `prefect/deploy_superbot_flow.py` registers `deploy-superbot` at lines 104, 169 |

---

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| SDPL-01 | 17-02 | Deploy super_bot from Slack with self-restart and post-restart "I'm back" confirmation | SATISFIED | `_self_deploy()` + `_check_deploy_recovery()` implement the full self-restart loop |
| SDPL-02 | 17-02 | Deploy mic_transformer from Slack with git pull, deps install, and health check | SATISFIED (partial) | `_external_deploy()` triggers Prefect and polls; git pull/deps install happen inside the Prefect flow per CONTEXT.md locked decision. Health check is TBD (CONTEXT.md: "service name TBD") |
| SDPL-03 | 17-01 | Deploy status showing current commit, branch, **last deploy time**, and pending changes count | PARTIAL | SHA, branch, pending changes shown. Last deploy time NOT tracked or displayed. REQUIREMENTS.md checkbox still unchecked (line 151) |
| SDPL-04 | 17-01 | Deploy preview showing commits between current HEAD and origin/main | SATISFIED | `get_deploy_preview()` runs `git fetch` + `git log HEAD..origin/main`; REQUIREMENTS.md checkbox unchecked (line 152) but code is correct |
| SDPL-05 | 17-01 | Deploy blocks with warning if agent task running; force override available | SATISFIED | `_handle_deploy_guard` checks `queue_manager.get_current_task()`; "force" keyword bypasses block; REQUIREMENTS.md checkbox unchecked (line 153) but code is correct |
| VRFY-01 | 17-03 | Digest changelog verified working on VM | HUMAN NEEDED | Plan 03 human checkpoint approved per summary; no automated evidence |
| VRFY-02 | 17-03 | Fast-path commands verified on VM | HUMAN NEEDED | Same as above |
| VRFY-03 | 17-03 | Background task monitoring verified on VM | HUMAN NEEDED | Same as above |
| VRFY-04 | 17-03 | Progress heartbeat verified on VM | HUMAN NEEDED | Same as above |

**Note -- REQUIREMENTS.md checkbox inconsistency:** SDPL-03, SDPL-04, and SDPL-05 are unchecked (`- [ ]`) at lines 151-153 in the requirement definitions, but marked "Complete" in the phase table (lines 382-384). SDPL-03 has a real code gap (missing last deploy time). SDPL-04 and SDPL-05 are implemented correctly in code; the checkboxes were not updated.

---

## Anti-Patterns Found

| File | Pattern | Severity | Impact |
|------|---------|----------|--------|
| `bot/deploy_state.py` line 37 | `"service": None, # TBD -- needs VM verification` | Info | mic_transformer service name unknown; deploy.py does not use the service field (delegates to Prefect), so no functional impact currently |

No TODO/FIXME/stub/placeholder patterns found in any of the five new or modified files.

---

## Human Verification Required

### 1. End-to-end super_bot self-deploy

**Test:** In Slack, type `deploy super_bot` (with pending commits on the VM)
**Expected:** Bot posts pre-restart message with SHA details and commit list, triggers Prefect deploy, restarts, and posts "I'm back, running commit `<new_sha>`" to original thread within 30 seconds
**Why human:** Requires live Prefect flow run and bot process restart on production VM

### 2. End-to-end mic_transformer deploy

**Test:** In Slack, type `deploy mic_transformer`
**Expected:** Bot triggers Prefect flow `deploy-mic-transformer`, shows polling progress edited in-place every 5 seconds, and reports COMPLETED or the failure state
**Why human:** Requires the `deploy-mic-transformer` Prefect deployment to exist on the VM (it is listed as TBD/unverified in RESEARCH.md)

### 3. VRFY-01 through VRFY-04 production verification

**Test:** Follow the checklist in DEPLOY.md lines 618-631 (digest changelog, fast-path commands, batch crawl, heartbeat)
**Expected:** All four feature families confirmed working on the production VM
**Why human:** These are live VM behavioral checks; Plan 03 summary says a human approved them but this cannot be verified from the codebase alone

---

## Gaps Summary

One code gap blocks full SDPL-03 satisfaction: the `deploy status` command does not display last deploy time, which is part of the REQUIREMENTS.md SDPL-03 description. The implementation shows SHA, branch, and pending-change count -- three of the four fields. Last deploy time requires either writing a timestamp after each successful deploy (to a file or the deploy-state mechanism) and reading it back in the status handler, or adding it as a tracked field in deploy_state.py.

Additionally, REQUIREMENTS.md has a documentation inconsistency: SDPL-03, SDPL-04, and SDPL-05 checkboxes are unchecked despite the phase table marking them Complete. SDPL-04 and SDPL-05 are correctly implemented in code, so those two checkboxes should be updated. SDPL-03 should remain unchecked until last deploy time is implemented.

All other phase deliverables are substantively implemented and correctly wired. All five phase-17 commits exist in the git log (4e59923, ea75e0d, ebe4e03, 1a9af89, 5b46486).

---

_Verified: 2026-03-25T19:00:00Z_
_Verifier: Claude (gsd-verifier)_

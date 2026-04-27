# SuperBot — Project Notes for Claude Code

Slack bridge that runs as a systemd service on a GCP VM and processes Slack mentions through the Claude Agent SDK.

## Constants

| Thing | Value |
|---|---|
| Production VM | `superbot-vm` (zone `us-west1-a`) |
| Service unit | `superbot.service` |
| Service user | `bot` |
| Bot Slack user ID | `U0AN19JMTNV` |
| Smoke-test channel | `C08QJGAN6US` |
| Working dir on VM | `/home/bot/super_bot` (and `/home/bot/mic_transformer` for the agent) |
| Env file on VM | `/home/bot/.env` (loaded by systemd `EnvironmentFile=`) |
| Auth | `ANTHROPIC_API_KEY` in `/home/bot/.env` (no OAuth — see Auth Notes) |

## Verification (REQUIRED after every SuperBot change)

**Do not consider a SuperBot fix complete until the smoke test passes.** The only true verification is "real Slack message in, real Slack message out" — unit tests and offline harnesses are insufficient because they don't exercise the production VM, systemd env, or live `claude` subprocess.

### Slack client requirements

Smoke tests must be posted via a **user token** or the `mcp__claude_ai_Slack__slack_send_message` MCP tool, not via a bot token. SuperBot's `is_bot_message` guard (`bot/access_control.py`) filters any event with a `bot_id`, so `xoxb-` token posts never reach the agent and silently show up as `filtered_bot_message` in the journal.

Slack appends a `*Sent using* <@U0A3LP3CR8F|Claude>` context block when messages are posted via integrations (including the Claude Code MCP). As of the fix in `bot/handlers.py::_clean_message_text`, SuperBot now strips both labeled mentions and the `*Sent using*` footer before matching, so fast-path commands like `bot health` work from MCP-posted messages.

### Deep smoke (the only working path for me, ~30s–5min)

Steps:

1. Send a free-form mention via `mcp__claude_ai_Slack__slack_send_message`:
   - `channel_id`: `C08QJGAN6US`
   - `message`: `<@U0AN19JMTNV> what is 2 + 2` (or any short factual question)
   - Capture the returned message `ts`.
2. Poll the thread every ~30 seconds via `mcp__claude_ai_Slack__slack_read_thread` (channel `C08QJGAN6US`, `message_ts` = the captured ts) for up to 6 minutes. The agent path is slow because the bot creates a worktree per task.
3. Cross-check with logs to see if the task is alive or stuck:
   ```bash
   gcloud compute ssh superbot-vm --zone=us-west1-a \
     --command="sudo journalctl -u superbot --since '10 minutes ago' --no-pager | grep -E 'agent\.(run_end|run_start|generic_error)|heartbeat' | tail -20"
   ```
   `agent.run_end ... subtype=success` = pass. `subtype=error_internal` or `error_timeout` = fail.
4. **Pass criteria**: a final assistant reply appears in the thread (not just "Working on it"), `agent.run_end` shows `subtype=success`, and the answer is sensible. This exercises the full Claude Agent SDK auth path (the path that broke on 2026-04-07 when the OAuth token expired).

### Post-test cleanup

8. After smoke completes (pass or fail), post a single follow-up to the same thread (`slack_send_message` with `thread_ts` set):
   - On pass: `[smoke test passed]`
   - On fail: `[smoke test failed: <one-line reason>]`

This makes it visually obvious to humans in the channel that the noise was a Claude Code test, not a real incident.

### Offline pre-check (skip Slack)

For agent-stack changes, run the offline harness on the VM before doing the Slack smoke — it's faster and isolates the agent from Slack noise:

```bash
gcloud compute ssh superbot-vm --zone=us-west1-a \
  --command='sudo -u bot bash -c "set -a; . /home/bot/.env; set +a; cd /home/bot/super_bot && PYTHONPATH=. .venv/bin/python scripts/test_agent.py --timeout 60 \"say hi\""'
```

The `set -a; . /home/bot/.env; set +a;` prefix is required: `sudo -u bot bash` does not source `.env`, so without it the claude CLI dies with "Not logged in · Please run /login" even though `ANTHROPIC_API_KEY` is in the file. The prompt is a positional argument (no `--prompt` flag). `PYTHONPATH=.` is needed because `scripts/test_agent.py` imports `bot.agent`.

If this fails, fix the agent first — no point hitting Slack until the offline harness is green.

### Reading logs after a failure

```bash
gcloud compute ssh superbot-vm --zone=us-west1-a \
  --command="sudo journalctl -u superbot -n 200 --no-pager | grep -B2 -A10 -E 'agent\.(generic_error|process_error|run_start)|Fatal error|exit code 1'"
```

## Known issues to fix (surfaced by 2026-04-07 smoke test)

1. ~~Fast-path matcher should ignore Slack context-block footers.~~ **Fixed** in `bot/handlers.py::_clean_message_text` — strips labeled `<@U|label>` mentions and trailing `*Sent using*` blocks. Also resolves #2 (the same footer caused the is_code_task classifier to misfire).
2. ~~Worktree code-task classifier is over-eager on `bot health *Sent using*`.~~ **Resolved** by #1 (the footer no longer reaches the classifier).
3. ~~Heartbeat `last_activity` never advances past "Starting up..."~~ **Fixed** in `bot/progress.py::make_on_message` (PR #17) — any unrecognized ToolUseBlock now sets a generic "Running &lt;tool&gt;..." milestone, with `mcp__` prefix stripped. Also added a stopped-early rendering path so a partial-text fallback no longer ships under a green checkmark.
4. ~~Generic-Exception handler in `bot/agent.py` swallows real error details.~~ **Fixed** in commit 8b82321 — `_format_error_detail` now captures `repr(exc)`, chained `__cause__` / `__context__`, and adds a "DIAGNOSTIC" hint for the empty-stderr / "Check stderr output for details" signature. Regression coverage in `tests/test_agent_error_detail.py`.
5. ~~`thedotmack` plugin SessionEnd hook errors pollute journalctl.~~ **Resolved** on 2026-04-27 by `claude plugin uninstall claude-mem@thedotmack --scope user` on `superbot-vm`. The plugin had been installed at user scope but never actually fired in headless `claude --print` mode, so no journal pollution was observed in the 14 days before removal — uninstalled to eliminate the latent risk.

## VM firewall policy (mic_transformer)

The VM's `/home/bot/mic_transformer` checkout stays permanently on the `vm/accumulated-*` branch (currently `vm/accumulated-2026-04-21`), not `develop`. This is a deliberate "firewall" so VM-origin edits (bot-spawned tasks, manual fixes on the VM) cannot leak into `develop`.

**To sync the VM with the latest `develop`:**
```bash
gcloud compute ssh superbot-vm --zone=us-west1-a \
  --command='sudo -u bot bash -c "cd /home/bot/mic_transformer && git fetch origin && git merge origin/develop"'
```
Develop merges *in*, VM commits never PR up directly.

**To upstream a VM-origin commit**: cherry-pick it from `vm/accumulated-*` onto a fresh branch off `origin/develop` on the laptop, then open a normal PR. Never PR the whole accumulated branch.

## Auth Notes

As of 2026-04-07 the bot authenticates via `ANTHROPIC_API_KEY` (set in `/home/bot/.env`), not OAuth. The previous OAuth flow (`~/.claude/.credentials.json`) expired silently and caused all tasks to fail with an opaque "Command failed with exit code 1 / Check stderr output for details" error. The stale credentials file was moved to `.credentials.json.bak.<timestamp>`.

If auth fails again:
1. Verify `ANTHROPIC_API_KEY` is in `/home/bot/.env` and the env reaches the systemd process.
2. Test directly: `gcloud compute ssh superbot-vm --zone=us-west1-a --command='sudo -u bot bash -c "cd /home/bot/mic_transformer && echo hi | claude --print --permission-mode=bypassPermissions 2>&1"'` — should print a reply, not a 401.
3. If `.credentials.json` was somehow recreated and is winning over the env var, move it aside again.

## Agent capabilities on the VM

The agent runs with `cwd=/home/bot/mic_transformer` as user `bot` on `superbot-vm`. That VM has a GCP service account attached with Drive and GCS read access — Application Default Credentials resolve automatically via the metadata server, so `google.auth.default()` just works (no OAuth, no keyfile, no `gcloud auth login` needed).

### Known failure mode: Google Drive / Sheets URLs (observed 2026-04-21)

When given a `docs.google.com/spreadsheets/...` URL, the agent reaches for `WebFetch`, gets 401, and concludes "I have no credentials." That conclusion is wrong — the VM has ADC.

The correct path is documented in `mic_transformer/CLAUDE.md` → Google Drive: Drive API + ADC + openpyxl (for xlsx) or Drive export to CSV (for native Sheets). The Sheets API itself will 403 because our service account doesn't have domain-wide delegation for the `spreadsheets` scope — that's a dead end, always go through Drive.

If the agent reports "can't access that sheet," push back; it figures it out on the second try.

## Restarting the service

```bash
sudo systemctl restart superbot
```

Or use `scripts/restart_superbot.sh` (with optional `--pull` to pull latest code first).

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

### Important caveat: Slack MCP appends a footer

When Claude Code (me) sends a message via `mcp__claude_ai_Slack__slack_send_message`, Slack automatically appends a context block like `*Sent using* <@U0A3LP3CR8F|Claude>` to the message. After SuperBot strips the `<@bot>` mention, the prompt that reaches `bot/handlers.py` looks like `bot health *Sent using*` (not `bot health`).

Consequences:
- **Fast-path commands match exactly**, so anything I send via Slack MCP will NOT hit the fast path. Every smoke test from me will go through the full Claude Agent SDK, taking 30s–5min instead of <5s.
- **The code-task classifier in `bot/worktree.py`** also misfires on the footer text and creates an unnecessary worktree.

Until both are fixed, my smoke tests must use the Deep smoke procedure below — there is no working "Quick smoke" path for me. Humans typing in Slack directly do NOT get the footer, so the fast path still works for them.

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
  --command='sudo -u bot bash -c "cd /home/bot/super_bot && .venv/bin/python scripts/test_agent.py --prompt \"say hi\" --timeout 60"'
```

If this fails, fix the agent first — no point hitting Slack until the offline harness is green.

### Reading logs after a failure

```bash
gcloud compute ssh superbot-vm --zone=us-west1-a \
  --command="sudo journalctl -u superbot -n 200 --no-pager | grep -B2 -A10 -E 'agent\.(generic_error|process_error|run_start)|Fatal error|exit code 1'"
```

## Known issues to fix (surfaced by 2026-04-07 smoke test)

1. **Fast-path matcher should ignore Slack context-block footers.** When messages are sent via Slack MCP (or any client that adds a `context` block), SuperBot's mention-stripper preserves trailing markdown like `*Sent using*`, breaking exact-match commands like `bot health`. Fix in `bot/handlers.py` mention-stripping or `bot/fast_commands.py` matcher: trim trailing `*Sent using*...` and any `<@USERID>` patterns after the primary text.
2. **Worktree code-task classifier is over-eager.** "bot health *Sent using*" was misclassified as a code task and a worktree was created. Investigate `bot/worktree.py` keyword-matching — likely matching on a substring in the footer.
3. **Heartbeat `last_activity` never advances past "Starting up..."** when the agent runs tools without producing text blocks. The on_text callback in `bot/agent.py:154-165` only fires for `TextBlock`s; tool-only turns leave the heartbeat stale. Consider also tagging activity from `on_message` (ToolUseBlock).
4. **Generic-Exception handler in `bot/agent.py:200-229` swallows real error details.** Today's 401 surfaced as opaque "Command failed with exit code 1 / Check stderr output for details". Need to capture `repr(exc)` and any chained exception detail when `stderr_lines` is empty.
5. **`thedotmack` plugin SessionEnd hook errors** (Bun not installed) pollute journalctl. Either install bun or remove the plugin from `/home/bot/.claude/plugins/`.

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

# Phase 8: Response Timing — Context

## User Decisions

### Display Format
- **Italic footer line** on its own line at the end of the message
- Example: `_Completed in 2m 34s_`
- Consistent style for both success and error/timeout messages

### Time Format
- Always show minutes + seconds: `Xm Ys` (e.g. `0m 34s`, `2m 34s`, `10m 0s`)
- Never omit minutes even for short tasks

### Implementation Notes
- `handlers.py` already computes `duration_s` at line 102 — reuse this
- Pass `duration_s` to `progress.post_result()` as a new parameter
- `post_result()` appends the italic footer to all message types (completion, error, timeout)
- The footer goes after any PR/MR URL if present

### Files to Modify
- `bot/handlers.py` — pass elapsed time to `post_result`
- `bot/progress.py` — accept `duration_s`, format and append footer

"""
Standalone CLI harness for testing the agent stack without Slack.

Exercises bot/agent.py and bot/session_map.py directly, allowing
end-to-end validation of Claude Agent SDK integration, session
resumption, max-turns termination, and timeout behavior.

Usage:
    python scripts/test_agent.py "list files in the bot/ directory"
    python scripts/test_agent.py "what did you just find?" --thread-ts 12345.67890
    python scripts/test_agent.py "count from 1 to 100" --max-turns 2
    python scripts/test_agent.py "sleep for 15 minutes" --timeout 5
"""

import argparse
import asyncio
import sys

from bot.agent import run_agent_with_timeout
from bot import session_map


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="CLI test harness for the agent stack (no Slack dependency)",
    )
    parser.add_argument("prompt", help="Prompt to send to Claude")
    parser.add_argument(
        "--thread-ts",
        default="test-thread-001",
        help="Thread timestamp for session keying (default: test-thread-001)",
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        default=25,
        help="Maximum conversation turns (default: 25)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=1800,
        help="Wall-clock timeout in seconds (default: 1800)",
    )
    parser.add_argument(
        "--channel",
        default="C_TEST",
        help="Channel ID for session_map key (default: C_TEST)",
    )
    args = parser.parse_args()

    # Look up existing session
    existing_session = session_map.get(args.channel, args.thread_ts)
    if existing_session:
        print(f"Session: resuming {existing_session[:16]}")
    else:
        print("Session: new")

    # Run the agent
    result = await run_agent_with_timeout(
        args.prompt,
        existing_session,
        timeout_seconds=args.timeout,
        max_turns=args.max_turns,
    )

    # Persist session_id for future resumption
    if result["session_id"] is not None:
        session_map.set(args.channel, args.thread_ts, result["session_id"])

    # Print results
    subtype = result["subtype"]
    num_turns = result["num_turns"]
    print("=" * 60)
    print(f"Result ({subtype}, {num_turns} turns)")
    print("=" * 60)

    if result["result"] is not None:
        print(result["result"])
    else:
        # Show partial texts if available (timeout case)
        if result["partial_texts"]:
            print("(partial output captured before termination)")
            for i, text in enumerate(result["partial_texts"], 1):
                print(f"--- partial {i} ---")
                print(text)
        else:
            print("(no result captured)")

    # Continuation hints
    if subtype == "error_max_turns":
        print(
            f"\nReply with --thread-ts {args.thread_ts} to continue where I left off."
        )
    elif subtype == "error_timeout":
        print(f"\nTimed out. Reply with --thread-ts {args.thread_ts} to continue.")
    elif subtype == "error_cancelled":
        print("\nCancelled.")


if __name__ == "__main__":
    asyncio.run(main())

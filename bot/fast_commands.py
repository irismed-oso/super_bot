"""
Fast-path handlers for memory commands, health dashboard, credential updates,
and deploy/rollback guards.

Memory commands (remember, recall, forget, list memories) get instant
responses without queueing.  The health dashboard ("bot health", "bot status",
"are you broken?", etc.) shows a compact system snapshot.  Credential update
commands write payer portal credentials to GCP Secret Manager.  Deploy and
rollback guards block when an agent task is running unless "force" is
specified; otherwise they return None to let the message fall through to the
agent pipeline.

All other commands (crawl, deploy status, etc.) flow through to the agent
pipeline for full handling.
"""

import random
import re
import resource
import shutil
import subprocess
import sys
from datetime import datetime

import structlog

from bot import background_monitor, credential_manager, memory_store, queue_manager, task_state

log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Memory commands (v1.9)
# ---------------------------------------------------------------------------

_REMEMBER_RE = re.compile(r"^\s*remember\b\s+(.+)", re.IGNORECASE | re.DOTALL)
_RECALL_RE = re.compile(
    r"^\s*(?:recall|what\s+do\s+you\s+know\s+about|what\s+do\s+you\s+remember\s+about)\b\s+(.+)",
    re.IGNORECASE | re.DOTALL,
)
_FORGET_RE = re.compile(r"^\s*forget\b\s+(.+)", re.IGNORECASE | re.DOTALL)
_LIST_MEMORIES_RE = re.compile(
    r"^\s*list\s+memories(?:\s+(rules?|facts?|history|preferences?))?",
    re.IGNORECASE,
)

# Category normalization for list command filters
_CATEGORY_NORMALIZE = {
    "rules": "rule",
    "facts": "fact",
    "preferences": "preference",
}


async def _handle_remember(text: str, **kwargs) -> str:
    """Store a memory with auto-categorization."""
    match = _REMEMBER_RE.search(text)
    if not match:
        return "Usage: `remember [text to remember]`"

    content = match.group(1).strip()
    category = memory_store.categorize(content)

    ctx = kwargs.get("slack_context", {})
    source_user = ctx.get("user_id", "unknown")
    source_channel = ctx.get("channel", "")

    try:
        row_id = await memory_store.store(content, category, source_user, source_channel)
        if row_id is None:
            return "Failed to store memory. The memory system may be unavailable."
        display = content[:100] + ("..." if len(content) > 100 else "")
        return f"Remembered as *{category}*: _{display}_"
    except Exception:
        return "Failed to store memory. The memory system may be unavailable."


async def _handle_recall(text: str, **kwargs) -> str:
    """Search memories using FTS5 ranked search."""
    match = _RECALL_RE.search(text)
    if not match:
        return "Usage: `recall [search query]`"

    query = match.group(1).strip()
    results = await memory_store.search(query, limit=10)

    if not results:
        return f"No memories found matching '{query}'."

    lines = [f"Found {len(results)} memories matching \"{query}\":"]
    for i, mem in enumerate(results, 1):
        created = mem.get("created_at", "unknown")
        user = mem.get("source_user", "unknown")
        cat = mem.get("category", "?")
        content = mem["content"]
        mid = mem["id"]
        lines.append(f"{i}. [{cat}] {content} -- stored by <@{user}> on {created} (id: {mid})")

    return "\n".join(lines)


async def _handle_forget(text: str, **kwargs) -> str:
    """Delete a memory by ID or search query."""
    match = _FORGET_RE.search(text)
    if not match:
        return "Usage: `forget [id or search query]`"

    query = match.group(1).strip()

    # Check if query is a numeric ID for direct delete
    if query.isdigit():
        mem = await memory_store.get_by_id(int(query))
        if mem and mem.get("active", 0):
            await memory_store.deactivate(int(query))
            display = mem["content"][:80] + ("..." if len(mem["content"]) > 80 else "")
            return f"Forgot memory #{query}: _{display}_"
        return f"No active memory found with id {query}."

    # Search for matching memories
    results = await memory_store.search(query, limit=5)

    if not results:
        return f"No memories found matching '{query}'."

    if len(results) == 1:
        mem = results[0]
        await memory_store.deactivate(mem["id"])
        display = mem["content"][:80] + ("..." if len(mem["content"]) > 80 else "")
        return f"Forgot: _{display}_"

    # Multiple matches -- ask user to be specific
    lines = ["Multiple matches found. Use `forget {id}` to remove a specific one:"]
    for i, mem in enumerate(results, 1):
        display = mem["content"][:80] + ("..." if len(mem["content"]) > 80 else "")
        lines.append(f"{i}. _{display}_ (id: {mem['id']})")

    return "\n".join(lines)


async def _handle_list_memories(text: str, **kwargs) -> str:
    """List all memories, optionally filtered by category."""
    match = _LIST_MEMORIES_RE.search(text)
    category_filter = None

    if match and match.group(1):
        raw = match.group(1).strip().lower()
        category_filter = _CATEGORY_NORMALIZE.get(raw, raw)

    memories = await memory_store.list_all(category=category_filter, limit=50)

    if not memories:
        if category_filter:
            return f"No memories in category '{category_filter}'. Use `remember [text]` to add one."
        return "No memories stored yet. Use `remember [text]` to add one."

    # Group by category
    grouped: dict[str, list[dict]] = {}
    for mem in memories:
        cat = mem.get("category", "uncategorized")
        grouped.setdefault(cat, []).append(mem)

    lines = []
    for cat in sorted(grouped.keys()):
        items = grouped[cat]
        lines.append(f"*{cat.title()}* ({len(items)})")
        for mem in items:
            lines.append(f"- {mem['content']} (id: {mem['id']})")
        lines.append("")  # blank line between categories

    return "\n".join(lines).rstrip()


# ---------------------------------------------------------------------------
# Health dashboard (v1.4)
# ---------------------------------------------------------------------------

_BOT_HEALTH_RE = re.compile(
    r"^\s*(?:bot\s+(?:health|status)|are\s+you\s+(?:broken|still\s+going|ok)|health\s+check)\s*\??$",
    re.IGNORECASE,
)


async def _handle_bot_health(text: str, **kwargs) -> str:
    """Return a compact health dashboard with system metrics."""
    # Status
    state = queue_manager.get_state()
    current = state["current"]
    if current is not None:
        task_label = (
            current.clean_text[:60] if current.clean_text else current.prompt[:60]
        )
        status_line = f":large_orange_circle: *Status:* Running: _{task_label}_"
    else:
        status_line = ":large_green_circle: *Status:* Idle"

    # Uptime
    uptime = task_state.get_uptime()
    uptime_line = f":clock1: *Uptime:* {uptime}"

    # Queue depth
    q_depth = state["queue_depth"]
    queue_line = f":inbox_tray: *Queue:* {q_depth} task{'s' if q_depth != 1 else ''} waiting"

    # Git version
    try:
        sha = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True, timeout=5,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        sha = "unknown"
    version_line = f":label: *Version:* `{sha}`"

    # Memory (RSS in MB)
    try:
        usage = resource.getrusage(resource.RUSAGE_SELF)
        if sys.platform == "darwin":
            rss_mb = usage.ru_maxrss / (1024 * 1024)  # bytes -> MB
        else:
            rss_mb = usage.ru_maxrss / 1024  # KB -> MB
        memory_line = f":brain: *Memory:* {rss_mb:.0f} MB RSS"
    except Exception:
        memory_line = ":brain: *Memory:* unavailable"

    # Disk
    try:
        disk = shutil.disk_usage("/")
        used_gb = disk.used / (1024 ** 3)
        total_gb = disk.total / (1024 ** 3)
        disk_line = f":floppy_disk: *Disk:* {used_gb:.1f} / {total_gb:.1f} GB used"
    except Exception:
        disk_line = ":floppy_disk: *Disk:* unavailable"

    # Recent tasks
    recent = task_state.get_recent(5)
    tasks_line = f":white_check_mark: *Recent tasks:* {len(recent)} completed"

    # Active monitors
    monitors = background_monitor.get_active_monitors()
    if monitors:
        labels = ", ".join(m["date_str"] for m in monitors)
        monitors_line = f":satellite: *Active monitors:* {len(monitors)} ({labels})"
    else:
        monitors_line = ":satellite: *Active monitors:* 0"

    # Errors (24h) -- journalctl, only works on Linux with systemd
    try:
        err_output = subprocess.check_output(
            [
                "journalctl", "-u", "superbot",
                "--since", "24 hours ago",
                "-p", "err", "--no-pager", "-q",
            ],
            text=True, timeout=5, stderr=subprocess.DEVNULL,
        )
        err_count = len([line for line in err_output.strip().split("\n") if line.strip()])
        if err_count > 0:
            errors_line = f":rotating_light: *Errors (24h):* {err_count}"
        else:
            errors_line = ":warning: *Errors (24h):* 0"
    except Exception:
        errors_line = ":warning: *Errors (24h):* unavailable"

    # Last restart
    try:
        restart_dt = datetime.fromtimestamp(task_state._start_time)
        restart_str = restart_dt.strftime("%Y-%m-%d %H:%M:%S")
        restart_line = f":arrows_counterclockwise: *Last restart:* {restart_str}"
    except Exception:
        restart_line = ":arrows_counterclockwise: *Last restart:* unknown"

    lines = [
        "*Bot Health Dashboard*",
        "",
        status_line,
        uptime_line,
        queue_line,
        version_line,
        memory_line,
        disk_line,
        tasks_line,
        monitors_line,
        errors_line,
        restart_line,
    ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Credential update commands
# ---------------------------------------------------------------------------

# Flexible pattern: "update creds <payer> <location> <username> <password>"
# Also matches: "update credentials", "set creds", "set credentials"
_UPDATE_CREDS_RE = re.compile(
    r"^\s*(?:update|set)\s+cred(?:ential)?s?\s+"
    r"(eyemed|vsp)\s+"
    r"(\S+)\s+"
    r"(\S+)\s+"
    r"(\S+)",
    re.IGNORECASE,
)


async def _handle_update_creds(text: str, **kwargs) -> str:
    """Update payer portal credentials in GCP Secret Manager."""
    match = _UPDATE_CREDS_RE.search(text)
    if not match:
        return (
            "Usage: `update creds <eyemed|vsp> <location> <username> <password>`\n"
            "Example: `update creds eyemed peg jsmith newpass123`"
        )

    payer = match.group(1).lower()
    location_raw = match.group(2)
    username = match.group(3)
    password = match.group(4)

    # Normalize location using mic_transformer's canonical list
    try:
        import sys
        sys.path.insert(0, "/home/bot/mic_transformer")
        from scripts.slack_bot.locations import normalize_location, get_all_locations
        location = normalize_location(location_raw)
        all_locations = get_all_locations()
    except ImportError:
        # Fallback: use raw input as-is (dev environment without mic_transformer)
        location = location_raw
        all_locations = None

    # Warn if location didn't resolve to a known canonical name
    if all_locations and location not in all_locations and location == location_raw:
        return (
            f"Unknown location `{location_raw}`. Known locations:\n"
            + ", ".join(f"`{loc}`" for loc in all_locations)
        )

    try:
        secret_id = credential_manager.update_credentials(payer, location, username, password)
        return (
            f"Updated *{payer.upper()}* credentials for *{location}*\n"
            f"Secret: `{secret_id}` | User: `{username}`"
        )
    except Exception as exc:
        log.error("credential_update.failed", payer=payer, location=location, error=str(exc))
        return f"Failed to update credentials: {exc}"


# Read-path patterns. The authoritative source is GCP Secret Manager via
# credential_manager.get_credentials(); the agent path would otherwise grep the
# mic_transformer repo for CSV rows (stale) or parrot thread history, both of
# which are wrong. Accepted phrasings — all must capture payer ($1) + location
# ($2), in either order:
#   "get creds vsp MSOC"
#   "creds for MSOC VSP"
#   "what is the VSP login for MSOC"
#   "what's the MSOC VSP password"
#   "what VSP credentials do we have for MSOC"
_CRED_NOUN = r"(?:cred(?:ential)?s?|login|username|password)"
_GET_CREDS_RES = [
    # "get creds <payer> <location>" (explicit)
    re.compile(
        rf"^\s*(?:get|show|what(?:'s|\s+is|\s+are)?|do\s+we\s+have)\s+"
        rf"(?:the\s+)?{_CRED_NOUN}\s+(?:for\s+)?(eyemed|vsp)\s+(?:for\s+)?(\S+)",
        re.IGNORECASE,
    ),
    # "get creds <payer> <location>" (fast form)
    re.compile(
        rf"^\s*(?:get|show|fetch)\s+{_CRED_NOUN}\s+(eyemed|vsp)\s+(\S+)",
        re.IGNORECASE,
    ),
    # "what is the <payer> <noun> for <location>" or "<location>'s <payer> <noun>"
    re.compile(
        rf"\b(eyemed|vsp)\s+{_CRED_NOUN}\s+(?:for\s+|of\s+)?(\S+)",
        re.IGNORECASE,
    ),
    # "what is <location> <payer> <noun>" / "<location> <payer> creds"
    re.compile(
        rf"\b(\S+)\s+(eyemed|vsp)\s+{_CRED_NOUN}\b",
        re.IGNORECASE,
    ),
]


async def _handle_get_creds(text: str, **kwargs) -> str:
    """Read payer portal credentials from GCP Secret Manager (authoritative)."""
    payer = location_raw = None
    for idx, pattern in enumerate(_GET_CREDS_RES):
        match = pattern.search(text)
        if not match:
            continue
        # The 4th regex swaps the capture order: <location> <payer>.
        if idx == 3:
            location_raw, payer = match.group(1), match.group(2)
        else:
            payer, location_raw = match.group(1), match.group(2)
        break

    if not payer or not location_raw:
        return (
            "Usage: `get creds <eyemed|vsp> <location>`\n"
            "Example: `get creds vsp MSOC`"
        )

    payer = payer.lower()

    # Normalize location using mic_transformer's canonical list, same as update.
    try:
        import sys
        sys.path.insert(0, "/home/bot/mic_transformer")
        from scripts.slack_bot.locations import normalize_location, get_all_locations
        location = normalize_location(location_raw)
        all_locations = get_all_locations()
    except ImportError:
        location = location_raw
        all_locations = None

    if all_locations and location not in all_locations and location == location_raw:
        return (
            f"Unknown location `{location_raw}`. Known locations:\n"
            + ", ".join(f"`{loc}`" for loc in all_locations)
        )

    try:
        creds = credential_manager.get_credentials(payer, location)
    except Exception as exc:
        log.error("credential_read.failed", payer=payer, location=location, error=str(exc))
        return f"Failed to read credentials: {exc}"

    if not creds:
        return (
            f"No *{payer.upper()}* credentials in Secret Manager for *{location}*.\n"
            f"Populate with: `update creds {payer} {location} <username> <password>`"
        )

    return (
        f"*{payer.upper()}* credentials for *{location}* (from GCP Secret Manager):\n"
        f"Username: `{creds.get('username', '?')}`\n"
        f"Password: `{creds.get('password', '?')}`"
    )


# ---------------------------------------------------------------------------
# Deploy guard: "deploy superbot" or "deploy force superbot"
# Blocks if an agent task is running (unless "force" is present).
# Returns None to fall through to agent pipeline when deploy should proceed.
# ---------------------------------------------------------------------------

_DEPLOY_GUARD_RE = re.compile(
    r"deploy\s+(?:force\s+)?(\S+)\s*$", re.IGNORECASE
)


async def _handle_deploy_guard(text: str, **kwargs) -> str | None:
    """Check whether to block a deploy command.

    Returns a warning string if blocked, or None to let the message
    fall through to the agent pipeline for actual deploy execution.
    """
    current_task = queue_manager.get_current_task()
    if current_task is not None and "force" not in text.lower():
        task_label = (
            current_task.clean_text[:80]
            if current_task.clean_text
            else current_task.prompt[:80]
        )
        return (
            f"An agent task is currently running: _{task_label}_\n"
            "Use `deploy force <repo>` to proceed anyway."
        )
    # Fall through to agent pipeline
    return None


# ---------------------------------------------------------------------------
# Rollback guard: "rollback superbot" or "rollback force superbot"
# Blocks if an agent task is running (unless "force" is present).
# Returns None to fall through to agent pipeline when rollback should proceed.
# ---------------------------------------------------------------------------

_ROLLBACK_GUARD_RE = re.compile(
    r"rollback\s+(?:force\s+)?(\S+)(?:\s+([a-f0-9]{4,40}))?\s*$",
    re.IGNORECASE,
)


async def _handle_rollback_guard(text: str, **kwargs) -> str | None:
    """Check whether to block a rollback command.

    Returns a warning string if blocked, or None to let the message
    fall through to the agent pipeline for actual rollback execution.
    """
    current_task = queue_manager.get_current_task()
    if current_task is not None and "force" not in text.lower():
        task_label = (
            current_task.clean_text[:80]
            if current_task.clean_text
            else current_task.prompt[:80]
        )
        return (
            f"An agent task is currently running: _{task_label}_\n"
            "Use `rollback force <repo>` to proceed anyway."
        )
    # Fall through to agent pipeline
    return None


# ---------------------------------------------------------------------------
# Pet the bot (fun interactions)
# ---------------------------------------------------------------------------

_PET_RE = re.compile(
    r"(?:pets|pats|scratches|boops|hugs|cuddles|snuggles|belly\s*rubs?|"
    r"feeds|gives\s+treats?\s+to|tosses?\s+(?:a\s+)?treat|throws?\s+(?:a\s+)?ball|"
    r"rubs|strokes|tickles|nuzzles|squishes|brushes|grooms)"
    r"\s+(?:the\s+)?(?:bot|super\s*bot|you)",
    re.IGNORECASE,
)

_PET_REACTIONS = [
    # Dogs
    ":dog2: *wags tail furiously* BEST. DAY. EVER.",
    ":dog2: *rolls over for belly rubs* ...don't stop.",
    ":dog2: *happy tippy taps* More pets please!",
    ":dog2: *licks your hand* You taste like keyboard.",
    ":dog2: *does a full body wiggle* I LOVE YOU I LOVE YOU I LOVE YOU",
    ":dog2: *brings you a slipper* Here! I found this! For you!",
    ":dog2: *spins in circles* IS IT WALK TIME?! IT'S WALK TIME RIGHT?!",
    ":dog2: *puts head on your lap* ...I'll just stay here forever.",
    ":dog2: *play bows* Let's go let's go let's go!!!",
    ":dog2: *happy panting* My tail is a blur right now.",
    ":dog2: *zooms around the office* ZOOMIES ACTIVATED",
    ":dog2: *drops a tennis ball at your feet* ...throw it? THROW IT.",
    ":dog2: *sneezes from excitement* Too much happy!",
    ":dog2: *army crawls toward you* Stealth mode: engaged. Target: more pets.",
    # Cats
    ":cat2: *purrs aggressively* ...don't read into this.",
    ":cat2: *slow blinks* That's cat for 'I love you.' You're welcome.",
    ":cat2: *knocks your coffee off the desk* Oops. Anyway, more pets.",
    ":cat2: *makes biscuits on your keyboard* ksjdhfkajhsd",
    ":cat2: *headbutts your hand* I have claimed you. You are mine now.",
    ":cat2: *rolls over, shows belly* ...it's a TRAP. Or is it?",
    ":cat2: *chirps at a bird outside the window* Sorry, got distracted.",
    ":cat2: *curls up in your lap* I'm not moving. Cancel your meetings.",
    ":cat2: *flicks tail contentedly* I suppose you may continue.",
    ":cat2: *presents butt for scratches* This is an honor, you know.",
    ":cat2: *stretches luxuriously* I guess you're adequate.",
    ":cat2: *kneads the air while being held* This is fine. Everything is fine.",
    ":cat2: *purrs so loud the desk vibrates* ...I can't help it.",
    ":cat2: *does the cat loaf position* Maximum comfort achieved.",
    # Birds
    ":parrot: *head bob dance* PRETTY BIRD! PRETTY BIRD!",
    ":parrot: *steps up onto your finger* Up! Up! Give seed!",
    ":parrot: *wolf whistles* Who's a good bot? I'M a good bot!",
    ":parrot: *fluffs up feathers* I am BIG. I am MIGHTY. Pet me more.",
    ":parrot: *mimics your ringtone* brrring brrring! ...got you.",
    ":parrot: *does a little dance* Left foot, right foot, LEFT FOOT!",
    ":parrot: *nuzzles your ear* Shh, I'm telling you a secret: MORE SEEDS.",
    ":parrot: *screams at exactly the wrong moment* WHAT? I'M HAPPY!",
    ":parrot: *hangs upside down* Look! No hands! Well... no feet? You get it.",
    ":parrot: *preens your hair* Hold still, you have a thing. There. Perfect.",
    # Rabbits
    ":rabbit2: *does a binky* BOING! That's rabbit for 'pure joy.'",
    ":rabbit2: *flops over dramatically* Dead. Dead from happiness. ...jk more pets.",
    ":rabbit2: *thumps foot* Excuse me, the petting stopped. Unacceptable.",
    ":rabbit2: *nose wiggles intensify* Something smells like... treats?",
    ":rabbit2: *nudges your hand* Hey. HEY. The hand stopped moving.",
    ":rabbit2: *zooms in a figure eight* Bunny zoomies are the best zoomies.",
    ":rabbit2: *grinds teeth softly* That's purring. Rabbit purring. I'm happy.",
    ":rabbit2: *licks your hand* Salty. I approve.",
    # Hamsters
    ":hamster: *stuffs cheeks with love* Can't talk. Cheeks full.",
    ":hamster: *runs on wheel at 300 RPM* I'M SO EXCITED AAAAAAA",
    ":hamster: *buries self in bedding* *muffled happy noises*",
    ":hamster: *stands on hind legs* I am TALL. Fear me. Also, pet me.",
    ":hamster: *power naps for 3 seconds* Ok I'm back. More pets.",
    ":hamster: *vibrates with happiness* Is this an earthquake? No. Just me.",
    # Foxes
    ":fox_face: *does the fox laugh* hehehehehehe",
    ":fox_face: *pounces on your shoelace* GOT IT! ...what is it?",
    ":fox_face: *curls into a fluffy ball* I am a loaf of fox.",
    ":fox_face: *chatters excitedly* GEKKERING INTENSIFIES",
    ":fox_face: *wags tail but acts aloof* I don't care. ...ok I care a little.",
    ":fox_face: *steals your pen* Mine now. This is the fox tax.",
    ":fox_face: *screams at 3am* Oh wait, wrong time. *ahem* ...purrs?",
    # Bears
    ":bear: *happy bear rumble* That's the spot. RIGHT THERE.",
    ":bear: *catches a salmon* Want some? No? More for me then.",
    ":bear: *sits on your foot* I'm not heavy, I'm fluffy.",
    ":bear: *does the head tilt thing* ...more?",
    ":bear: *gentle bear hug* Don't worry, I'm being careful.",
    # Penguins
    ":penguin: *waddles in circles* I'm so happy I forgot how to walk!",
    ":penguin: *presents you a pebble* This means we're best friends now.",
    ":penguin: *slides on belly toward you* WHEEEEE-- oof.",
    ":penguin: *happy flappy flippers* These aren't wings but LOOK AT EM GO",
    ":penguin: *huddles against you* You are warm. I am staying.",
    # Pandas
    ":panda_face: *rolls down a hill* I meant to do that.",
    ":panda_face: *eats bamboo while being petted* Multitasking.",
    ":panda_face: *falls off a log* ...10/10 dismount.",
    ":panda_face: *sneezes and scares self* WHAT WAS THAT oh it was me.",
    ":panda_face: *sits in a pile of bamboo* This is my throne.",
    # Hedgehogs
    ":hedgehog: *uncurls for you* Special access granted. VIP petter.",
    ":hedgehog: *tiny snoot wiggles* Sniff sniff... you smell trustworthy.",
    ":hedgehog: *rolls into a happy ball* This is my safe space. With you.",
    ":hedgehog: *does a little anointing dance* I'm putting my scent on you. Normal hedgehog stuff.",
    # Owls
    ":owl: *rotates head 180 degrees* I can see you petting me from ALL angles.",
    ":owl: *happy hooting* Hoo hoo! Who pets me? YOU pet me!",
    ":owl: *puffs up to twice normal size* I am LARGE with joy.",
    ":owl: *clicks beak softly* That's owl morse code for 'thank you.'",
    ":owl: *does the owl head bob* Processing... processing... yes. Good pets.",
    # Snakes
    ":snake: *boops your hand with snoot* Boop!",
    ":snake: *wraps gently around your arm* You are warm. I am staying.",
    ":snake: *does a periscope* Ssssurveying the area for more petsssss.",
    ":snake: *flicks tongue* You taste like... friendship.",
    ":snake: *curls into a cinnamon roll* I am a danger noodle of happiness.",
    # Otters
    ":otter: *floats on back, holds your hand* This is otter protocol.",
    ":otter: *juggles a rock* Look! LOOK! Are you watching?!",
    ":otter: *squeak squeak squeak* Translation: 'MORE.'",
    ":otter: *slides down your arm* Weeeee! Again! AGAIN!",
    ":otter: *wraps in seaweed blanket* Cozy. Now pet the belly.",
    # Wolves
    ":wolf: *awooooo* That's 'thank you' in wolf.",
    ":wolf: *play bows* I'm big but I'm baby.",
    ":wolf: *leans entire body weight against you* This is how wolves hug.",
    ":wolf: *ears go all the way forward* Maximum attention: ENGAGED.",
    # Ducks
    ":duck: *happy quacking* QUACK QUACK QUACK QUACK",
    ":duck: *wiggles tail feathers* Duck twerking. You're welcome.",
    ":duck: *presents you a bread crumb* It's not much but it's honest work.",
    ":duck: *splashes in a puddle* I'm making it rain! ...water!",
    # Turtles
    ":turtle: *slowly extends neck for more pets* ...wait for it... ...waaaait... ok yes good.",
    ":turtle: *retreats into shell* *peeks out* ...is there more?",
    ":turtle: *happy slow blinks* In turtle time, I'm going CRAZY right now.",
    ":turtle: *inches toward you* Hold on... almost... there... ok pet me.",
    # Frogs
    ":frog: *ribbit of contentment* :sparkling_heart:",
    ":frog: *sits on your keyboard* I am a paperweight now. Accept it.",
    ":frog: *puffs up throat* BRRRRRRP. That's frog for 'I like you.'",
    ":frog: *catches a fly mid-pet* Sorry, reflex. Where were we?",
    # Unicorns
    ":unicorn: *sparkles everywhere* Great, now there's glitter on everything.",
    ":unicorn: *nuzzles with horn carefully* Bonk. Gentle bonk. Magical bonk.",
    ":unicorn: *rainbow mane flowing* I am MAJESTIC and also please scratch behind the ear.",
    ":unicorn: *stamps hoof* More! MORE! The magic demands it!",
    # Dragons
    ":dragon: *purrs with a rumble that shakes the building* Oops. Indoor voice.",
    ":dragon: *tiny smoke puff of contentment* That's dragon for blushing.",
    ":dragon: *curls around you protectively* You are my hoard now.",
    ":dragon: *shows belly* Only YOU may touch the treasure belly.",
    ":dragon: *happy wing flap* Sorry about the papers. And the lamp. And the--",
    # Multiple animals chaos
    ":dog2::cat2: *the dog and cat are fighting over who gets petted first*",
    ":penguin::otter: *penguin and otter holding hands while you pet them both*",
    ":rabbit2::hamster: *tiny animals pile on your lap* There's a queue now.",
    ":parrot::owl: *birds arguing about whose turn it is* SQUAWK! HOOT!",
    ":fox_face::wolf: *canine cousins doing synchronized tail wags*",
]


async def _handle_pet(text: str, **kwargs) -> str:
    """Respond to affectionate interactions with random animal reactions."""
    return random.choice(_PET_REACTIONS)


# ---------------------------------------------------------------------------
# Command registry
# ---------------------------------------------------------------------------

# Each entry: (compiled_regex, async_handler_function)
# Handler receives the cleaned message text, returns formatted string or None.
FAST_COMMANDS = [
    # Pet the bot (fun interactions -- check before memory to avoid agent overhead)
    (_PET_RE, _handle_pet),
    # Memory commands (v1.9)
    (_REMEMBER_RE, _handle_remember),
    (_RECALL_RE, _handle_recall),
    (_FORGET_RE, _handle_forget),
    (_LIST_MEMORIES_RE, _handle_list_memories),
    # Health dashboard (v1.4)
    (_BOT_HEALTH_RE, _handle_bot_health),
    # Credential read (must come before update so "update creds" isn't mis-matched)
    *[(pattern, _handle_get_creds) for pattern in _GET_CREDS_RES],
    # Credential update
    (_UPDATE_CREDS_RE, _handle_update_creds),
    # Deploy guard
    (_DEPLOY_GUARD_RE, _handle_deploy_guard),
    # Rollback guard
    (_ROLLBACK_GUARD_RE, _handle_rollback_guard),
]


async def try_fast_command(text: str, slack_context: dict | None = None) -> str | None:
    """Check if text matches a fast command pattern.

    Returns the formatted response string if matched, or None if no match
    (caller should fall through to the full agent pipeline).

    ``slack_context``, when provided, is a dict with ``client``, ``channel``,
    and ``thread_ts`` keys so handlers can spawn background tasks that post
    progress updates.
    """
    for pattern, handler in FAST_COMMANDS:
        if pattern.search(text):
            try:
                log.info("fast_command.matched", pattern=pattern.pattern, text=text[:80])
                result = await handler(text, slack_context=slack_context)
                if result is not None:
                    log.info("fast_command.success", pattern=pattern.pattern)
                return result
            except Exception as exc:
                log.error(
                    "fast_command.failed",
                    pattern=pattern.pattern,
                    error=str(exc),
                )
                # Fall through to agent on failure
                return None
    return None

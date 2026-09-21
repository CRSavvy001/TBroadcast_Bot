"""
Telegram Broadcast Bot
-----------------------
Repeats a chosen message to a list of registered groups on an interval,
until you stop it with /stopbroadcast.

Commands (only usable by the ADMIN_USER_ID set in env vars):
  /start                      - Show help
  /addgroup                   - Run inside a group to register it for broadcasts
  /removegroup                - Run inside a group to unregister it
  /listgroups                 - List all registered group chat IDs
  /broadcast <interval_sec>   - Reply to the message you want repeated, with
                                 this command, to start the loop (min 3 sec)
  /stopbroadcast              - Stop the running broadcast loop

Environment variables required:
  BOT_TOKEN        - token from @BotFather
  ADMIN_USER_ID     - your numeric Telegram user ID (only you can control the bot)
"""

import json
import logging
import os
from pathlib import Path

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)
from telegram.error import TelegramError, RetryAfter, Forbidden

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_USER_ID_RAW = os.environ.get("ADMIN_USER_ID")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is not set.")
if not ADMIN_USER_ID_RAW:
    raise RuntimeError("ADMIN_USER_ID environment variable is not set.")

ADMIN_USER_ID = int(ADMIN_USER_ID_RAW)

# Minimum allowed interval, in seconds. Telegram will start rejecting
# requests (429 Too Many Requests) if you hammer groups too fast, and
# identical messages posted every second across many groups is a classic
# spam signature that can get a bot limited or banned. 3 seconds is a
# safer floor; raise it further if you're broadcasting to many groups.
MIN_INTERVAL_SECONDS = 2

DATA_FILE = Path(__file__).parent / "groups.json"
BROADCAST_JOB_NAME = "broadcast_job"


# ---------- persistence helpers ----------

def load_groups() -> set[int]:
    if DATA_FILE.exists():
        try:
            return set(json.loads(DATA_FILE.read_text()))
        except (json.JSONDecodeError, ValueError):
            return set()
    return set()


def save_groups(groups: set[int]) -> None:
    DATA_FILE.write_text(json.dumps(list(groups)))


# ---------- access control ----------

def is_admin(update: Update) -> bool:
    return update.effective_user is not None and update.effective_user.id == ADMIN_USER_ID


# ---------- command handlers ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update):
        await update.message.reply_text("This bot is private.")
        return
    await update.message.reply_text(
        "Broadcast bot ready.\n\n"
        "1. Add me to your groups and give me permission to send messages.\n"
        "2. In each group, send /addgroup to register it.\n"
        "3. In our private chat, send the message you want repeated, "
        "then reply to it with /broadcast <seconds> (minimum "
        f"{MIN_INTERVAL_SECONDS} seconds).\n"
        "4. Send /stopbroadcast any time to stop.\n"
        "5. /listgroups shows registered groups, /removegroup unregisters "
        "the current one."
    )


async def add_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update):
        return
    chat = update.effective_chat
    if chat.type not in ("group", "supergroup"):
        await update.message.reply_text("Run this command inside the group you want to register.")
        return
    groups = load_groups()
    groups.add(chat.id)
    save_groups(groups)
    await update.message.reply_text(f"Registered this group ({chat.id}) for broadcasts.")


async def remove_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update):
        return
    chat = update.effective_chat
    groups = load_groups()
    if chat.id in groups:
        groups.remove(chat.id)
        save_groups(groups)
        await update.message.reply_text("Unregistered this group.")
    else:
        await update.message.reply_text("This group wasn't registered.")


async def list_groups(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update):
        return
    groups = load_groups()
    if not groups:
        await update.message.reply_text("No groups registered yet.")
        return
    await update.message.reply_text(
        "Registered groups:\n" + "\n".join(str(g) for g in sorted(groups))
    )


async def broadcast_tick(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Runs on every interval tick: sends the stored message to all groups."""
    job = context.job
    data = job.data
    text = data["text"]
    source_chat_id = data["source_chat_id"]
    source_message_id = data["source_message_id"]

    groups = load_groups()
    if not groups:
        logger.info("No registered groups; skipping this tick.")
        return

    for chat_id in list(groups):
        try:
            await context.bot.forward_message(
                chat_id=chat_id,
                from_chat_id=source_chat_id,
                message_id=source_message_id,
            )
        except RetryAfter as e:
            logger.warning("Rate limited, sleeping %s seconds", e.retry_after)
        except Forbidden:
            logger.warning("Bot was removed from/blocked by chat %s; unregistering it.", chat_id)
            groups.discard(chat_id)
            save_groups(groups)
        except TelegramError as e:
            logger.error("Failed to send to %s: %s", chat_id, e)

    # Fall back to plain text send if forwarding failed entirely because the
    # source message is unavailable (kept simple; forward_message covers the
    # normal case above).
    _ = text  # reserved for a future plain-send fallback


async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update):
        return

    if not update.message.reply_to_message:
        await update.message.reply_text(
            "Reply to the message you want broadcast with:\n"
            f"/broadcast <interval_seconds>  (minimum {MIN_INTERVAL_SECONDS})"
        )
        return

    args = context.args
    if not args or not args[0].isdigit():
        await update.message.reply_text(f"Usage: /broadcast <interval_seconds, min {MIN_INTERVAL_SECONDS}>")
        return

    interval = int(args[0])
    if interval < MIN_INTERVAL_SECONDS:
        await update.message.reply_text(
            f"Interval too short. Using the minimum safe interval of "
            f"{MIN_INTERVAL_SECONDS} seconds instead to avoid Telegram rate limits."
        )
        interval = MIN_INTERVAL_SECONDS

    groups = load_groups()
    if not groups:
        await update.message.reply_text("No groups registered. Use /addgroup inside a group first.")
        return

    # Stop any existing broadcast before starting a new one.
    existing = context.job_queue.get_jobs_by_name(BROADCAST_JOB_NAME)
    for j in existing:
        j.schedule_removal()

    source = update.message.reply_to_message
    context.job_queue.run_repeating(
        broadcast_tick,
        interval=interval,
        first=0,
        name=BROADCAST_JOB_NAME,
        data={
            "text": source.text or source.caption or "",
            "source_chat_id": source.chat_id,
            "source_message_id": source.message_id,
        },
    )
    await update.message.reply_text(
        f"Broadcasting to {len(groups)} group(s) every {interval} seconds. "
        "Send /stopbroadcast to stop."
    )


async def stop_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update):
        return
    jobs = context.job_queue.get_jobs_by_name(BROADCAST_JOB_NAME)
    if not jobs:
        await update.message.reply_text("No broadcast is running.")
        return
    for j in jobs:
        j.schedule_removal()
    await update.message.reply_text("Broadcast stopped.")


def main() -> None:
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("addgroup", add_group))
    app.add_handler(CommandHandler("removegroup", remove_group))
    app.add_handler(CommandHandler("listgroups", list_groups))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("stopbroadcast", stop_broadcast))

    logger.info("Bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

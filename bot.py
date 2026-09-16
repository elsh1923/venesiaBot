"""
Anonymous Story Bot
--------------------
People send a story/message to the bot -> it is forwarded to the owner
WITHOUT revealing who sent it (no name, no username, no user ID visible
in the owner's chat).

The owner can reply to that message (using Telegram's native "reply"
feature) and the bot will deliver the reply back to the original sender,
still without exposing the owner's personal account.

How anonymity works:
- We use `copy_message` instead of `forward_message`. Telegram's forward
  feature stamps "Forwarded from <name>" on the message - copy_message
  does NOT do that, it just clones the content.
- We keep a small local database mapping:
      (message_id of the copy in the owner's chat) -> (sender's chat_id)
  so that when the owner replies to that specific message, we know who
  to send the reply back to - without ever printing that ID anywhere
  the owner can see it.
- The database persists to disk (SQLite) so restarts don't lose the
  mapping and break "reply" functionality for older stories.

Environment variables required:
  BOT_TOKEN   - token from @BotFather
  OWNER_ID    - your personal Telegram numeric user ID (get it from
                @userinfobot). Only messages from this ID are treated
                as "owner replies"; everyone else is treated as an
                anonymous sender.

Run:
  pip install -r requirements.txt
  export BOT_TOKEN=xxxx
  export OWNER_ID=123456789
  python3 bot.py
"""

import asyncio
import logging
import os
import sqlite3
from contextlib import closing

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    CommandHandler,
    filters,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ["BOT_TOKEN"]
OWNER_ID = int(os.environ["OWNER_ID"])
DB_PATH = os.environ.get("DB_PATH", "mapping.db")
CHANNEL_ID = os.environ.get("CHANNEL_ID", "@Veni212121")


def db_init():
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.execute("PRAGMA journal_mode=WAL")  # safer concurrent access
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS mapping (
                owner_message_id INTEGER PRIMARY KEY,
                sender_chat_id   INTEGER NOT NULL,
                message_text     TEXT
            )
            """
        )
        # Migrate existing DB: add message_text column if missing
        try:
            conn.execute("ALTER TABLE mapping ADD COLUMN message_text TEXT")
        except sqlite3.OperationalError:
            pass  # Column already exists
        conn.commit()


def db_save(owner_message_id: int, sender_chat_id: int, message_text: str = None):
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO mapping (owner_message_id, sender_chat_id, message_text) VALUES (?, ?, ?)",
            (owner_message_id, sender_chat_id, message_text),
        )
        conn.commit()


def db_lookup(owner_message_id: int):
    """Returns (sender_chat_id, message_text) or (None, None)."""
    with closing(sqlite3.connect(DB_PATH)) as conn:
        row = conn.execute(
            "SELECT sender_chat_id, message_text FROM mapping WHERE owner_message_id = ?",
            (owner_message_id,),
        ).fetchone()
        return (row[0], row[1]) if row else (None, None)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == OWNER_ID:
        await update.message.reply_text(
            "ቦቱ እየሠራ ነው ✅\n\n"
            "📩 ታሪኮች ሲደርሱ ከዚህ ይታያሉ።\n"
            "\u2014 ምላሽ ለመስጠት: ለታሪኩ Telegram Reply ይጠቀሙ\n"
            "\u2014 ወደ ቻናሉ ለመለጠፍ: የሚታየውን 📢 ቁልፍ ይጫኑ"
        )
    else:
        await update.message.reply_text(
            "ይህ የኢትዮጲያ ኦርቶዶክስ ተዋሕዶ አማኞች የተለያዩ አስተማሪና ጣፋጭ ታሪኮች "
            "ወደ ሚተላለፉበት እና እንዲሁም ጥያቄዎቻችሁ ወደ ሚመለሱበት ገጽ በሰላም መጣችሁ ።"
        )


async def handle_owner_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner replies to a copied story -> deliver back to original sender."""
    replied = update.message.reply_to_message
    if replied is None:
        await update.message.reply_text(
            "ምላሽ ለመስጠት፣ ለዚያ ታሪክ Telegram ን 'Reply' ይጠቀሙ።"
        )
        return

    sender_chat_id, _ = db_lookup(replied.message_id)
    if sender_chat_id is None:
        await update.message.reply_text(
            "ይህ ታሪክ ከማን እንደመጣ ማግኘት አልተቻለም። (ምናልባት ጊዜው ያለፈ ወይም ቀደም ሲል ምላሽ ተሰጥቶታል።)"
        )
        return

    try:
        await context.bot.copy_message(
            chat_id=sender_chat_id,
            from_chat_id=update.effective_chat.id,
            message_id=update.message.message_id,
        )
        await update.message.reply_text("ምላሹ ተልኳል ✅")
    except Exception as e:
        logger.exception("Failed to deliver reply to sender")
        await update.message.reply_text(f"ምላሹን ማድረስ አልተቻለም: {e}")


async def handle_incoming_story(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Anyone (not the owner) sends a message -> copy it to the owner with action buttons."""
    sender_chat_id = update.effective_chat.id

    copied = await context.bot.copy_message(
        chat_id=OWNER_ID,
        from_chat_id=sender_chat_id,
        message_id=update.message.message_id,
    )
    # Store the message text (None for media) so we can combine with comment later
    message_text = update.message.text or None
    db_save(copied.message_id, sender_chat_id, message_text)

    # Send a control message with inline buttons to the owner
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 ወደ ቻናሉ ለጥፍ", callback_data=f"post:{copied.message_id}")],
    ])
    await context.bot.send_message(
        chat_id=OWNER_ID,
        text="📩 ታሪክ ደረሰ!\n"
             "— ምላሽ ለመስጠት: ለታሪኩ Telegram Reply ይጠቀሙ\n"
             "— ወደ ቻናሉ ለመለጠፍ: ከታች የሚታየውን ቁልፍ ይጫኑ",
        reply_markup=keyboard,
    )

    await update.message.reply_text("አስተያየቱ ተልኳል። እናመሰግናለን ✅")


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline button presses from owner."""
    query = update.callback_query
    await query.answer()

    if query.data.startswith("post:"):
        # Guard: warn owner if another post is already waiting for a comment
        if "pending_post_msg_id" in context.user_data:
            await query.message.reply_text(
                "⚠️ ቀድም የታሪክ አስተያየት ወለ ነው።\n"
                "መጠቀም አስተያየት ይፃፉ፣ ወይም ለመሰረዝ /cancel ይፃፉ።"
            )
            return
        owner_msg_id = int(query.data.split(":")[1])
        context.user_data["pending_post_msg_id"] = owner_msg_id
        await query.message.reply_text(
            "✏️ አስተያየትዎን ይፃፉ — ከዚያ ወደ ቻናሉ ይለጠፋል።"
        )


async def cancel_pending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner cancels a pending channel post."""
    if update.effective_user.id != OWNER_ID:
        return
    if context.user_data.pop("pending_post_msg_id", None) is not None:
        await update.message.reply_text("✅ ተሰር዇ል።")
    else:
        await update.message.reply_text("ምንም የለለበት ስራዝ የለም።")


async def route_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user is None or update.message is None:
        return

    if update.effective_user.id == OWNER_ID:

        # Post original story flow: owner typed their comment
        if "pending_post_msg_id" in context.user_data:
            pending = context.user_data.pop("pending_post_msg_id")
            comment = update.message.text or update.message.caption or ""
            _, story_text = db_lookup(pending)
            try:
                if story_text:
                    # Text story: merge into one message
                    await context.bot.send_message(
                        chat_id=CHANNEL_ID,
                        text=f"{story_text}\n\n{comment}",
                    )
                else:
                    # Media story: attach comment as caption
                    await context.bot.copy_message(
                        chat_id=CHANNEL_ID,
                        from_chat_id=OWNER_ID,
                        message_id=pending,
                        caption=comment,
                    )
                await update.message.reply_text("ወደ ቻናሉ ተለጥፏል ✅")
            except Exception as e:
                logger.exception("Failed to post to channel")
                await update.message.reply_text(f"ወደ ቻናሉ መለጠፍ አልተቻለም: {e}")

        else:
            await handle_owner_reply(update, context)
    else:
        await handle_incoming_story(update, context)


def main():
    db_init()
    app: Application = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cancel", cancel_pending))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, route_message))

    logger.info("Bot starting (polling)...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    try:
        asyncio.get_event_loop().run_until_complete(asyncio.sleep(0))
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())
    main()

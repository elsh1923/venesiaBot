import os
import json
import asyncio
import logging
import traceback
from flask import Flask, request, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
import redis

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Environment Variables ---
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))
CHANNEL_ID = os.environ.get("CHANNEL_ID", "@Veni212121")
KV_URL = os.environ.get("KV_URL", os.environ.get("REDIS_URL", ""))

# --- Redis Database Connection ---
try:
    if KV_URL:
        r = redis.Redis.from_url(KV_URL, decode_responses=True)
    else:
        r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
    logger.info("Redis connection configured.")
except Exception as e:
    logger.error(f"Redis connection failed: {e}")
    r = None

# --- Database Helpers ---
def db_save(owner_message_id: int, sender_chat_id: int, message_text: str = None):
    data = {"chat_id": sender_chat_id, "text": message_text}
    r.set(f"mapping:{owner_message_id}", json.dumps(data))

def db_lookup(owner_message_id: int):
    val = r.get(f"mapping:{owner_message_id}")
    if val:
        data = json.loads(val)
        return data.get("chat_id"), data.get("text")
    return None, None

def set_pending_post(owner_message_id: int):
    r.set("pending_post", str(owner_message_id))

def get_pending_post():
    val = r.get("pending_post")
    return int(val) if val else None

def clear_pending_post():
    r.delete("pending_post")

def get_alias(sender_chat_id: int) -> str:
    """Get or create a persistent anonymous alias like Person A, Person B, etc."""
    alias = r.get(f"alias:{sender_chat_id}")
    if alias:
        return alias
    # Increment counter and assign next letter
    count = r.incr("alias_counter")
    # Convert number to letter(s): 1=A, 2=B, ... 26=Z, 27=AA, 28=AB, ...
    letters = ""
    n = count
    while n > 0:
        n -= 1
        letters = chr(65 + (n % 26)) + letters
        n //= 26
    alias = f"Person {letters}"
    r.set(f"alias:{sender_chat_id}", alias)
    return alias


# --- Bot Handlers ---
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
            "እንኳን በሰላም መጡ! 🕊️✨\n\n"
            "ይህ የኢትዮጲያ ኦርቶዶክስ ተዋሕዶ አማኞች የተለያዩ አስተማሪና ጣፋጭ ታሪኮች "
            "የሚተላለፉበት እና ጥያቄዎች የሚመለሱበት ገጽ ነው።\n\n"
            "🔒 ማንነትዎ ሙሉ በሙሉ የተጠበቀ (ምስጢራዊ) ነው::\n\n"
            "✍️ ታሪክዎን፣ ጥያቄዎን ወይም አስተያየትዎን አሁኑኑ ይፃፉልን!"
        )


async def handle_owner_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    sender_chat_id = update.effective_chat.id
    alias = get_alias(sender_chat_id)
    logger.info(f"Incoming story from {alias}, forwarding to OWNER_ID={OWNER_ID}")

    message_text = update.message.text or None
    original_caption = update.message.caption or ""

    if message_text:
        # Text message: send as a new message with the alias tag embedded
        tagged_text = f"👤 {alias}\n\n{message_text}"
        sent = await context.bot.send_message(
            chat_id=OWNER_ID,
            text=tagged_text,
        )
        db_save(sent.message_id, sender_chat_id, message_text)
    else:
        # Media message (photo, video, etc.): copy with alias in the caption
        tagged_caption = f"👤 {alias}\n\n{original_caption}".strip()
        copied = await context.bot.copy_message(
            chat_id=OWNER_ID,
            from_chat_id=sender_chat_id,
            message_id=update.message.message_id,
            caption=tagged_caption,
        )
        db_save(copied.message_id, sender_chat_id, None)

    # Send control buttons
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 ወደ ቻናሉ ለጥፍ", callback_data=f"post:{sent.message_id if message_text else copied.message_id}")],
    ])
    await context.bot.send_message(
        chat_id=OWNER_ID,
        text="Reply ለምላሽ | 📢 ወደ ቻናሉ ለመለጠፍ",
        reply_markup=keyboard,
    )
    await update.message.reply_text("አስተያየቱ ተልኳል። እናመሰግናለን ✅")


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data.startswith("post:"):
        if get_pending_post() is not None:
            await query.message.reply_text(
                "⚠️ ቀድም የታሪክ አስተያየት ወለ ነው።\n"
                "መጠቀም አስተያየት ይፃፉ፣ ወይም ለመሰረዝ /cancel ይፃፉ።"
            )
            return
        owner_msg_id = int(query.data.split(":")[1])
        set_pending_post(owner_msg_id)
        await query.message.reply_text(
            "✏️ አስተያየትዎን ይፃፉ — ከዚያ ወደ ቻናሉ ይለጠፋል።"
        )


async def cancel_pending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    if get_pending_post() is not None:
        clear_pending_post()
        await update.message.reply_text("✅ ተሰር዇ል።")
    else:
        await update.message.reply_text("ምንም የለለበት ስራዝ የለም።")


async def route_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user is None or update.message is None:
        return

    if update.effective_user.id == OWNER_ID:
        pending = get_pending_post()
        if pending is not None:
            answer = update.message.text or update.message.caption or ""
            _, story_text = db_lookup(pending)
            try:
                if story_text:
                    # Text question: combine question + answer into one message
                    combined = (
                        f"❓ ጥያቄ:\n{story_text}\n\n"
                        f"✅ መልስ:\n{answer}"
                    )
                    await context.bot.send_message(
                        chat_id=CHANNEL_ID,
                        text=combined,
                    )
                else:
                    # Media question: copy media with answer as caption
                    caption = f"✅ መልስ:\n{answer}"
                    await context.bot.copy_message(
                        chat_id=CHANNEL_ID,
                        from_chat_id=OWNER_ID,
                        message_id=pending,
                        caption=caption,
                    )
                await update.message.reply_text("ወደ ቻናሉ ተለጥፏል ✅")
                clear_pending_post()
            except Exception as e:
                logger.exception("Failed to post to channel")
                await update.message.reply_text(f"ወደ ቻናሉ መለጠፍ አልተቻለም: {e}")
        else:
            await handle_owner_reply(update, context)
    else:
        await handle_incoming_story(update, context)


# --- Setup PTB Application ---
ptb_app = ApplicationBuilder().token(BOT_TOKEN).updater(None).build()
ptb_app.add_handler(CommandHandler("start", start))
ptb_app.add_handler(CommandHandler("cancel", cancel_pending))
ptb_app.add_handler(CallbackQueryHandler(button_callback))
ptb_app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, route_message))

_initialized = False
_loop = asyncio.new_event_loop()
asyncio.set_event_loop(_loop)

async def process_update(update_json):
    global _initialized
    if not _initialized:
        await ptb_app.initialize()
        _initialized = True
    update = Update.de_json(update_json, ptb_app.bot)
    await ptb_app.process_update(update)

WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")

@app.route("/", methods=["GET"])
def index():
    return "Bot is running.", 200

@app.route("/api/webhook", methods=["POST"])
def webhook():
    # Optional webhook secret verification
    if WEBHOOK_SECRET:
        secret_header = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
        if secret_header != WEBHOOK_SECRET:
            return jsonify({"error": "Unauthorized"}), 403

    try:
        data = request.get_json()
        if data is None:
            return jsonify({"error": "Invalid JSON"}), 400

        _loop.run_until_complete(process_update(data))

        return "OK", 200
    except Exception as e:
        logger.exception("Error processing update")
        return jsonify({"error": "Internal server error"}), 500

if __name__ == "__main__":
    app.run(debug=True, port=8000)

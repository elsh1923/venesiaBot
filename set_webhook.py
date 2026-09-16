import os
import sys
import asyncio
from telegram.ext import ApplicationBuilder

async def set_webhook():
    token = os.environ.get("BOT_TOKEN")
    if not token:
        print("Please set the BOT_TOKEN environment variable.")
        sys.exit(1)
        
    if len(sys.argv) < 2:
        print("Usage: python set_webhook.py <YOUR_VERCEL_URL>")
        print("Example: python set_webhook.py https://my-bot-project.vercel.app")
        sys.exit(1)

    url = sys.argv[1].rstrip("/")
    webhook_url = f"{url}/api/webhook"
    
    app = ApplicationBuilder().token(token).build()
    await app.bot.set_webhook(url=webhook_url)
    
    print(f"Webhook successfully set to {webhook_url}")

if __name__ == "__main__":
    asyncio.run(set_webhook())

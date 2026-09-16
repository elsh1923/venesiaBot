"""
Simple script to set the Telegram webhook.
Uses only the built-in urllib module — no external dependencies needed.

Usage:
    python set_webhook.py <VERCEL_URL>

Example:
    python set_webhook.py https://venesia-bot.vercel.app
"""
import os
import sys
import json
import urllib.request

def set_webhook():
    token = os.environ.get("BOT_TOKEN")
    if not token:
        print("ERROR: Please set the BOT_TOKEN environment variable.")
        sys.exit(1)

    if len(sys.argv) < 2:
        print("Usage: python set_webhook.py <YOUR_VERCEL_URL>")
        print("Example: python set_webhook.py https://my-bot-project.vercel.app")
        sys.exit(1)

    url = sys.argv[1].rstrip("/")
    webhook_url = f"{url}/api/webhook"

    api_url = f"https://api.telegram.org/bot{token}/setWebhook?url={webhook_url}"

    with urllib.request.urlopen(api_url) as response:
        result = json.loads(response.read().decode())

    if result.get("ok"):
        print(f"SUCCESS: Webhook set to: {webhook_url}")
    else:
        print(f"FAILED: {result.get('description', 'Unknown error')}")
        sys.exit(1)

if __name__ == "__main__":
    set_webhook()

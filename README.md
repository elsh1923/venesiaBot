# Anonymous Story Bot — Setup & Deployment Guide

This bot lets people send a story to your Telegram bot, which forwards it to
you with **no name, username, or account info attached**. You can reply
(using Telegram's native "Reply" feature) and your response goes back to
the original sender — still anonymously, without exposing your personal
account.

---

## 1. Create the bot on Telegram

1. Open a chat with **@BotFather** on Telegram.
2. Send `/newbot`, follow the prompts, choose a name and a username
   (must end in `bot`, e.g. `MyStoryHelperBot`).
3. BotFather gives you a **token** like `123456789:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`.
   Save it — this is `BOT_TOKEN`.

## 2. Get your own numeric Telegram ID

1. Open a chat with **@userinfobot**.
2. Send any message — it replies with your numeric ID.
3. Save it — this is `OWNER_ID`.

---

## 3. Get a free, always-on server (Oracle Cloud "Always Free")

This is a real free-forever VPS (not a trial), with no sleep/spin-down —
important since stories can arrive at any time.

1. Go to https://www.oracle.com/cloud/free/ and sign up (requires a card
   for identity verification only — the Always Free tier is not billed).
2. Create a Compute Instance:
   - Shape: **VM.Standard.E2.1.Micro** (Always Free eligible)
   - Image: **Ubuntu** (latest LTS)
   - Keep the default networking; make sure a public IP is assigned.
3. Download the SSH key Oracle gives you during setup — you'll need it to
   connect.
4. Connect to the server:
   ```
   ssh -i your-key.pem ubuntu@<your-server-ip>
   ```

## 4. Install and run the bot

On the server:

```bash
sudo apt update && sudo apt install -y python3-venv python3-pip
mkdir ~/anon_story_bot && cd ~/anon_story_bot
# upload bot.py and requirements.txt here (see "uploading files" below)

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file with your credentials:

```bash
cat > .env << 'EOF'
BOT_TOKEN=your_token_here
OWNER_ID=your_numeric_id_here
EOF
```

Test it manually first:

```bash
export $(cat .env | xargs)
python3 bot.py
```

Send `/start` to your bot from your phone — it should reply immediately.
If it works, stop it with `Ctrl+C`.

## 5. Keep it running 24/7 (auto-restart, survives reboots)

Use the included `anon-story-bot.service` file so the bot restarts
automatically if it crashes or the server reboots:

```bash
sudo cp anon-story-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable anon-story-bot
sudo systemctl start anon-story-bot
```

Check it's alive:

```bash
sudo systemctl status anon-story-bot
```

View logs any time:

```bash
journalctl -u anon-story-bot -f
```

---

## Uploading files to the server

From your own computer (not the server):

```bash
scp -i your-key.pem bot.py requirements.txt anon-story-bot.service ubuntu@<your-server-ip>:~/anon_story_bot/
```

---

## How anonymity is enforced

- Messages are copied (not forwarded) to you, so Telegram's
  "Forwarded from ..." tag never appears.
- The only thing linking a story to its sender is a private local
  database on your own server — nobody outside has access to it.
- Replying uses the same copy method, so senders never see your
  personal account either.

## Notes

- The bot uses long-polling, so it needs to be *running continuously* —
  that's exactly why we're using a real always-on VPS instead of a
  free tier that sleeps.
- If your channel grows a lot, this same tiny server will comfortably
  handle it — Telegram message volume for a feedback bot is very light
  on resources.

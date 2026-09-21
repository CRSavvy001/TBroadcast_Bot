 # Telegram Broadcast Bot

Forwards a chosen message to a list of registered groups on a repeating
interval, until you send `/stopbroadcast`.

## Important: Telegram's rules on this

Sending identical messages to many groups on a tight loop is exactly the
pattern Telegram's anti-spam systems watch for. To reduce the risk of your
bot getting rate-limited or banned:

- The bot enforces a **minimum 2-second interval** between broadcast ticks,
  even if you ask for less.
- Keep your group list reasonable — the more groups, the more requests per
  tick, and the more likely you'll hit `429 Too Many Requests`.
- Consider whether the groups' members actually want repeated messages;
  admins can and do remove/report bots that spam.

## 1. Create the bot with @BotFather

1. In Telegram, message **@BotFather** → `/newbot` → follow the prompts.
2. Copy the **bot token** it gives you (looks like `123456:ABC-DEF...`).

## 2. Get your numeric Telegram user ID

Message **@userinfobot** (or **@getidsbot**) on Telegram — it will reply
with your numeric ID. This is your `ADMIN_USER_ID`, so only you can control
the bot.

## 3. Upload this code to GitHub from your phone

**Easiest way — GitHub mobile app:**
1. Install the **GitHub** app, sign in.
2. Tap **+** → **New repository** → name it (e.g. `telegram-broadcast-bot`)
   → Create.
3. Open the repo → tap **+** / the "Add file" option → **Create new file**.
4. Create each file below with the exact name, paste its contents, and
   commit: `bot.py`, `requirements.txt`, `Procfile`, `.gitignore`,
   `README.md`.

**Alternative — mobile browser:**
1. Go to github.com, log in, create a new repository.
2. Use **Add file → Upload files**, and upload each file from wherever
   you saved them on your phone (e.g. from a Files/Downloads app after I
   send them to you here).

Either way, you should end up with a repo containing `bot.py`,
`requirements.txt`, `Procfile`, and `.gitignore` at the top level.

## 4. Deploy on Railway

1. Go to railway.com (works fine on mobile browser) and log in.
2. **New Project → Deploy from GitHub repo** → pick your
   `telegram-broadcast-bot` repo → authorize Railway to access it if asked.
3. Once the project is created, open it → **Variables** tab → add:
   - `BOT_TOKEN` = the token from @BotFather
   - `ADMIN_USER_ID` = your numeric ID from step 2
4. Railway will detect the `Procfile` and run `python bot.py` as a worker.
   If it instead tries to run it as a web service, go to **Settings →
   Deploy** and make sure the start command is `python bot.py`.
5. Wait for the deploy to finish — check the **Deployments → Logs** tab for
   `Bot starting...` to confirm it's running.

## 5. Using the bot

1. Add your bot to each Telegram group, and give it permission to send
   messages (Telegram usually does this by default when you add a bot).
2. Inside each group, send `/addgroup` — the bot registers that group's
   chat ID in `groups.json`.
3. In a **private chat** with the bot, send the message you want
   broadcast.
4. **Reply** to that message with `/broadcast <seconds>` — e.g.
   `/broadcast 2` to repeat it every 2 seconds (minimum enforced: 2).
5. Send `/stopbroadcast` any time to stop the loop.
6. `/listgroups` shows registered groups; `/removegroup` unregisters the
   group you run it in.

## Notes on persistence

`groups.json` is stored on Railway's local disk. It survives restarts but
can be wiped on a fresh redeploy in some configurations. If you want
guaranteed persistence, add a Railway **Volume** mounted at the project
directory, or switch storage to a small database — ask me if you'd like
that upgrade.

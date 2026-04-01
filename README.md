# Alpine CC ForeTees WhatsApp Bot

Text a WhatsApp number to check and book tee times, tennis courts, and dining
reservations at Alpine Country Club powered by your ForeTees account.

---

## How it works

```
You text: "tee times Saturday morning"
   Bot logs into ForeTees as you
   Bot replies: "1. 8:30 AM  2. 8:40 AM  3. 9:00 AM ..."
   You text: "3"
   Bot books 9:00 AM and confirms
```

---

## One-time setup (takes ~20 minutes)

### Step 1 - Twilio WhatsApp Sandbox (free)

1. Go to [twilio.com](https://twilio.com) and create a free account.
2. In the Twilio Console, go to **Messaging > Try it out > Send a WhatsApp message**.
3. Note the sandbox number and the join word (e.g. `join bright-tiger`).
4. From your iPhone WhatsApp, send that join word to the Twilio sandbox number.
5. From the Console, note your **Account SID** and **Auth Token** (on the home page).

### Step 2 - Deploy to Railway (free)

1. Go to [railway.app](https://railway.app) and sign in with GitHub.
2. Click **New Project > Deploy from GitHub repo** and connect this repo.
3. In Railway project settings, add these **environment variables**:

| Variable | Value |
|---|---|
| `FORETEES_USERNAME` | `1386` |
| `FORETEES_PASSWORD` | Your ForeTees password |
| `OWNER_PHONE` | Your number e.g. `12015559876` |
| `TWILIO_ACCOUNT_SID` | From Twilio Console |
| `TWILIO_AUTH_TOKEN` | From Twilio Console |

4. Deploy. Railway gives you a public URL like `https://alpine-bot-production.up.railway.app`.

### Step 3 - Connect Twilio to your server

1. Twilio Console > **Messaging > Try it out > WhatsApp Sandbox**.
2. In **"When a message comes in"**, paste your Railway URL + `/whatsapp`:
   `https://alpine-bot-production.up.railway.app/whatsapp`
3. Set method to **HTTP POST**. Save.

**That's it.** Text your Twilio sandbox number from WhatsApp and the bot responds.

---

## Usage examples

| You text | Bot does |
|---|---|
| `tee times this Saturday` | Lists available Saturday tee times |
| `golf Sunday morning` | Lists Sunday AM tee times |
| `3` or `9:30` | Books that slot from the last list |
| `tennis courts Friday` | Lists Friday court availability |
| `dining Saturday night for 2` | Shows Saturday dining slots for 2 |
| `cancel` | Clears current booking flow |
| `help` | Shows usage guide |

---

## Troubleshooting

**Bot doesn't respond**: Check your phone is joined to the Twilio sandbox. Check Railway logs.

**"No available tee times"**: ForeTees only shows times 7 days in advance; new slots open at 7:00 AM.

**Session expired**: Delete `session.json` and the bot will log in fresh on the next message.

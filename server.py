"""
server.py — FastAPI webhook that receives WhatsApp messages via Twilio
and replies using the ForeTees bot.

Run locally:  uvicorn server:app --host 0.0.0.0 --port 8000
"""
import os
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Form
from fastapi.responses import PlainTextResponse
from twilio.twiml.messaging_response import MessagingResponse

import config
from foretees import ForeTees
from bot import handle_message

# ── Global ForeTees instance (shared across requests) ───────────────────────────
_ft: ForeTees = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start and stop the Playwright browser with the app."""
    global _ft
    _ft = ForeTees(config.FORETEES_USERNAME, config.FORETEES_PASSWORD)
    # Start browser in background so server can respond to healthchecks immediately
    asyncio.create_task(_ft.start())
    print("🚀 ForeTees browser starting in background...")
    yield
    await _ft.stop()
    print("🛑 ForeTees browser stopped.")


app = FastAPI(lifespan=lifespan)


# ── Health check ────────────────────────────────────────────────────────────
@app.get("/")
async def health():
    return {"status": "ok", "bot": "Alpine CC ForeTees Bot"}


# ── WhatsApp webhook ──────────────────────────────────────────────────────
@app.post("/whatsapp")
async def whatsapp_webhook(
    request: Request,
    From: str = Form(...),
    Body: str = Form(...),
):
    """
    Twilio sends POST requests here when you receive a WhatsApp message.
    From: the user's WhatsApp number (e.g. "whatsapp:+12015551234")
    Body: the message text
    """
    phone = From.replace("whatsapp:", "").strip()
    text  = Body.strip()

    print(f"[{phone}] → {text!r}")

    # Only respond to messages from the configured owner number
    if config.OWNER_PHONE and phone != config.OWNER_PHONE:
        print(f"  ⛔ Unknown sender, ignoring.")
        return PlainTextResponse("", status_code=200)

    try:
        reply = await handle_message(phone, text, _ft)
    except Exception as exc:
        print(f"  ❌ Error: {exc}")
        reply = "⚠️ Something went wrong. Please try again in a moment."

    print(f"[{phone}] ← {reply!r}")

    # Return TwiML response
    twiml = MessagingResponse()
    twiml.message(reply)
    return PlainTextResponse(str(twiml), media_type="application/xml")

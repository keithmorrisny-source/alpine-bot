"""
config.py — Edit these values before deploying.
For other members, just copy this whole folder and update this file.
"""
import os

# ── ForeTees credentials ────────────────────────────────────────────────
FORETEES_USERNAME = os.getenv("FORETEES_USERNAME", "1386")
FORETEES_PASSWORD = os.getenv("FORETEES_PASSWORD", "Morris11")

# ── Your WhatsApp number (digits only, with country code, no +) ───────────────────
# The bot will ONLY respond to messages from this number.
# Example: "12015559876"  (US number, no + or spaces)
OWNER_PHONE = os.getenv("OWNER_PHONE", "")   # ← fill this in!

# ── Twilio credentials ────────────────────────────────────────────────
# Get these from https://console.twilio.com after setting up the WhatsApp Sandbox
TWILIO_ACCOUNT_SID  = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN   = os.getenv("TWILIO_AUTH_TOKEN", "")

# The Twilio WhatsApp Sandbox number (leave as-is for sandbox)
# For a dedicated number later, change to your purchased Twilio number.
TWILIO_WHATSAPP_FROM = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")

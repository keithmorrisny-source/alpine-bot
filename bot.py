"""
bot.py — Conversation logic for the Alpine CC ForeTees WhatsApp bot.

Handles:
  • Intent detection from natural language messages
  • Multi-turn conversation state (per user phone number)
  • Response formatting
"""
import re
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import dateparser

# ── Conversation state ──────────────────────────────────────────────────────────────────
# Keyed by user phone number; lives in memory (fine for single-user personal bot)
_sessions: Dict[str, Dict[str, Any]] = {}

IDLE       = "idle"
SHOW_GOLF  = "show_golf"
SHOW_TENNIS = "show_tennis"
SHOW_DINING = "show_dining"
CONFIRM    = "confirm"

HELP_TEXT = (
    "*Alpine CC Booking Bot* 🏌️🎾🍴\n\n"
    "Just text me naturally:\n"
    "• _tee times Saturday_ → show available golf slots\n"
    "• _tennis courts Friday morning_ → show open courts\n"
    "• _dining Saturday night_ → show dining slots\n"
    "• _book 9:30_ or just _1_ → book from the last list\n"
    "• _cancel_ → start over\n"
    "• _help_ → show this message\n\n"
    "Tee times open 7 days in advance at 7:00 AM."
)


# ── Intent detection ──────────────────────────────────────────────────────────────────

def _detect_intent(msg: str) -> Dict[str, Any]:
    """
    Parse a free-text message and return an intent dict.
    Returns: {type, date_str, time_pref, selection, duration, party_size}
    """
    msg_lower = msg.lower().strip()
    result: Dict[str, Any] = {
        "type": None,          # "golf" | "tennis" | "dining" | "book" | "cancel" | "help"
        "date_str": None,      # MM/DD/YYYY
        "time_pref": None,     # "morning" | "afternoon" | "evening" | None
        "selection": None,     # int index or time string when user picks a slot
        "duration_min": 60,    # for tennis
        "party_size": 2,       # for dining
    }

    # ── Cancel / Help ────────────────────────────────────────────────────────────────────────
    if re.search(r"\bcancel\b|\breset\b|\bstart over\b|\bnever mind\b", msg_lower):
        result["type"] = "cancel"
        return result
    if re.search(r"\bhelp\b|\binfo\b|\bhow\b", msg_lower):
        result["type"] = "help"
        return result

    # ── Activity type ────────────────────────────────────────────────────────────────────────
    if re.search(r"\bgolf\b|\btee\s*time\b|\btee\s*times\b|\btee\b", msg_lower):
        result["type"] = "golf"
    elif re.search(r"\btennis\b|\bcourt\b|\bcourts\b", msg_lower):
        result["type"] = "tennis"
    elif re.search(r"\bdining\b|\bdinner\b|\blunch\b|\breservation\b|\brestaurant\b|\bbar\b", msg_lower):
        result["type"] = "dining"

    # ── Slot selection (user picking from a list) ──────────────────────────────────────────────
    # "1", "2", "3" ... or "book 9:30 AM", "9:30", "the 10am one"
    sel_match = re.match(r"^(\d+)$", msg.strip())
    time_match = re.search(r"\b(\d{1,2}:\d{2}\s*(?:am|pm)?)\b", msg_lower)
    if sel_match:
        result["type"] = result["type"] or "book"
        result["selection"] = int(sel_match.group(1))
    elif time_match:
        result["type"] = result["type"] or "book"
        result["selection"] = time_match.group(1).upper().strip()

    # ── Time-of-day preference ───────────────────────────────────────────────────────────────
    if re.search(r"\bmorning\b|\bam\b|early", msg_lower):
        result["time_pref"] = "morning"
    elif re.search(r"\bafternoon\b|\blunch\b|\bnoon\b", msg_lower):
        result["time_pref"] = "afternoon"
    elif re.search(r"\bevening\b|\bnight\b|\bdinner\b|\bpm\b", msg_lower):
        result["time_pref"] = "evening"

    # ── Duration (tennis) ────────────────────────────────────────────────────────────────────────
    dur_match = re.search(r"\b(30|60|90)\s*min", msg_lower)
    if dur_match:
        result["duration_min"] = int(dur_match.group(1))

    # ── Party size (dining) ──────────────────────────────────────────────────────────────────
    party_match = re.search(
        r"\b(?:for\s+(\d+)|(\d+)\s+(?:people|persons?|guests?|of us|pax)|party\s+of\s+(\d+)|table\s+for\s+(\d+))\b",
        msg_lower
    )
    if party_match:
        val = next(g for g in party_match.groups() if g is not None)
        result["party_size"] = int(val)

    # ── Date parsing ────────────────────────────────────────────────────────────────────────
    # dateparser handles: "Saturday", "next Friday", "tomorrow", "April 10", etc.
    parsed_dt = dateparser.parse(
        msg,
        settings={
            "PREFER_DATES_FROM": "future",
            "RETURN_AS_TIMEZONE_AWARE": False,
            "PREFER_DAY_OF_MONTH": "first",
        },
    )
    if parsed_dt:
        today = datetime.now().date()
        if parsed_dt.date() >= today:
            result["date_str"] = parsed_dt.strftime("%m/%d/%Y")

    return result


# ── Time filtering ────────────────────────────────────────────────────────────────────────

def _filter_by_time_pref(
    slots: List[Dict[str, Any]], pref: Optional[str]
) -> List[Dict[str, Any]]:
    """Filter slot list by morning / afternoon / evening preference."""
    if not pref or not slots:
        return slots

    def hour_of(slot):
        t = slot.get("time", "")
        m = re.search(r"(\d+):", t)
        h = int(m.group(1)) if m else 12
        if "PM" in t.upper() and h != 12:
            h += 12
        if "AM" in t.upper() and h == 12:
            h = 0
        return h

    if pref == "morning":
        return [s for s in slots if hour_of(s) < 12]
    if pref == "afternoon":
        return [s for s in slots if 12 <= hour_of(s) < 17]
    if pref == "evening":
        return [s for s in slots if hour_of(s) >= 17]
    return slots


# ── Response formatters ───────────────────────────────────────────────────────────────────────

def _fmt_tee_times(slots: List[Dict[str, Any]], date_str: str) -> str:
    if not slots:
        return f"😕 No available tee times on {date_str}. Try a different date."
    lines = [f"⛳ *Available tee times — {date_str}*\n"]
    for i, s in enumerate(slots, 1):
        spots = f"({s['open_spots']} open)" if s.get("open_spots", 4) < 4 else ""
        lines.append(f"{i}. {s['time']} {spots}".strip())
    lines.append("\nReply with a number or time to book (e.g. _3_ or _9:30_).")
    return "\n".join(lines)


def _fmt_tennis(slots: List[Dict[str, Any]], date_str: str) -> str:
    if not slots:
        return f"😕 No available tennis courts on {date_str}. Try a different date."
    lines = [f"🎾 *Available tennis slots — {date_str}*\n"]
    for i, s in enumerate(slots, 1):
        lines.append(f"{i}. {s['time']} — {s['court']}")
    lines.append("\nReply with a number or time (e.g. _2_ or _9:00 AM_).\nDefault duration: 60 min. Add _30 min_ or _90 min_ to change.")
    return "\n".join(lines)


def _fmt_dining(slots: List[Dict[str, Any]], date_str: str) -> str:
    if not slots:
        return f"😕 No dining slots available on {date_str}. Try a different date."
    lines = [f"🍴 *Available dining times — {date_str}*\n"]
    for i, s in enumerate(slots, 1):
        lines.append(f"{i}. {s['time']} — {s['location']}")
    lines.append("\nReply with a number or time (e.g. _1_ or _7:00 PM_).\nAdd party size like _for 3_ if needed.")
    return "\n".join(lines)


# ── Main conversation handler ─────────────────────────────────────────────────────────────────

async def handle_message(
    phone: str,
    text: str,
    foretees,           # ForeTees instance
) -> str:
    """
    Process an incoming WhatsApp message and return the reply string.
    foretees: an active ForeTees() context-managed instance.
    """
    session = _sessions.get(phone, {"step": IDLE, "slots": [], "type": None, "date_str": None})

    msg = text.strip()
    intent = _detect_intent(msg)

    # ── Always honour cancel / help regardless of state ──────────────────────────────────────
    if intent["type"] == "cancel":
        _sessions.pop(phone, None)
        return "👍 Cancelled. What would you like to book? (tee times, tennis, dining)"

    if intent["type"] == "help":
        return HELP_TEXT

    # ── In the middle of a booking flow: user is selecting a slot ──────────────────────
    if session["step"] in (SHOW_GOLF, SHOW_TENNIS, SHOW_DINING) and (
        intent["selection"] is not None or intent["type"] == "book"
    ):
        slots = session.get("slots", [])
        booking_type = session.get("type")
        date_str = session.get("date_str")
        sel = intent["selection"]
        duration_min = intent.get("duration_min", 60)
        party_size = intent.get("party_size", 2)

        chosen = None
        if isinstance(sel, int) and 1 <= sel <= len(slots):
            chosen = slots[sel - 1]
        elif isinstance(sel, str):
            sel_norm = sel.upper().replace(".", "").strip()
            for s in slots:
                if sel_norm in s["time"].upper():
                    chosen = s
                    break

        if not chosen:
            return (
                f"⚠️ I didn't catch that. Reply with a number (1–{len(slots)}) "
                f"or a time like _9:30 AM_."
            )

        _sessions.pop(phone, None)

        if booking_type == "golf":
            result = await foretees.book_tee_time(date_str, chosen["time"])
        elif booking_type == "tennis":
            result = await foretees.book_tennis_court(
                date_str, chosen["time"], duration_min=duration_min
            )
        elif booking_type == "dining":
            result = await foretees.book_dining(
                date_str, chosen["time"], party_size=party_size,
                location=chosen.get("location", "")
            )
        else:
            return "⚠️ Something went wrong. Please start over."

        return result["message"]

    # ── New query: look up available slots ─────────────────────────────────────────────────────────
    booking_type = intent["type"]
    date_str = intent["date_str"]

    if booking_type not in ("golf", "tennis", "dining"):
        return (
            "🤔 I didn't quite get that.\n\n"
            + HELP_TEXT
        )

    if not date_str:
        type_word = {"golf": "golf", "tennis": "tennis", "dining": "dining"}[booking_type]
        return f"What date would you like to check {type_word} for? (e.g. _this Saturday_ or _April 12_)"

    if booking_type == "golf":
        raw_slots = await foretees.get_tee_times(date_str)
        slots = _filter_by_time_pref(raw_slots, intent["time_pref"])
        reply = _fmt_tee_times(slots, date_str)
        next_step = SHOW_GOLF
    elif booking_type == "tennis":
        raw_slots = await foretees.get_tennis_courts(date_str)
        slots = _filter_by_time_pref(raw_slots, intent["time_pref"])
        reply = _fmt_tennis(slots, date_str)
        next_step = SHOW_TENNIS
    else:
        raw_slots = await foretees.get_dining_slots(date_str)
        slots = _filter_by_time_pref(raw_slots, intent["time_pref"])
        reply = _fmt_dining(slots, date_str)
        next_step = SHOW_DINING

    if slots:
        _sessions[phone] = {
            "step": next_step,
            "type": booking_type,
            "date_str": date_str,
            "slots": slots,
        }
    else:
        _sessions.pop(phone, None)

    return reply

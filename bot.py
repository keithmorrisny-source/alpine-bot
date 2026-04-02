"""
bot.py - Conversation logic for the Alpine CC ForeTees WhatsApp bot.

Fixes:
  1. Use search_dates() to extract dates from full sentences.
  2. Save AWAITING_DATE state when asking for a date so follow-up replies work.
"""

import re
from datetime import datetime
from typing import Dict, Any, Optional, List

import dateparser
from dateparser.search import search_dates

# -- Conversation state -------------------------------------------------------
_sessions: Dict[str, Dict[str, Any]] = {}

IDLE          = "idle"
AWAITING_DATE = "awaiting_date"
SHOW_GOLF     = "show_golf"
SHOW_TENNIS   = "show_tennis"
SHOW_DINING   = "show_dining"

HELP_TEXT = (
    "*Alpine CC Booking Bot*\n\n"
    "Just text me naturally:\n"
    "- tee times Saturday -> show available golf slots\n"
    "- tennis courts Friday morning -> show open courts\n"
    "- dining Saturday night -> show dining slots\n"
    "- book 9:30 or just 1 -> book from the last list\n"
    "- cancel -> start over\n"
    "- help -> show this message\n\n"
    "Tee times open 7 days in advance at 7:00 AM."
)


def _detect_intent(msg: str) -> Dict[str, Any]:
    msg_lower = msg.lower().strip()
    result: Dict[str, Any] = {
        "type": None,
        "date_str": None,
        "time_pref": None,
        "selection": None,
        "duration_min": 60,
        "party_size": 2,
    }

    if re.search(r"\bcancel\b|\breset\b|\bstart over\b|\bnever mind\b", msg_lower):
        result["type"] = "cancel"
        return result
    if re.search(r"\bhelp\b|\binfo\b|\bhow\b", msg_lower):
        result["type"] = "help"
        return result

    if re.search(r"\bgolf\b|\btee\s*time\b|\btee\s*times\b|\btee\b", msg_lower):
        result["type"] = "golf"
    elif re.search(r"\btennis\b|\bcourt\b|\bcourts\b", msg_lower):
        result["type"] = "tennis"
    elif re.search(r"\bdining\b|\bdinner\b|\blunch\b|\breservation\b|\brestaurant\b|\bbar\b", msg_lower):
        result["type"] = "dining"

    sel_match = re.match(r"^(\d+)$", msg.strip())
    time_match = re.search(r"\b(\d{1,2}:\d{2}\s*(?:am|pm)?)\b", msg_lower)
    if sel_match:
        result["type"] = result["type"] or "book"
        result["selection"] = int(sel_match.group(1))
    elif time_match:
        result["type"] = result["type"] or "book"
        result["selection"] = time_match.group(1).upper().strip()

    if re.search(r"\bmorning\b|\bam\b|early", msg_lower):
        result["time_pref"] = "morning"
    elif re.search(r"\bafternoon\b|\blunch\b|\bnoon\b", msg_lower):
        result["time_pref"] = "afternoon"
    elif re.search(r"\bevening\b|\bnight\b|\bdinner\b|\bpm\b", msg_lower):
        result["time_pref"] = "evening"

    dur_match = re.search(r"\b(30|60|90)\s*min", msg_lower)
    if dur_match:
        result["duration_min"] = int(dur_match.group(1))

    party_match = re.search(
        r"\b(?:for\s+(\d+)|(\d+)\s+(?:people|persons?|guests?|of us|pax)"
        r"|party\s+of\s+(\d+)|table\s+for\s+(\d+))\b",
        msg_lower,
    )
    if party_match:
        val = next(g for g in party_match.groups() if g is not None)
        result["party_size"] = int(val)

    today = datetime.now().date()
    date_found = False
    try:
        found = search_dates(
            msg,
            settings={
                "PREFER_DATES_FROM": "future",
                "RETURN_AS_TIMEZONE_AWARE": False,
                "PREFER_DAY_OF_MONTH": "first",
            },
        )
        if found:
            for _, dt in found:
                if dt.date() >= today:
                    result["date_str"] = dt.strftime("%m/%d/%Y")
                    date_found = True
                    break
    except Exception:
        pass

    if not date_found:
        parsed_dt = dateparser.parse(
            msg,
            settings={
                "PREFER_DATES_FROM": "future",
                "RETURN_AS_TIMEZONE_AWARE": False,
                "PREFER_DAY_OF_MONTH": "first",
            },
        )
        if parsed_dt and parsed_dt.date() >= today:
            result["date_str"] = parsed_dt.strftime("%m/%d/%Y")

    return result


def _filter_by_time_pref(
    slots: List[Dict[str, Any]], pref: Optional[str]
) -> List[Dict[str, Any]]:
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


def _fmt_tee_times(slots: List[Dict[str, Any]], date_str: str) -> str:
    if not slots:
        return f"No available tee times on {date_str}. Try a different date."
    lines = [f"Available tee times - {date_str}\n"]
    for i, s in enumerate(slots, 1):
        spots = f"({s['open_spots']} open)" if s.get("open_spots", 4) < 4 else ""
        lines.append(f"{i}. {s['time']} {spots}".strip())
    lines.append("\nReply with a number or time to book (e.g. 3 or 9:30).")
    return "\n".join(lines)


def _fmt_tennis(slots: List[Dict[str, Any]], date_str: str) -> str:
    if not slots:
        return f"No available tennis courts on {date_str}. Try a different date."
    lines = [f"Available tennis slots - {date_str}\n"]
    for i, s in enumerate(slots, 1):
        lines.append(f"{i}. {s['time']} - {s['court']}")
    lines.append("\nReply with a number or time. Default: 60 min.")
    return "\n".join(lines)


def _fmt_dining(slots: List[Dict[str, Any]], date_str: str) -> str:
    if not slots:
        return f"No dining slots available on {date_str}. Try a different date."
    lines = [f"Available dining times - {date_str}\n"]
    for i, s in enumerate(slots, 1):
        lines.append(f"{i}. {s['time']} - {s['location']}")
    lines.append("\nReply with a number or time. Add party size like: for 3")
    return "\n".join(lines)


async def _lookup_slots(booking_type, date_str, intent, foretees):
    if booking_type == "golf":
        raw = await foretees.get_tee_times(date_str)
        slots = _filter_by_time_pref(raw, intent.get("time_pref"))
        return slots, _fmt_tee_times(slots, date_str), SHOW_GOLF
    elif booking_type == "tennis":
        raw = await foretees.get_tennis_courts(date_str)
        slots = _filter_by_time_pref(raw, intent.get("time_pref"))
        return slots, _fmt_tennis(slots, date_str), SHOW_TENNIS
    else:
        raw = await foretees.get_dining_slots(date_str)
        slots = _filter_by_time_pref(raw, intent.get("time_pref"))
        return slots, _fmt_dining(slots, date_str), SHOW_DINING


async def handle_message(phone: str, text: str, foretees) -> str:
    session = _sessions.get(
        phone, {"step": IDLE, "slots": [], "type": None, "date_str": None}
    )
    msg = text.strip()
    intent = _detect_intent(msg)

    if intent["type"] == "cancel":
        _sessions.pop(phone, None)
        return "Cancelled. What would you like to book? (tee times, tennis, dining)"
    if intent["type"] == "help":
        return HELP_TEXT

    if session.get("step") == AWAITING_DATE:
        date_str = intent.get("date_str")
        if not date_str:
            return "I did not catch that date. Try again (e.g. April 3 or this Saturday)."
        booking_type = session["type"]
        saved_intent = {
            "time_pref": session.get("time_pref"),
            "duration_min": session.get("duration_min", 60),
            "party_size": session.get("party_size", 2),
        }
        slots, reply, next_step = await _lookup_slots(
            booking_type, date_str, saved_intent, foretees
        )
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
            return f"I did not catch that. Reply with a number (1-{len(slots)}) or a time like 9:30 AM."

        _sessions.pop(phone, None)
        if booking_type == "golf":
            result = await foretees.book_tee_time(date_str, chosen["time"])
        elif booking_type == "tennis":
            result = await foretees.book_tennis_court(
                date_str, chosen["time"], duration_min=duration_min
            )
        elif booking_type == "dining":
            result = await foretees.book_dining(
                date_str, chosen["time"],
                party_size=party_size,
                location=chosen.get("location", ""),
            )
        else:
            return "Something went wrong. Please start over."
        return result["message"]

    booking_type = intent["type"]
    date_str = intent["date_str"]

    if booking_type not in ("golf", "tennis", "dining"):
        return "I did not quite get that.\n\n" + HELP_TEXT

    if not date_str:
        type_word = {"golf": "golf", "tennis": "tennis", "dining": "dining"}[booking_type]
        _sessions[phone] = {
            "step": AWAITING_DATE,
            "type": booking_type,
            "time_pref": intent.get("time_pref"),
            "duration_min": intent.get("duration_min", 60),
            "party_size": intent.get("party_size", 2),
            "slots": [],
            "date_str": None,
        }
        return f"What date would you like to check {type_word} for? (e.g. this Saturday or April 12)"

    slots, reply, next_step = await _lookup_slots(booking_type, date_str, intent, foretees)
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

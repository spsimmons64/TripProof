"""When a record falls due again under a rule's recurrence - one answer for every screen that asks.

A number of days, or a number of calendar months. "Every twelve months" and "every six months" are
months: 365 days lands a day early across a leap year, and 183 days is not six months at all. A
month with no such day ends on its last day."""
from calendar import monthrange
from datetime import date, timedelta


def renewed(rule: dict, start: date) -> date | None:
    """The day a record dated `start` stops answering the rule, or None if it is asked once."""
    if rule.get("recurrence") == "days" and rule.get("recurrencedays"):
        return start + timedelta(days=int(rule["recurrencedays"]))
    if rule.get("recurrence") == "months" and rule.get("recurrencemonths"):
        n = start.month - 1 + int(rule["recurrencemonths"])
        year, month = start.year + n // 12, n % 12 + 1
        return date(year, month, min(start.day, monthrange(year, month)[1]))
    return None

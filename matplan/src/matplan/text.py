"""Gemensam svensk textformatering för CLI och export."""

from datetime import date

from .inkop import Kop

VECKODAGAR = ("mån", "tis", "ons", "tor", "fre", "lör", "sön")
MANADER = ("jan", "feb", "mar", "apr", "maj", "jun", "jul", "aug", "sep", "okt", "nov", "dec")


def datum(d: date) -> str:
    return f"{VECKODAGAR[d.weekday()]} {d.day} {MANADER[d.month - 1]}"


def forpackning(kop: Kop) -> str:
    if kop.antal is None:
        return "lösvikt"
    return f"{kop.antal} st"

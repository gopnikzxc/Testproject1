"""Erbjudanden: när är ett pris riktigt bra?

Ett pris räknas som rea när det ligger minst `grans` (t.ex. 25 %) under
medianen av produktens kr/kg under de senaste veckorna. Historiken räknas
med ett pris per dag (det senaste), så att flera hämtningar samma dag inte
väger tyngre. Med för lite historik avgör butikens egen erbjudandeflagga.
"""

from datetime import datetime
from statistics import median

MIN_DAGAR = 3


def ar_rea(historik: list[tuple[datetime, float]], nuvarande: float, flagga: bool, grans: float) -> bool:
    per_dag: dict = {}
    for tid, kr_per_kg in sorted(historik):
        per_dag[tid.date()] = kr_per_kg
    if len(per_dag) < MIN_DAGAR:
        return flagga
    return nuvarande <= (1 - grans) * median(per_dag.values()) + 1e-9

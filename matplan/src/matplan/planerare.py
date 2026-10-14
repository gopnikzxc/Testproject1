"""Planeraren: ren, deterministisk logik från katalog och mål till en plan.

I den här första versionen fyller lunch och middag hela dagsmålet.
Frukost och mellanmål tillkommer i #3, poängsättning i #4.
"""

import math
from dataclasses import dataclass
from itertools import product

from .katalog import Ingrediens

BLOCKDAGAR = 3
GRONSAKER_GRAM = 300
AVRUNDNING_GRAM = 5


class PlaneringsFel(Exception):
    pass


@dataclass(frozen=True)
class Rad:
    namn: str
    slot: str
    gram: int
    kcal: float
    protein: float
    kr: float


@dataclass(frozen=True)
class Maltid:
    rader: tuple[Rad, ...]

    @property
    def kcal(self) -> float:
        return sum(r.kcal for r in self.rader)

    @property
    def protein(self) -> float:
        return sum(r.protein for r in self.rader)

    @property
    def kr(self) -> float:
        return sum(r.kr for r in self.rader)


@dataclass(frozen=True)
class Dag:
    lunch: Maltid
    middag: Maltid

    @property
    def kcal(self) -> float:
        return self.lunch.kcal + self.middag.kcal

    @property
    def protein(self) -> float:
        return self.lunch.protein + self.middag.protein

    @property
    def kr(self) -> float:
        return self.lunch.kr + self.middag.kr


@dataclass(frozen=True)
class Plan:
    dagar: tuple[Dag, ...]


def _rad(ingrediens: Ingrediens, gram: int) -> Rad:
    return Rad(
        namn=ingrediens.namn,
        slot=ingrediens.slot,
        gram=gram,
        kcal=ingrediens.kcal_100g * gram / 100,
        protein=ingrediens.protein_100g * gram / 100,
        kr=ingrediens.kr_per_kg * gram / 1000,
    )


def _avrunda_upp(gram: float) -> int:
    return math.ceil(gram / AVRUNDNING_GRAM - 1e-9) * AVRUNDNING_GRAM


def _avrunda_ned(gram: float) -> int:
    return int(gram // AVRUNDNING_GRAM) * AVRUNDNING_GRAM


def _dimensionera(
    p: Ingrediens, k: Ingrediens, g: Ingrediens, kcal_tak: float, protein_golv: float
) -> Maltid | None:
    """Gram för protein- och kolhydratkällan så att måltiden når proteingolvet
    och fyller upp till kcal-taket. Grönsaker ligger på fast volym."""
    kvar_kcal = kcal_tak - g.kcal_100g * GRONSAKER_GRAM / 100
    kvar_protein = protein_golv - g.protein_100g * GRONSAKER_GRAM / 100

    # Lös  kcal: kp*xp + kk*xk = kvar_kcal,  protein: pp*xp + pk*xk = kvar_protein
    # med x i hektogram.
    kp, pp = p.kcal_100g, p.protein_100g
    kk, pk = k.kcal_100g, k.protein_100g
    determinant = kp * pk - kk * pp
    if determinant == 0:
        return None
    xk = (kp * kvar_protein - pp * kvar_kcal) / determinant
    xk = max(xk, 0.0)
    xp = max((kvar_protein - pk * xk) / pp, 0.0)

    protein_gram = _avrunda_upp(xp * 100)
    kolhydrat_gram = _avrunda_ned(xk * 100)
    while True:
        maltid = Maltid((_rad(p, protein_gram), _rad(k, kolhydrat_gram), _rad(g, GRONSAKER_GRAM)))
        if maltid.kcal <= kcal_tak or kolhydrat_gram == 0:
            break
        kolhydrat_gram -= AVRUNDNING_GRAM

    if maltid.kcal > kcal_tak or maltid.protein < protein_golv:
        return None
    if protein_gram == 0 or kolhydrat_gram == 0:
        return None
    return maltid


def planera(ingredienser: list[Ingrediens], kcal_mal: float, protein_mal: float) -> Plan:
    per_slot = {
        slot: sorted((i for i in ingredienser if i.slot == slot), key=lambda i: i.namn)
        for slot in ("protein", "kolhydrater", "grönsaker")
    }
    kandidater = []
    for p, k, g in product(per_slot["protein"], per_slot["kolhydrater"], per_slot["grönsaker"]):
        maltid = _dimensionera(p, k, g, kcal_mal / 2, protein_mal / 2)
        if maltid is not None:
            kandidater.append(maltid)

    if not kandidater:
        raise PlaneringsFel(
            f"Ingen kombination i katalogen når {protein_mal:g} g protein "
            f"inom {kcal_mal:g} kcal per dag."
        )

    # Billigaste måltiden; namnen avgör vid lika pris. Viktad poäng kommer i #4.
    basta = min(kandidater, key=lambda m: (round(m.kr, 6), [r.namn for r in m.rader]))
    dag = Dag(lunch=basta, middag=basta)
    return Plan(dagar=(dag,) * BLOCKDAGAR)

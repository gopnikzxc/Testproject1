"""Planeraren: ren, deterministisk logik från katalog och mål till en plan.

En dag är frukost, lunch, middag och mellanmål. Lunch och middag är samma
batch under ett rullande tredagarsblock. Alla äter samma ingredienser, men
varje person får egna gram som når personens kcal-tak och proteingolv.
Frukost och mellanmål är likadana varje dag. Bland kombinationerna som når
målen väljs den med bäst viktad poäng på proteintäthet, volym och kostnad.
"""

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from itertools import product

from .katalog import Ingrediens

BLOCKDAGAR = 3
GRONSAKER_GRAM = 300
BAR_GRAM = 100
AVRUNDNING_GRAM = 5

# Andel av dagens kcal och protein per måltid, före normalisering.
VIKT_FRUKOST = 2
VIKT_HUVUDMAL = 3
VIKT_MELLANMAL = 1


class PlaneringsFel(Exception):
    pass


@dataclass(frozen=True)
class Vikter:
    """Hur mycket proteintäthet, volym och låg kostnad väger vid valet."""

    protein: float = 1.0
    volym: float = 1.0
    kostnad: float = 1.0


@dataclass(frozen=True)
class Profil:
    namn: str
    kcal_mal: float
    protein_mal: float


@dataclass(frozen=True)
class Rad:
    namn: str
    slot: str
    gram: int
    kcal: float
    protein: float
    kr: float


@dataclass(frozen=True)
class Portion:
    person: str
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

    @property
    def ingredienser(self) -> tuple[str, ...]:
        return tuple(r.namn for r in self.rader)


@dataclass(frozen=True)
class Maltid:
    typ: str
    portioner: tuple[Portion, ...]

    def portion(self, person: str) -> Portion:
        return next(p for p in self.portioner if p.person == person)

    @property
    def ingredienser(self) -> tuple[str, ...]:
        return self.portioner[0].ingredienser

    @property
    def kr(self) -> float:
        return sum(p.kr for p in self.portioner)

    @property
    def protein_tathet(self) -> float:
        """Gram protein per 100 kcal, över alla portioner."""
        return 100 * sum(p.protein for p in self.portioner) / sum(p.kcal for p in self.portioner)

    @property
    def volym(self) -> float:
        """Gram mat per kcal, över alla portioner."""
        gram = sum(r.gram for p in self.portioner for r in p.rader)
        return gram / sum(p.kcal for p in self.portioner)

    @property
    def kr_per_g_protein(self) -> float:
        return self.kr / sum(p.protein for p in self.portioner)


@dataclass(frozen=True)
class Dag:
    datum: date
    maltider: tuple[Maltid, ...]

    def maltid(self, typ: str) -> Maltid:
        return next(m for m in self.maltider if m.typ == typ)

    def kcal(self, person: str) -> float:
        return sum(m.portion(person).kcal for m in self.maltider)

    def protein(self, person: str) -> float:
        return sum(m.portion(person).protein for m in self.maltider)

    @property
    def kr(self) -> float:
        return sum(m.kr for m in self.maltider)


@dataclass(frozen=True)
class Block:
    dagar: tuple[Dag, ...]

    @property
    def batch(self) -> Maltid:
        return self.dagar[0].maltid("lunch")

    @property
    def batchmangd(self) -> dict[str, int]:
        """Gram per ingrediens att laga till lunch och middag för hela blocket."""
        mangd: dict[str, int] = {}
        for dag in self.dagar:
            for typ in ("lunch", "middag"):
                for portion in dag.maltid(typ).portioner:
                    for rad in portion.rader:
                        mangd[rad.namn] = mangd.get(rad.namn, 0) + rad.gram
        return mangd


@dataclass(frozen=True)
class Plan:
    profiler: tuple[Profil, ...]
    block: tuple[Block, ...]
    priser_hamtade: datetime | None = None
    utan_butikspris: tuple[str, ...] = ()

    @property
    def dagar(self) -> tuple[Dag, ...]:
        return tuple(dag for block in self.block for dag in block.dagar)


def _rad(ingrediens: Ingrediens, slot: str, gram: int) -> Rad:
    return Rad(
        namn=ingrediens.namn,
        slot=slot,
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
    p: Ingrediens,
    k: Ingrediens,
    fast: Ingrediens,
    fast_gram: int,
    slotar: tuple[str, str, str],
    kcal_tak: float,
    protein_golv: float,
) -> tuple[Rad, ...] | None:
    """Gram för protein- och kolhydratkällan så att portionen når proteingolvet
    och fyller upp till kcal-taket. Den fasta ingrediensen ger volym."""
    kvar_kcal = kcal_tak - fast.kcal_100g * fast_gram / 100
    kvar_protein = protein_golv - fast.protein_100g * fast_gram / 100

    # Lös  kcal: kp*xp + kk*xk = kvar_kcal,  protein: pp*xp + pk*xk = kvar_protein
    # med x i hektogram.
    kp, pp = p.kcal_100g, p.protein_100g
    kk, pk = k.kcal_100g, k.protein_100g
    determinant = kp * pk - kk * pp
    if determinant == 0:
        return None
    xk = max((kp * kvar_protein - pp * kvar_kcal) / determinant, 0.0)
    xp = max((kvar_protein - pk * xk) / pp, 0.0)

    protein_gram = _avrunda_upp(xp * 100)
    kolhydrat_gram = _avrunda_ned(xk * 100)

    def rader_for(pg: int, kg: int) -> tuple[Rad, ...]:
        return (_rad(p, slotar[0], pg), _rad(k, slotar[1], kg), _rad(fast, slotar[2], fast_gram))

    # Avrundningen till hela 5 g kan tappa protein eller spräcka kcal-taket:
    # lägg till proteinkälla när protein saknas, dra från kolhydratkällan när
    # kcal-taket spräcks, tills båda håller.
    for _ in range(1000):
        if kolhydrat_gram <= 0:
            return None
        rader = rader_for(protein_gram, kolhydrat_gram)
        kcal = sum(r.kcal for r in rader)
        protein = sum(r.protein for r in rader)
        if kcal <= kcal_tak and protein >= protein_golv:
            break
        if protein < protein_golv:
            protein_gram += AVRUNDNING_GRAM
        else:
            kolhydrat_gram -= AVRUNDNING_GRAM
    else:
        return None
    if protein_gram == 0:
        return None
    return rader


def _kategori(ingredienser: list[Ingrediens], *kategorier: str) -> list[Ingrediens]:
    return sorted((i for i in ingredienser if i.kategori in kategorier), key=lambda i: i.namn)


def _rangordna(kandidater: list[Maltid], vikter: Vikter) -> list[Maltid]:
    """Bäst först. Varje mått normaliseras till 0..1 över kandidaterna och
    vägs ihop; låg kostnad räknas som bra."""

    def normalisera(varden: list[float]) -> list[float]:
        lagst, hogst = min(varden), max(varden)
        if hogst - lagst < 1e-12:
            return [0.0] * len(varden)
        return [(v - lagst) / (hogst - lagst) for v in varden]

    tathet = normalisera([m.protein_tathet for m in kandidater])
    volym = normalisera([m.volym for m in kandidater])
    kostnad = normalisera([m.kr_per_g_protein for m in kandidater])
    poang = [
        vikter.protein * t + vikter.volym * v - vikter.kostnad * k
        for t, v, k in zip(tathet, volym, kostnad)
    ]
    ordning = sorted(range(len(kandidater)), key=lambda i: (-round(poang[i], 9), kandidater[i].ingredienser))
    return [kandidater[i] for i in ordning]


def _valj(
    typ: str,
    kombinationer,
    profiler: tuple[Profil, ...],
    mal: dict[str, tuple[float, float]],
    dimensionera,
    vikter: Vikter,
    undvik: tuple[str, ...] | None = None,
) -> Maltid | None:
    """Kombinationen med bäst poäng bland dem som går att dimensionera för alla."""
    kandidater = []
    for kombination in kombinationer:
        portioner = []
        for profil in profiler:
            rader = dimensionera(kombination, *mal[profil.namn])
            if rader is None:
                break
            portioner.append(Portion(profil.namn, rader))
        else:
            kandidater.append(Maltid(typ, tuple(portioner)))
    if undvik is not None and any(m.ingredienser != undvik for m in kandidater):
        kandidater = [m for m in kandidater if m.ingredienser != undvik]
    if not kandidater:
        return None
    return _rangordna(kandidater, vikter)[0]


def _fel(maltid: str) -> PlaneringsFel:
    return PlaneringsFel(
        f"Ingen kombination i katalogen når allas proteinmål inom kcal-taket ({maltid})."
    )


def planera(
    ingredienser: list[Ingrediens],
    profiler: tuple[Profil, ...],
    start: date,
    plandagar: int = 7,
    frukost: bool = True,
    antal_mellanmal: int = 2,
    vikter: Vikter = Vikter(),
) -> Plan:
    vikt_total = 2 * VIKT_HUVUDMAL + (VIKT_FRUKOST if frukost else 0) + antal_mellanmal * VIKT_MELLANMAL

    def andel(profil: Profil, vikt: int) -> tuple[float, float]:
        return profil.kcal_mal * vikt / vikt_total, profil.protein_mal * vikt / vikt_total

    fasta_maltider: list[Maltid] = []

    if frukost:
        frukost_maltid = _valj(
            "frukost",
            product(_kategori(ingredienser, "mejeri"), _kategori(ingredienser, "flingor"), _kategori(ingredienser, "bär")),
            profiler,
            {p.namn: andel(p, VIKT_FRUKOST) for p in profiler},
            lambda k, kcal, protein: _dimensionera(*k, BAR_GRAM, ("protein", "flingor", "bär"), kcal, protein),
            vikter,
        )
        if frukost_maltid is None:
            raise _fel("frukost")
        fasta_maltider.append(frukost_maltid)

    # Mellanmål: en mejerivara var, i poängordning, dimensionerad till sin kcal-andel.
    mellanmal = _rangordna(
        [
            Maltid(
                "mellanmål",
                tuple(
                    Portion(
                        profil.namn,
                        (_rad(vara, "mellanmål", _avrunda_ned(andel(profil, VIKT_MELLANMAL)[0] / vara.kcal_100g * 100)),),
                    )
                    for profil in profiler
                ),
            )
            for vara in _kategori(ingredienser, "mejeri")
        ],
        vikter,
    ) if antal_mellanmal else []
    for nummer in range(antal_mellanmal):
        fasta_maltider.append(Maltid(f"mellanmål {nummer + 1}", mellanmal[nummer % len(mellanmal)].portioner))

    # Lunch och middag tar det som är kvar av dagens kcal, hälften var. Proteingolvet
    # är det som saknas till dagens mål, men minst måltidens egen andel, så att
    # huvudmålen inte blir proteinfattiga när mellanmålen redan når målet.
    huvudmal = {}
    for profil in profiler:
        kcal = profil.kcal_mal - sum(m.portion(profil.namn).kcal for m in fasta_maltider)
        protein = profil.protein_mal - sum(m.portion(profil.namn).protein for m in fasta_maltider)
        _, protein_andel = andel(profil, VIKT_HUVUDMAL)
        huvudmal[profil.namn] = (kcal / 2, max(protein / 2, protein_andel))

    huvudkombinationer = list(
        product(
            _kategori(ingredienser, "protein"),
            _kategori(ingredienser, "kolhydrater"),
            _kategori(ingredienser, "grönsaker"),
        )
    )
    block = []
    foregaende = None
    for blockstart in range(0, plandagar, BLOCKDAGAR):
        lunch = _valj(
            "lunch",
            huvudkombinationer,
            profiler,
            huvudmal,
            lambda k, kcal, protein: _dimensionera(*k, GRONSAKER_GRAM, ("protein", "kolhydrater", "grönsaker"), kcal, protein),
            vikter,
            undvik=foregaende,
        )
        if lunch is None:
            raise _fel("lunch och middag")
        middag = Maltid("middag", lunch.portioner)
        foregaende = lunch.ingredienser

        dagar = []
        for offset in range(blockstart, min(blockstart + BLOCKDAGAR, plandagar)):
            maltider = fasta_maltider[: int(frukost)] + [lunch, middag] + fasta_maltider[int(frukost) :]
            dagar.append(Dag(start + timedelta(days=offset), tuple(maltider)))
        block.append(Block(tuple(dagar)))

    return Plan(profiler=profiler, block=tuple(block))

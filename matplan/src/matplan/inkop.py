"""Inköpslistan: ren logik från behov i gram och butikspriser till vad som ska köpas.

Varje ingrediens köps i hela förpackningar (eller lösvikt om förpackningsstorlek
saknas). Listan jämför billigaste enskilda butik mot billigaste uppdelning.
"""

import math
from dataclasses import dataclass

from .bunkra import Bunkring
from .butiker import Produkt


@dataclass(frozen=True)
class Kop:
    produkt: Produkt
    antal: int | None  # förpackningar; None betyder lösvikt
    kostnad: float
    rea: bool = False


@dataclass(frozen=True)
class Listrad:
    ingrediens: str
    gram: int
    alternativ: dict[str, Kop]  # billigaste köpet per butik
    platshallar_kr: float  # kostnad med katalogens platshållarpris

    @property
    def billigast(self) -> tuple[str, Kop] | None:
        if not self.alternativ:
            return None
        return min(self.alternativ.items(), key=lambda bk: (round(bk[1].kostnad, 6), bk[0]))


@dataclass(frozen=True)
class Butikstotal:
    butik: str
    kostnad: float
    saknas: tuple[str, ...]


@dataclass(frozen=True)
class Inkopslista:
    rader: tuple[Listrad, ...]
    butiker: tuple[Butikstotal, ...]  # bäst först: kompletta, sedan billigast
    bunkring: tuple[Bunkring, ...] = ()  # accepterade bunkringsköp, utanför budgeten

    @property
    def bunkring_kr(self) -> float:
        return sum(b.kostnad for b in self.bunkring)

    @property
    def basta_butik(self) -> Butikstotal | None:
        return self.butiker[0] if self.butiker else None

    @property
    def delad_kostnad(self) -> float:
        """Varje ingrediens i den butik där den är billigast."""
        return sum(rad.billigast[1].kostnad for rad in self.rader if rad.billigast)

    @property
    def besparing(self) -> float:
        basta = self.basta_butik
        if basta is None or basta.saknas:
            return 0.0
        return basta.kostnad - self.delad_kostnad

    @property
    def platshallar_kr(self) -> float:
        return sum(rad.platshallar_kr for rad in self.rader)


def _kop(produkt: Produkt, gram: int, rea: bool) -> Kop:
    if produkt.forpackning_g:
        antal = math.ceil(gram / produkt.forpackning_g - 1e-9)
        return Kop(produkt, antal, antal * produkt.pris_kr, rea)
    return Kop(produkt, None, produkt.kr_per_kg * gram / 1000, rea)


def bygg_lista(
    behov: dict[str, int],
    produkter: dict[str, list[Produkt]],
    platshallarpris: dict[str, float],
    rea: frozenset[tuple[str, str]] = frozenset(),
) -> Inkopslista:
    """`behov`: gram att köpa per ingrediens. `produkter`: matchade produkter per ingrediens.
    `rea`: (butik, produkt_id) som är på rea."""
    rader = []
    for ingrediens in sorted(behov):
        gram = behov[ingrediens]
        if gram <= 0:
            continue
        alternativ: dict[str, Kop] = {}
        for produkt in produkter.get(ingrediens, []):
            kop = _kop(produkt, gram, (produkt.butik, produkt.produkt_id) in rea)
            nuvarande = alternativ.get(produkt.butik)
            if nuvarande is None or (kop.kostnad, produkt.kr_per_kg) < (nuvarande.kostnad, nuvarande.produkt.kr_per_kg):
                alternativ[produkt.butik] = kop
        rader.append(Listrad(ingrediens, gram, alternativ, platshallarpris[ingrediens] * gram / 1000))

    butiksnamn = sorted({butik for rad in rader for butik in rad.alternativ})
    totaler = [
        Butikstotal(
            butik,
            sum(rad.alternativ[butik].kostnad for rad in rader if butik in rad.alternativ),
            tuple(rad.ingrediens for rad in rader if butik not in rad.alternativ),
        )
        for butik in butiksnamn
    ]
    totaler.sort(key=lambda t: (len(t.saknas), round(t.kostnad, 6), t.butik))
    return Inkopslista(tuple(rader), tuple(totaler))

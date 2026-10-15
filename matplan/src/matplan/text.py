"""Gemensam svensk textformatering för CLI och export."""

from datetime import date

from .butiker import Produkt
from .inkop import Kop
from .naring import KALLNAMN

VECKODAGAR = ("mån", "tis", "ons", "tor", "fre", "lör", "sön")
MANADER = ("jan", "feb", "mar", "apr", "maj", "jun", "jul", "aug", "sep", "okt", "nov", "dec")


def datum(d: date) -> str:
    return f"{VECKODAGAR[d.weekday()]} {d.day} {MANADER[d.month - 1]}"


def kr(belopp: float) -> str:
    """111.5 -> "111,50 kr", 1041.81 -> "1 041,81 kr"."""
    return f"{belopp:,.2f}".replace(",", " ").replace(".", ",") + " kr"


def vikt(gram: float) -> str:
    """Under 1 kg i gram ("510 g"), annars i kg med upp till två decimaler ("1,02 kg", "3 kg")."""
    if gram < 1000:
        return f"{gram:.0f} g"
    return f"{gram / 1000:.2f}".rstrip("0").rstrip(".").replace(".", ",") + " kg"


def marke(varumarke: str) -> str:
    """Butikerna skriver ofta märken med versaler ("GARANT EKO" -> "Garant Eko")."""
    return varumarke.title() if varumarke.isupper() else varumarke


def produkttext(produkt: Produkt) -> str:
    """Det som står på hyllan: märke, namn och förpackningsstorlek."""
    delar = [marke(produkt.varumarke), produkt.namn]
    if produkt.forpackning_g:
        delar.append(vikt(produkt.forpackning_g))
    return " ".join(d for d in delar if d)


def mangd(antal: int | None, forpackning_g: float | None, gram: float) -> str:
    """"2 st (1,02 kg)" eller, för lösvikt, "lösvikt 3 kg"."""
    if antal is None or not forpackning_g:
        return f"lösvikt {vikt(gram)}"
    return f"{antal} st ({vikt(antal * forpackning_g)})"


def listrad(produkt: Produkt, antal: int | None, gram: float, kostnad: float) -> str:
    """"Garant Tonfisk Vatten 510 g – 2 st (1,02 kg) – 111,50 kr"."""
    return f"{produkttext(produkt)} – {mangd(antal, produkt.forpackning_g, gram)} – {kr(kostnad)}"


def forpackning(kop: Kop, gram: float) -> str:
    return mangd(kop.antal, kop.produkt.forpackning_g, gram)


def naringstext(produktkallor: tuple[tuple[str, str], ...]) -> str:
    """"Kycklingfilé: butiken · Vitkål: Livsmedelsverket"."""
    return " · ".join(f"{namn}: {KALLNAMN.get(kalla, kalla)}" for namn, kalla in produktkallor)

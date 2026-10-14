"""Butiksadaptrar bakom ett gemensamt gränssnitt.

Varje kedja är en modul som returnerar normaliserade `Produkt`-poster för en
söktermer i en konfigurerad butik. Endpoints är inofficiella webbutiks-API:er
och kan ändras; en adapter som går sönder ska kasta `ButiksFel` så att övriga
butiker fortfarande kan hämtas.
"""

import re
from dataclasses import dataclass
from typing import Protocol


class ButiksFel(Exception):
    pass


@dataclass(frozen=True)
class Produkt:
    butik: str
    produkt_id: str
    namn: str
    varumarke: str
    forpackning_g: float | None
    pris_kr: float
    kr_per_kg: float
    erbjudande: bool = False
    kategori: str = ""  # butikens egen kategori, t.ex. "Fryst / Frysta bär & frukt"
    beskrivning: str = ""  # t.ex. "500G 1,5% KESO"; används vid matchning men sparas inte


class Butik(Protocol):
    namn: str

    def sok(self, sokord: str) -> list[Produkt]: ...


def _ord(text: str) -> set[str]:
    return set(re.findall(r"\w+", text.casefold()))


def matchar(produktnamn: str, sokord: tuple[str, ...], beskrivning: str = "") -> bool:
    """Sant om någon sökterm passar: termens första ord finns som helt ord i
    produktnamnet och alla dess ord finns i namnet eller beskrivningen (där
    t.ex. fetthalten står). Kravet på första ordet i namnet hindrar att en
    smoothie med "blåbär" i beskrivningen blir blåbär."""
    namnord = _ord(produktnamn)
    allaord = namnord | _ord(beskrivning)
    for term in sokord:
        termord = re.findall(r"\w+", term.casefold())
        if termord and termord[0] in namnord and set(termord) <= allaord:
            return True
    return False


def ratt_kategori(produktkategori: str, butikskategori: tuple[str, ...]) -> bool:
    """Sant om butikens kategori innehåller något av orden, eller om något av
    dem saknas (butiken anger ingen kategori eller ingrediensen kräver ingen)."""
    if not produktkategori or not butikskategori:
        return True
    kategori = produktkategori.casefold()
    return any(ord in kategori for ord in butikskategori)

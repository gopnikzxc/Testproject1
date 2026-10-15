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
class ValdButik:
    """Butiken som hämtas och planeras mot: kedja, kedjans butiksnummer och
    namnet som priser och sortiment sparas under."""

    kedja: str  # adapterns nyckel, t.ex. "citygross"
    nummer: int
    namn: str


YTTERBY = ValdButik("citygross", 3240, "City Gross Ytterby")
WILLYS_KUNGALV = ValdButik("willys", 2104, "Willys Kungälv")


@dataclass(frozen=True)
class Butiksplats:
    """En butik i kedjans butikslista."""

    kedja: str
    id: str  # kedjans id för butikssidan (City Gross: siteId); inte butiksnumret
    namn: str  # t.ex. "City Gross Ytterby"
    ort: str
    postnummer: str  # fem siffror, t.ex. "44250"
    adress: str = ""
    lat: float | None = None
    lng: float | None = None


class Butiksregister(Protocol):
    """En kedjas butikslista."""

    kedja: str

    def butiker(self) -> list[Butiksplats]: ...

    def butiksnummer(self, plats: Butiksplats) -> int: ...


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
    beskrivning: str = ""  # t.ex. "500G 1,5% KESO"; förpackning och fetthalt
    ean: str = ""
    # Näringsvärden per 100 g (eller ml) enligt butikens data; None om de saknas.
    kcal: float | None = None
    protein: float | None = None
    fett: float | None = None
    kolhydrater: float | None = None
    fiber: float | None = None
    # Sätts av kärnan: varifrån näringsvärdena kommer ("butik", "livsmedelsverket",
    # "openfoodfacts" eller "katalog"; None = inga värden) och produktens slot.
    naringskalla: str | None = None
    slot: str | None = None


class Butik(Protocol):
    namn: str
    nyckel: str  # kedjan, som i ValdButik.kedja, t.ex. "citygross"

    def sok(self, sokord: str, butikskategori: tuple[str, ...] = ()) -> list[Produkt]:
        """Produkter som matchar söktermen. `butikskategori` är ingrediensens
        kategoriord; en butik vars sökträffar saknar kategori kan använda dem
        för att filtrera på sin sida (se Willys)."""
        ...


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


def utesluten(produktnamn: str, uteslut: tuple[str, ...]) -> bool:
    """Sant om något av orden står som helt ord i produktnamnet."""
    return bool(_ord(produktnamn) & {o.casefold() for o in uteslut})


def ratt_kategori(produktkategori: str, butikskategori: tuple[str, ...]) -> bool:
    """Sant om butikens kategori innehåller något av orden, eller om något av
    dem saknas (butiken anger ingen kategori eller ingrediensen kräver ingen)."""
    if not produktkategori or not butikskategori:
        return True
    kategori = produktkategori.casefold()
    return any(ord in kategori for ord in butikskategori)

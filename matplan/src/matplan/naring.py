"""Näringsvärden per 100 g från Livsmedelsverket, med Open Food Facts som
reserv för märkesvaror.

- Livsmedelsverkets livsmedelsdatabas (CC BY 4.0, ange Livsmedelsverket som
  källa): `/livsmedel/api/v1/livsmedel/{nummer}/naringsvarden`.
- Open Food Facts (ODbL): `/api/v2/product/{ean}.json`, för varor som saknas
  hos Livsmedelsverket, t.ex. keso 1,5 % och grekisk yoghurt 0 %.

Livsmedelsverkets hela lista (`/livsmedel?limit=…`, drygt 2600 livsmedel)
hämtas en gång och används för att föreslå närmaste livsmedel för produkter
som saknar butikens näringsvärden ("Vitkål Sverige" -> "Vitkål").
"""

import re
import urllib.error
from dataclasses import dataclass

from .http import HttpKlient

LIVSMEDELSVERKET = "https://dataportal.livsmedelsverket.se/livsmedel/api/v1"
OPEN_FOOD_FACTS = "https://world.openfoodfacts.org/api/v2"

KALLHANVISNING = {
    "livsmedelsverket": "Näringsvärden: Livsmedelsverkets livsmedelsdatabas (CC BY 4.0)",
    "openfoodfacts": "Näringsvärden för märkesvaror: Open Food Facts (ODbL)",
}

# Hur produktens näringsvärden visas.
KALLNAMN = {
    "butik": "butiken",
    "livsmedelsverket": "Livsmedelsverket",
    "openfoodfacts": "Open Food Facts",
    "katalog": "katalogen (inte hämtad än)",
}
LISTSTORLEK = 3000


def _ord(text: str) -> list[str]:
    return [o for o in re.findall(r"[^\W\d_]+", text.casefold()) if len(o) > 1 or o in ("i", "m")]


def _likhet(ord_: str, produktord: list[str], svans: bool = True) -> int:
    """2 för samma ord, 1 för ett produktord som börjar med ordet ("sejfilé" ~
    "sej") eller, med `svans`, slutar likadant på minst fyra bokstäver
    ("kycklingfilé" ~ "bröstfilé"), annars 0."""
    basta = 0
    for p in produktord:
        if p == ord_:
            return 2
        if len(ord_) >= 3 and p.startswith(ord_):
            basta = 1
        elif svans and len(ord_) >= 4 and len(p) >= 4 and ord_[-4:] == p[-4:]:
            basta = 1
    return basta


def foresla(namn: str, lista: list[tuple[int, str]]) -> tuple[int, str] | None:
    """Närmaste livsmedel i Livsmedelsverkets lista för ett produktnamn: mest
    gemensamma ord (se `_likhet`), sedan färst extra ord hos livsmedlet, sedan
    kortast namn. Livsmedlets första ord måste vara ett produktord eller början
    på ett. Lika slut räknas bara för produktord som inte redan finns som ord."""
    produktord = _ord(namn)
    if not produktord:
        return None
    basta, basta_poang = None, None
    for nummer, lmv_namn in lista:
        lmv_ord = list(dict.fromkeys(_ord(lmv_namn)))
        if not lmv_ord or not _likhet(lmv_ord[0], produktord, svans=False):
            continue
        lediga = [p for p in produktord if p not in lmv_ord]
        likheter = [2 if o in produktord else _likhet(o, lediga) for o in lmv_ord]
        poang = (sum(likheter), -sum(1 for v in likheter if not v), -len(lmv_namn), -nummer)
        if basta_poang is None or poang > basta_poang:
            basta, basta_poang = (nummer, lmv_namn), poang
    return basta


class NaringsFel(Exception):
    pass


class NaringsNatverksFel(NaringsFel):
    """Källan gick inte att nå; försök igen vid nästa hämtning."""


@dataclass(frozen=True)
class Naring:
    kalla: str  # "livsmedelsverket" eller "openfoodfacts"
    kcal: float
    protein: float
    fett: float | None
    kolhydrater: float | None
    fiber: float | None
    vatten: float | None


def _hamta(http: HttpKlient, url: str, kalla: str):
    try:
        return http.hamta_json(url)
    except (urllib.error.URLError, TimeoutError) as fel:
        raise NaringsNatverksFel(f"Kunde inte nå {kalla}: {fel}") from fel
    except ValueError as fel:
        raise NaringsFel(f"Oväntat svar från {kalla}: {fel}") from fel


class Livsmedelsverket:
    def __init__(self, http: HttpKlient):
        self._http = http

    def lista(self) -> list[tuple[int, str]]:
        """Alla livsmedel: (nummer, namn)."""
        svar = _hamta(self._http, f"{LIVSMEDELSVERKET}/livsmedel?offset=0&limit={LISTSTORLEK}&sprak=1", "Livsmedelsverket")
        try:
            return [(int(rad["nummer"]), str(rad["namn"]).strip()) for rad in svar["livsmedel"]]
        except (KeyError, TypeError, ValueError) as fel:
            raise NaringsFel(f"Oväntad livsmedelslista från Livsmedelsverket ({fel})") from fel

    def hamta(self, nummer: int) -> Naring:
        rader = _hamta(self._http, f"{LIVSMEDELSVERKET}/livsmedel/{nummer}/naringsvarden?sprak=1", "Livsmedelsverket")
        try:
            varden = {}
            for rad in rader:
                # Bara "per 100 g ätlig del"; vissa rader saknar koden men har viktGram 100.
                if rad.get("matrisenhetkod", "W") != "W" or rad.get("viktGram", 100) != 100:
                    continue
                kod = "ENERC_KCAL" if rad["euroFIRkod"] == "ENERC" and rad["enhet"] == "kcal" else rad["euroFIRkod"]
                varden[kod] = float(rad["varde"])
            return Naring(
                "livsmedelsverket",
                kcal=varden["ENERC_KCAL"],
                protein=varden["PROT"],
                fett=varden.get("FAT"),
                kolhydrater=varden.get("CHO"),
                fiber=varden.get("FIBT"),
                vatten=varden.get("WATER"),
            )
        except (KeyError, TypeError, ValueError) as fel:
            raise NaringsFel(f"Livsmedelsverket saknar kcal/protein för nummer {nummer} ({fel})") from fel


class OpenFoodFacts:
    def __init__(self, http: HttpKlient):
        self._http = http

    def hamta(self, ean: str) -> Naring:
        svar = _hamta(
            self._http, f"{OPEN_FOOD_FACTS}/product/{ean}.json?fields=product_name,nutriments", "Open Food Facts"
        )
        try:
            if svar.get("status") != 1:
                raise NaringsFel(f"Open Food Facts har ingen vara med EAN {ean}")
            n = svar["product"]["nutriments"]

            def tal(nyckel):
                varde = n.get(nyckel)
                return None if varde is None else float(varde)

            return Naring(
                "openfoodfacts",
                kcal=float(n["energy-kcal_100g"]),
                protein=float(n["proteins_100g"]),
                fett=tal("fat_100g"),
                kolhydrater=tal("carbohydrates_100g"),
                fiber=tal("fiber_100g"),
                vatten=None,
            )
        except (KeyError, TypeError, ValueError, AttributeError) as fel:
            raise NaringsFel(f"Open Food Facts saknar kcal/protein för EAN {ean} ({fel})") from fel

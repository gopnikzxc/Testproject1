"""Näringsvärden per 100 g från Livsmedelsverket, med Open Food Facts som
reserv för märkesvaror.

- Livsmedelsverkets livsmedelsdatabas (CC BY 4.0, ange Livsmedelsverket som
  källa): `/livsmedel/api/v1/livsmedel/{nummer}/naringsvarden`.
- Open Food Facts (ODbL): `/api/v2/product/{ean}.json`, för varor som saknas
  hos Livsmedelsverket, t.ex. keso 1,5 % och grekisk yoghurt 0 %.
"""

import urllib.error
from dataclasses import dataclass

from .http import HttpKlient

LIVSMEDELSVERKET = "https://dataportal.livsmedelsverket.se/livsmedel/api/v1"
OPEN_FOOD_FACTS = "https://world.openfoodfacts.org/api/v2"

KALLHANVISNING = {
    "livsmedelsverket": "Näringsvärden: Livsmedelsverkets livsmedelsdatabas (CC BY 4.0)",
    "openfoodfacts": "Näringsvärden för märkesvaror: Open Food Facts (ODbL)",
}


class NaringsFel(Exception):
    pass


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
        raise NaringsFel(f"Kunde inte nå {kalla}: {fel}") from fel
    except ValueError as fel:
        raise NaringsFel(f"Oväntat svar från {kalla}: {fel}") from fel


class Livsmedelsverket:
    def __init__(self, http: HttpKlient):
        self._http = http

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

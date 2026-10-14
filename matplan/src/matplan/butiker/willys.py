"""Willys: produktsök med butikens sortiment och priser via webbutikens API.

Butiken väljs i sessionen: hämta en CSRF-token (`/axfood/rest/csrf-token`)
och anropa `POST /axfood/rest/store/activate?storeId=…` med den i
`X-CSRF-TOKEN`; därefter ger `/search` den butikens sortiment. Willys
Kungälv Komarken (Vikingagatan 1) är butik 2104 i `/axfood/rest/store`.

Sökträffarna saknar kategori, men sökningen har en kategori-facett vars
värden kan användas som filter (`q=broccoli:category:Grönsaker & kryddor`).
Adaptern söker därför en gång brett och sedan en gång per facett som passar
ingrediensens butikskategori, och märker produkterna med facettens namn.
"""

import json
import urllib.error

from ..http import HttpKlient
from . import ButiksFel, Produkt, ratt_kategori

BAS = "https://www.willys.se"
KUNGALV = "2104"
# Ägg jämförpris anges per styck; räkna om med en normalstor äggvikt.
GRAM_PER_AGG = 60


def _kronor(text: str) -> float:
    """"57,80 kr" -> 57.8"""
    return float(text.replace("kr", "").replace("\xa0", "").replace(" ", "").replace(",", "."))


class Willys:
    def __init__(self, http: HttpKlient, butik_id: str = KUNGALV, namn: str = "Willys Kungälv"):
        self._http = http
        self._butik_id = butik_id
        self.namn = namn
        self._aktiverad = False

    def sok(self, sokord: str, butikskategori: tuple[str, ...] = ()) -> list[Produkt]:
        try:
            self._aktivera()
            svar = self._sok(sokord)
            if not butikskategori:
                return self._produkter(svar, "")
            facett = next((f for f in svar.get("facets") or [] if f.get("code") == "category"), None)
            produkter: dict[str, Produkt] = {}
            for varde in (facett or {}).get("values", []):
                if not ratt_kategori(varde["name"], butikskategori):
                    continue
                for produkt in self._produkter(self._sok(varde["query"]["query"]["value"]), varde["name"]):
                    produkter[produkt.produkt_id] = produkt
            return list(produkter.values())
        except (urllib.error.URLError, TimeoutError) as fel:
            raise ButiksFel(f"Kunde inte nå Willys: {fel}") from fel
        except (ValueError, KeyError, TypeError, AttributeError) as fel:
            raise ButiksFel(f"Oväntat svar från Willys ({type(fel).__name__}: {fel})") from fel

    def _aktivera(self) -> None:
        """Väljer butiken i sessionen, en gång per adapterinstans (en hämtning)."""
        if self._aktiverad:
            return
        token = json.loads(self._http.skicka(f"{BAS}/axfood/rest/csrf-token", metod="GET"))
        self._http.skicka(
            f"{BAS}/axfood/rest/store/activate?storeId={self._butik_id}&activelySelected=true&forceAsPickingStore=false",
            headers={"X-CSRF-TOKEN": token},
        )
        self._aktiverad = True

    def _sok(self, fraga: str) -> dict:
        return self._http.hamta_json(
            f"{BAS}/search", {"q": fraga, "size": 100, "page": 0}, cachenyckel=f"willys:{self._butik_id}:"
        )

    def _produkter(self, svar: dict, kategori: str) -> list[Produkt]:
        return [p for p in (self._produkt(rad, kategori) for rad in svar["results"]) if p is not None]

    def _produkt(self, rad: dict, kategori: str) -> Produkt | None:
        try:
            if not rad.get("online", True) or rad.get("outOfStock"):
                return None
            pris = float(rad["priceValue"])
            jamfor = _kronor(rad["comparePrice"])
            enhet = rad["comparePriceUnit"]
            per_kg_pris = rad.get("priceUnit") == "kr/kg" or rad["code"].endswith("_KG")

            if enhet == "kg":
                kr_per_kg = jamfor
                forpackning = None if per_kg_pris else round(pris / jamfor * 1000)
            elif enhet == "st" and "ägg" in rad["name"].casefold():
                kr_per_kg = jamfor / GRAM_PER_AGG * 1000
                forpackning = round(pris / jamfor) * GRAM_PER_AGG
            else:
                return None  # liter eller styck utan säker omräkning till kg

            return Produkt(
                butik=self.namn,
                produkt_id=rad["code"],
                namn=rad["name"],
                varumarke=rad.get("manufacturer") or "",
                forpackning_g=float(forpackning) if forpackning else None,
                pris_kr=pris,
                kr_per_kg=float(kr_per_kg),
                erbjudande=bool(rad.get("potentialPromotions") or rad.get("savingsAmount")),
                kategori=kategori,
                beskrivning=rad.get("productLine2") or "",
            )
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            return None  # en enskild konstig produkt ska inte fälla sökningen

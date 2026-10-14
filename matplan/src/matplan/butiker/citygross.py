"""City Gross: produktsök med butikspriser via webbutikens Loop54-API.

Butiksnumret hittas via webbutikens GraphQL (`lindbakstorenumber(siteId)`);
Ytterby har siteId 31 i `/api/v1/PageData/stores` och butiksnummer 3240.
Med `store=<butiksnummer>` returnerar sökningen den butikens sortiment och
priser (`productStoreDetails.id` blir butiksnumret).
"""

import urllib.error

from ..http import HttpKlient
from . import ButiksFel, Produkt

BAS = "https://www.citygross.se/api/v1"
YTTERBY = 3240
# Ägg jämförpris anges per styck; räkna om med en normalstor äggvikt.
GRAM_PER_AGG = 60


class CityGross:
    nyckel = "citygross"

    def __init__(self, http: HttpKlient, butiksnummer: int = YTTERBY, namn: str = "City Gross Ytterby"):
        self._http = http
        self._butiksnummer = butiksnummer
        self.namn = namn

    def sok(self, sokord: str, butikskategori: tuple[str, ...] = ()) -> list[Produkt]:
        # Sökträffarna har egen kategori; filtreringen sker i kärnan.
        try:
            svar = self._http.hamta_json(
                f"{BAS}/Loop54/search",
                {"searchQuery": sokord, "take": 50, "store": self._butiksnummer},
            )
            produkter = svar["searchResults"]["products"]
        except (urllib.error.URLError, TimeoutError) as fel:
            raise ButiksFel(f"Kunde inte nå City Gross: {fel}") from fel
        except (ValueError, KeyError, TypeError) as fel:
            raise ButiksFel(f"Oväntat svar från City Gross ({type(fel).__name__}: {fel})") from fel
        return [p for p in (self._produkt(rad) for rad in produkter) if p is not None]

    def _produkt(self, rad: dict) -> Produkt | None:
        try:
            detaljer = rad["productStoreDetails"]
            if not detaljer or not detaljer.get("p_has_price"):
                return None
            priser = detaljer["prices"]
            pris = priser["currentPrice"]
            jamfor, enhet = pris["comparativePrice"], pris["comparativePriceUnit"]
            netto = (rad.get("netContent") or {}).get("value")

            if enhet == "KGM":
                kr_per_kg = jamfor
            elif enhet == "PCE" and "ägg" in rad["name"].casefold():
                kr_per_kg = jamfor / GRAM_PER_AGG * 1000
                netto = round(pris["price"] / jamfor) * GRAM_PER_AGG if jamfor else None
            else:
                return None  # styckpris eller liter utan säker omräkning till kg

            # Varor som säljs per kg (id-suffix _KG) har bara en ungefärlig styckvikt.
            forpackning = None if pris["unit"] == "KGM" or rad["id"].endswith("_KG") else netto
            return Produkt(
                butik=self.namn,
                produkt_id=rad["id"],
                namn=rad["name"],
                varumarke=rad.get("brand") or "",
                forpackning_g=float(forpackning) if forpackning else None,
                pris_kr=float(pris["price"]),
                kr_per_kg=float(kr_per_kg),
                erbjudande=bool(priser.get("hasDiscount") or priser.get("hasPromotion")),
                kategori=" / ".join(k for k in (rad.get("superCategory"), rad.get("category")) if k),
                beskrivning=rad.get("subtitle") or "",
            )
        except (KeyError, TypeError, ZeroDivisionError):
            return None  # en enskild konstig produkt ska inte fälla sökningen

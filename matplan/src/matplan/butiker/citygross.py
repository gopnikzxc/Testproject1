"""City Gross: produktsök med butikspriser via webbutikens Loop54-API.

Butiksnumret hittas via webbutikens GraphQL (`lindbakstorenumber(siteId)`);
Ytterby har siteId 31 i `/api/v1/PageData/stores` och butiksnummer 3240.
Med `store=<butiksnummer>` returnerar sökningen den butikens sortiment och
priser (`productStoreDetails.id` blir butiksnumret).

Hela sortimentet listas via kategorin "Matvaror" (sida 69) i sidor om 2000
(`/Loop54/category/69/products?skip=&take=&store=`). Bara livsmedel behålls:
icke-mat, godis, snacks och vissa underkategorier (glass, fikabröd, kex,
kryddor, såser, smör m.m.) sorteras bort.
"""

import urllib.error

from ..http import HttpKlient
from . import ButiksFel, Produkt

BAS = "https://www.citygross.se/api/v1"
YTTERBY = 3240
MATVAROR = 69
SIDSTORLEK = 2000

# Butikens toppkategorier och underkategorier som inte ska med (gemener).
EJ_LIVSMEDEL = {
    "apotek & receptfria läkemedel", "blommor", "godis", "hem & fritid", "husapotek", "husdjur",
    "hushåll", "köket", "skönhet & hygien", "snacks", "tobak",
}
EJ_UNDERKATEGORI = {
    "glass", "fikabröd", "kex & tilltugg", "kryddor & smaksättare", "smör & margarin", "kylda såser",
    "såser & tillbehör", "kryddsmör", "örter & smaksättare", "socker & sötningsmedel",
    "desserter & glasstillbehör", "efterrätter", "vitaminer & mineraler", "barntillbehör", "blöjor",
    "tvättservetter & barnvård",
}


def ar_livsmedel(toppkategori: str, underkategori: str) -> bool:
    return (
        toppkategori.strip().casefold() not in EJ_LIVSMEDEL
        and underkategori.strip().casefold() not in EJ_UNDERKATEGORI
    )


def _naring(rad: dict) -> dict[str, float] | None:
    """Näringsvärden per 100 g/ml ur butikens data. Bara deklarationer med uttalad
    bas i gram eller milliliter räknas (omräknade till 100); tomma platshållare
    hoppas över. Oförberedd vara ("som såld", preparationState 0) går först."""
    deklarationer = ((rad.get("foodAndBeverageExtension") or {}).get("nutrientInformations")) or []
    giltiga = [
        d for d in deklarationer
        if d.get("nutrients") and (d.get("nutrientBasisQuantity") or 0) > 0
        and d.get("nutrientBasisQuantityUnit") in ("gram", "milliliter")
    ]
    if not giltiga:
        return None
    basta = min(giltiga, key=lambda d: (d.get("preparationState") or 0, d["nutrientBasisQuantity"] != 100))
    faktor = 100 / basta["nutrientBasisQuantity"]
    varden: dict[str, float] = {}
    for n in basta["nutrients"]:
        kod, enhet, varde = n.get("typeCode"), n.get("unitOfMeasure"), n.get("value")
        if varde is None:
            continue
        if kod == "ENER-" and enhet == "kilokalori":
            varden["kcal"] = float(varde) * faktor
        elif kod in ("PRO-", "FAT", "CHOAVL", "FIBGT"):
            varden[{"PRO-": "protein", "FAT": "fett", "CHOAVL": "kolhydrater", "FIBGT": "fiber"}[kod]] = float(varde) * faktor
    if "kcal" not in varden or "protein" not in varden:
        return None
    return varden
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

    def sortiment(self, framsteg=None) -> list[Produkt]:
        """Hela butikens livsmedelssortiment, sida för sida."""
        produkter: list[Produkt] = []
        skip, totalt = 0, None
        try:
            while totalt is None or skip < totalt:
                if framsteg:
                    framsteg(self.namn, f"sortiment {skip}–{skip + SIDSTORLEK}")
                svar = self._http.hamta_json(
                    f"{BAS}/Loop54/category/{MATVAROR}/products",
                    {"skip": skip, "take": SIDSTORLEK, "store": self._butiksnummer},
                )
                totalt = int(svar["totalCount"])
                rader = svar["items"]
                for rad in rader:
                    if ar_livsmedel(rad.get("superCategory") or "", rad.get("category") or ""):
                        produkt = self._produkt(rad)
                        if produkt is not None:
                            produkter.append(produkt)
                if not rader:
                    break
                skip += SIDSTORLEK
        except (urllib.error.URLError, TimeoutError) as fel:
            raise ButiksFel(f"Kunde inte nå City Gross: {fel}") from fel
        except (ValueError, KeyError, TypeError) as fel:
            raise ButiksFel(f"Oväntat svar från City Gross ({type(fel).__name__}: {fel})") from fel
        return produkter

    def _produkt(self, rad: dict) -> Produkt | None:
        try:
            detaljer = rad["productStoreDetails"]
            if not detaljer or not detaljer.get("p_has_price"):
                return None
            priser = detaljer["prices"]
            pris = priser["currentPrice"]
            jamfor, enhet = pris["comparativePrice"], pris["comparativePriceUnit"]
            netto = (rad.get("netContent") or {}).get("value")

            if enhet in ("KGM", "LTR"):
                kr_per_kg = jamfor  # dryck: kr per liter räknas som kr per kg
            elif enhet == "PCE" and "ägg" in rad["name"].casefold():
                kr_per_kg = jamfor / GRAM_PER_AGG * 1000
                netto = round(pris["price"] / jamfor) * GRAM_PER_AGG if jamfor else None
            else:
                kr_per_kg = 0.0  # styckpris utan säker omräkning; sökbar men inte planerbar
            naring = _naring(rad) or {}

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
                ean=rad.get("gtin") or "",
                **naring,
            )
        except (KeyError, TypeError, ZeroDivisionError):
            return None  # en enskild konstig produkt ska inte fälla sökningen

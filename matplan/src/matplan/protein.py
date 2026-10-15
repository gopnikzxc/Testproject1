"""Proteintyp och proteinkvalitet.

Varje produkt och grupp får en proteintyp ur butikskategori och namn. Protein
räknas med en kvalitetsfaktor som ungefär följer PDCAAS; faktorerna kan
ändras i inställningarna (`kvalitet_<typ>`). Typen kan sättas för hand.
"""

import re

PROTEINTYPER = ("animaliskt", "ägg", "mejeri", "soja", "baljväxt", "spannmål", "övrigt")

STANDARDKVALITET = {
    "animaliskt": 1.0,
    "ägg": 1.0,
    "mejeri": 1.0,
    "soja": 0.9,
    "baljväxt": 0.7,
    "spannmål": 0.5,
    "övrigt": 0.6,
}

# Namn: delsträngar som är säkra var som helst i ett ord, och ordbörjan för korta ord.
_DJUR_DELORD = ("kyckling", "kalkon", "tonfisk", "fläsk", "skinka", "räk", "nötfärs", "nötkött", "köttbull", "högrev")
_DJUR_ORDBORJAN = ("lax", "sej", "torsk", "lamm", "korv", "fisk", "biff", "kött", "bacon", "hamburgare", "kotlett")
_DJUR_KATEGORI = ("kött", "fågel", "fisk", "skaldjur", "chark", "färser", "korv", "bacon")
_SOJA = ("soja", "tofu", "tempeh", "edamame")
_BALJVAXT_DELORD = ("bönor", "böna", "linser", "kikärt", "hummus", "falafel")
_MEJERI_ORD = ("keso", "kvarg", "yoghurt", "skyr", "mjölk", "ost", "filmjölk", "cottage")
_MEJERI_KATEGORI = ("mejeri", "kvarg", "yoghurt", "cottage", "mjölk")
_SPANNMAL_ORD = (
    "pasta", "havre", "havregryn", "gryn", "bröd", "couscous", "bulgur", "quinoa", "nudlar", "spaghetti",
    "makaroner", "penne", "tortilla", "flingor", "müsli", "musli", "mjöl",
)
_SPANNMAL_KATEGORI = ("pasta, ris", "flingor", "bröd", "gryn", "mjöl")


def _ord(text: str) -> list[str]:
    return re.findall(r"[^\W\d_]+", text.casefold())


def proteintyp(kategori: str = "", namn: str = "") -> str:
    """Proteintyp ur butikskategori och namn. Kött och fisk i namnet går före
    baljväxter (t.ex. tonfisk med bönor); kategorin avgör när namnet inte gör det."""
    kategori = kategori.casefold()
    ord_ = _ord(namn)
    text = " ".join(ord_)
    if any(s in text for s in _SOJA):
        return "soja"
    if any(d in text for d in _DJUR_DELORD) or any(o.startswith(_DJUR_ORDBORJAN) for o in ord_):
        return "animaliskt"
    if any(b in text for b in _BALJVAXT_DELORD) or any(o.startswith("ärt") for o in ord_) or "bönor" in kategori:
        return "baljväxt"
    if "ägg" in ord_ or kategori.endswith("/ ägg") or kategori == "ägg":
        return "ägg"
    if "havre" in text and "dryck" in text:
        return "spannmål"
    if any(o in _MEJERI_ORD for o in ord_) or any(m in kategori for m in _MEJERI_KATEGORI):
        return "mejeri"
    if any(k in kategori for k in _DJUR_KATEGORI):
        return "animaliskt"
    if (
        any(o in _SPANNMAL_ORD or o.endswith("ris") or "pasta" in o for o in ord_)
        or any(k in kategori for k in _SPANNMAL_KATEGORI)
    ):
        return "spannmål"
    return "övrigt"

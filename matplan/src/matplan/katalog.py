"""Inbyggd startkatalog med ingredienser.

Näringsvärden per 100 g (rå/okokt vara) är ungefärliga och handinmatade
tills Livsmedelsverket kopplas in (#5). Priserna är platshållare som används
när en ingrediens saknar butikspris från `matplan refresh`.

`sokord` är svenska söktermer mot butikerna; en produkt matchar om alla ord
i någon av termerna finns som hela ord i produktnamnet. `butikskategori` är
ord som butikens kategori för produkten måste innehålla (om butiken anger
kategori), så att t.ex. kattmat, färdigrätter och inlagd gurka sorteras bort.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Ingrediens:
    namn: str
    kategori: str
    kcal_100g: float
    protein_100g: float
    kr_per_kg: float
    sokord: tuple[str, ...] = ()
    forvaring: str = "kyl"  # "fryst", "torrvara" eller "kyl" (färskt, köps bara för planen)
    butikskategori: tuple[str, ...] = ()


_GRONT = ("frukt & grönt", "grönsaker", "rotfrukter")

STARTKATALOG = (
    Ingrediens("Kycklingfilé", "protein", 106, 23.1, 99, ("kycklingfilé", "kyckling filé", "kyckling bröstfilé"), "fryst", ("fågel", "kyckling")),
    Ingrediens("Ägg", "protein", 140, 12.4, 45, ("ägg",), butikskategori=("ägg",)),
    Ingrediens("Torskfilé, fryst", "protein", 75, 17.5, 110, ("torskfilé",), "fryst", ("fisk",)),
    Ingrediens("Nötfärs 10 %", "protein", 175, 19.0, 110, ("nötfärs 10",), "fryst", ("färs", "kött")),
    Ingrediens("Keso 1,5 %", "mejeri", 73, 12.3, 55, ("keso",), butikskategori=("mejeri", "cottage")),
    Ingrediens("Kvarg naturell", "mejeri", 61, 11.0, 45, ("kvarg naturell",), butikskategori=("mejeri", "kvarg")),
    Ingrediens("Grekisk yoghurt 2 %", "mejeri", 73, 9.0, 40, ("grekisk yoghurt naturell",), butikskategori=("yoghurt",)),
    Ingrediens("Potatis", "kolhydrater", 77, 2.0, 15, ("potatis",), butikskategori=_GRONT),
    Ingrediens("Ris, okokt", "kolhydrater", 350, 7.0, 30, ("jasminris", "basmatiris", "ris"), "torrvara", ("ris",)),
    Ingrediens("Fullkornspasta, okokt", "kolhydrater", 350, 13.0, 30, ("fullkornspasta",), "torrvara", ("pasta",)),
    Ingrediens("Havregryn", "flingor", 370, 13.0, 20, ("havregryn",), "torrvara", ("flingor", "gryn")),
    Ingrediens("Broccoli, fryst", "grönsaker", 34, 3.0, 35, ("broccoli",), "fryst", ("frysta grönsaker",)),
    Ingrediens("Vitkål", "grönsaker", 27, 1.3, 18, ("vitkål",), butikskategori=_GRONT),
    Ingrediens("Morot", "grönsaker", 37, 0.6, 15, ("morötter",), butikskategori=_GRONT),
    Ingrediens("Gurka", "grönsaker", 12, 0.7, 30, ("gurka",), butikskategori=_GRONT),
    Ingrediens("Blåbär, frysta", "bär", 57, 0.7, 50, ("blåbär",), "fryst", ("frysta bär", "fryst frukt", "frysta frukt")),
)

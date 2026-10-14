"""Inbyggd startkatalog med ingredienser.

Näringsvärden per 100 g (rå/okokt vara) är ungefärliga och handinmatade
tills Livsmedelsverket kopplas in (#5). Priserna är platshållare som används
när en ingrediens saknar butikspris från `matplan refresh`.

`sokord` är svenska söktermer mot butikerna; en produkt matchar om alla ord
i någon av termerna finns som hela ord i produktnamnet.
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


STARTKATALOG = (
    Ingrediens("Kycklingfilé", "protein", 106, 23.1, 99, ("kycklingfilé",), "fryst"),
    Ingrediens("Ägg", "protein", 140, 12.4, 45, ("ägg",)),
    Ingrediens("Torskfilé, fryst", "protein", 75, 17.5, 110, ("torskfilé",), "fryst"),
    Ingrediens("Nötfärs 10 %", "protein", 175, 19.0, 110, ("nötfärs",), "fryst"),
    Ingrediens("Keso 1,5 %", "mejeri", 73, 12.3, 55, ("keso",)),
    Ingrediens("Kvarg naturell", "mejeri", 61, 11.0, 45, ("kvarg naturell",)),
    Ingrediens("Grekisk yoghurt 2 %", "mejeri", 73, 9.0, 40, ("grekisk yoghurt",)),
    Ingrediens("Potatis", "kolhydrater", 77, 2.0, 15, ("potatis",)),
    Ingrediens("Ris, okokt", "kolhydrater", 350, 7.0, 30, ("jasminris", "basmatiris", "ris"), "torrvara"),
    Ingrediens("Fullkornspasta, okokt", "kolhydrater", 350, 13.0, 30, ("fullkornspasta",), "torrvara"),
    Ingrediens("Havregryn", "flingor", 370, 13.0, 20, ("havregryn",), "torrvara"),
    Ingrediens("Broccoli, fryst", "grönsaker", 34, 3.0, 35, ("broccoli",), "fryst"),
    Ingrediens("Vitkål", "grönsaker", 27, 1.3, 18, ("vitkål",)),
    Ingrediens("Morot", "grönsaker", 37, 0.6, 15, ("morötter",)),
    Ingrediens("Gurka", "grönsaker", 12, 0.7, 30, ("gurka",)),
    Ingrediens("Blåbär, frysta", "bär", 57, 0.7, 50, ("blåbär",), "fryst"),
)

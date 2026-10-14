"""Inbyggd startkatalog med ingredienser.

Näringsvärden per 100 g (rå/okokt vara) är ungefärliga och handinmatade,
och priserna är platshållare. Båda ersätts av Livsmedelsverket (#5) och
riktiga butikspriser (#6).
"""

from dataclasses import dataclass

SLOTAR = ("protein", "kolhydrater", "grönsaker")


@dataclass(frozen=True)
class Ingrediens:
    namn: str
    slot: str
    kcal_100g: float
    protein_100g: float
    kr_per_kg: float


STARTKATALOG = (
    Ingrediens("Kycklingfilé", "protein", 106, 23.1, 99),
    Ingrediens("Keso 1,5 %", "protein", 73, 12.3, 55),
    Ingrediens("Kvarg naturell", "protein", 61, 11.0, 45),
    Ingrediens("Ägg", "protein", 140, 12.4, 45),
    Ingrediens("Torskfilé, fryst", "protein", 75, 17.5, 110),
    Ingrediens("Nötfärs 10 %", "protein", 175, 19.0, 110),
    Ingrediens("Potatis", "kolhydrater", 77, 2.0, 15),
    Ingrediens("Ris, okokt", "kolhydrater", 350, 7.0, 30),
    Ingrediens("Fullkornspasta, okokt", "kolhydrater", 350, 13.0, 30),
    Ingrediens("Broccoli, fryst", "grönsaker", 34, 3.0, 35),
    Ingrediens("Vitkål", "grönsaker", 27, 1.3, 18),
    Ingrediens("Morot", "grönsaker", 37, 0.6, 15),
    Ingrediens("Gurka", "grönsaker", 12, 0.7, 30),
)

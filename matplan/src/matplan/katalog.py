"""Inbyggd startkatalog med ingredienser.

Näringsvärden hämtas vid `matplan refresh` från Livsmedelsverket (nummer i
`livsmedelsverket`) eller, för märkesvaror som saknas där, Open Food Facts
(streckkod i `ean`). Värdena i katalogen (per 100 g rå/okokt vara) används
bara tills dess. Priserna är platshållare för ingredienser utan butikspris.

`sokord` är svenska söktermer mot butikerna; en produkt matchar om alla ord
i någon av termerna finns som hela ord i produktens namn och beskrivning.
`butikskategori` är ord som butikens kategori för produkten måste innehålla
(om butiken anger kategori), så att t.ex. kattmat, färdigrätter och inlagd
gurka sorteras bort. `uteslut` är ord som inte får stå i produktnamnet, för
blandprodukter som hamnar i rätt kategori (t.ex. fryst smoothie bland bären).
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
    livsmedelsverket: int | None = None  # nummer i Livsmedelsverkets livsmedelsdatabas
    ean: str | None = None  # streckkod för näringsvärden från Open Food Facts
    uteslut: tuple[str, ...] = ()
    # Proteintyp ("" = härleds ur produkter och namn) och kvalitetsfaktor (sätts av kärnan).
    proteintyp: str = ""
    proteinkvalitet: float = 1.0
    # Enskilda produkt-id som uteslutits ur eller lagts till i gruppen för hand.
    undantag: tuple[str, ...] = ()
    med: tuple[str, ...] = ()


# Butikernas namn skiljer sig: City Gross "Frukt & grönt / Grönsaker", Willys
# "Grönsaker" och "Potatis & rotsaker" (Willys "Potatis" är krokettrar o.d.).
_GRONT = ("frukt & grönt", "grönsaker", "rotfrukter", "potatis & rotsaker")

STARTKATALOG = (
    Ingrediens("Kycklingfilé", "protein", 104, 23.1, 99, ("kycklingfilé", "kyckling filé", "kyckling bröstfilé"), "fryst", ("fågel", "kyckling"), livsmedelsverket=1173),
    Ingrediens("Ägg", "protein", 140, 12.4, 45, ("ägg",), butikskategori=("ägg",), livsmedelsverket=1225),
    Ingrediens("Torskfilé, fryst", "protein", 75, 17.5, 110, ("torskfilé",), "fryst", ("fisk",), livsmedelsverket=1246),
    Ingrediens("Nötfärs 10–12 %", "protein", 175, 19.0, 110, ("nötfärs 10", "nötfärs 12"), "fryst", ("färs", "kött"), livsmedelsverket=951),
    Ingrediens("Keso 1,5 %", "mejeri", 73, 13.0, 55, ("keso naturell 1,5",), butikskategori=("mejeri", "cottage"), ean="7310865051998"),
    Ingrediens("Kvarg naturell", "mejeri", 61, 11.0, 45, ("kvarg naturell",), butikskategori=("mejeri", "kvarg"), livsmedelsverket=3243),
    Ingrediens("Grekisk yoghurt 0 %", "mejeri", 59, 9.5, 40, ("grekisk yoghurt naturell 0",), butikskategori=("yoghurt",), ean="4016241050304"),
    Ingrediens("Potatis", "kolhydrater", 77, 2.0, 15, ("potatis",), butikskategori=_GRONT, livsmedelsverket=230),
    Ingrediens("Ris, okokt", "kolhydrater", 350, 7.0, 30, ("jasminris", "basmatiris", "ris"), "torrvara", ("ris",), livsmedelsverket=2481),
    Ingrediens("Fullkornspasta, okokt", "kolhydrater", 350, 13.0, 30, ("fullkornspasta",), "torrvara", ("pasta",), livsmedelsverket=848),
    Ingrediens("Havregryn", "flingor", 370, 13.0, 20, ("havregryn",), "torrvara", ("flingor", "gryn"), livsmedelsverket=702),
    Ingrediens("Broccoli, fryst", "grönsaker", 34, 3.0, 35, ("broccoli",), "fryst", ("frysta grönsaker", "grönsaker & kryddor"), livsmedelsverket=326),
    Ingrediens("Vitkål", "grönsaker", 27, 1.3, 18, ("vitkål",), butikskategori=_GRONT, livsmedelsverket=370),
    Ingrediens("Morot", "grönsaker", 37, 0.6, 15, ("morötter",), butikskategori=_GRONT, livsmedelsverket=289),
    Ingrediens("Gurka", "grönsaker", 12, 0.7, 30, ("gurka",), butikskategori=_GRONT, livsmedelsverket=339),
    Ingrediens("Blåbär, frysta", "bär", 57, 0.7, 50, ("blåbär",), "fryst", ("frysta bär", "fryst frukt", "frysta frukt", "frukt & bär"), livsmedelsverket=556, uteslut=("smoothie", "bärmix", "mix")),
)

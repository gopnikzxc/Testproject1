"""Slotklassificering ur näringsvärden och butikskategori (#29). Värdena är
City Gross egna (per 100 g/ml) för respektive vara."""

import pytest

from matplan.slot import klassificera

FALL = [
    # namn, kategori, kcal, protein, kolhydrater, fett, slot
    ("Tonfisk Vatten", "Skafferiet / Konserver", 110, 26.0, 0.0, 0.2, "protein"),
    ("Sejfilé", "Fryst / Fryst fisk & skaldjur", 80, 18.0, 0.0, 0.9, "protein"),
    ("Keso Naturell", "Mejeri, ost & ägg / Kvarg & cottage cheese", 93, 13.0, 1.6, 4.0, "mejeri"),
    ("Jasminris", "Skafferiet / Pasta, ris & mos", 350, 6.7, 79.0, 0.7, "kolhydrater"),
    ("Potatis Fast", "Frukt & grönt / Potatis & rotsaker", 77, 2.0, 16.0, 0.1, "kolhydrater"),
    ("Havregryn", "Skafferiet / Flingor, Musli & gryner", 367, 13.0, 58.0, 6.8, "flingor"),
    ("Broccoli Buketter", "Fryst / Frysta grönsaker & kryddor", 39, 4.4, 1.8, 0.9, "grönsaker"),
    ("Morötter", "Frukt & grönt / Potatis & rotsaker", 37, 0.6, 7.0, 0.2, "grönsaker"),
    ("Chicken Nuggets", "Fryst / Fryst kött, fågel, burgare mm", 270, 12.0, 14.0, 18.0, "kombination"),
    ("Fiskpinnar", "Fryst / Fryst fisk & skaldjur", 190, 12.0, 17.0, 8.1, "kombination"),
    ("Svarta Bönor Ekologiska", "Skafferiet / Bönor, ärtor & linser", 103, 7.6, 13.0, 0.8, "kombination"),
    ("Kycklinggryta med ris", "Fryst / Fryst färdigmat", 120, 7.5, 14.0, 3.0, "kombination"),
    ("Mellanmjölk", "Mejeri, ost & ägg / Mjölk & dryck", 47, 3.5, 4.7, 1.5, "mejeri"),
    ("Havredryck Ekologisk", "Mejeri, ost & ägg / Havre- & Sojadryck mm", 39, 1.1, 7.2, 0.5, "mejeri"),
    ("Proteindryck Choklad", "Dryck / Sport & energidryck", 60, 8.0, 4.0, 0.5, "mejeri"),
    ("Apelsinjuice", "Mejeri, ost & ägg / Juice, fruktdrycker & smoothies", 45, 0.7, 9.0, 0.0, "utesluten"),
    ("Apelsinjuice Ekologisk", "Dryck / Juice, fruktdrycker & smoothies", 42, 0.7, 8.8, 0.1, "utesluten"),
    ("Coca-Cola", "Dryck / Läsk", 42, 0.0, 10.6, 0.0, "utesluten"),
    ("Blåbär Odlade", "Fryst / Frysta bär & frukt", 57, 0.7, 12.0, 0.6, "bär"),
    ("Ägg 10P Frigående", "Mejeri, ost & ägg / Ägg", 140, 12.0, 0.0, 9.7, None),
]


@pytest.mark.parametrize("namn, kategori, kcal, protein, kolhydrater, fett, slot", FALL, ids=[f[0] for f in FALL])
def test_klassificering(namn, kategori, kcal, protein, kolhydrater, fett, slot):
    assert klassificera(kcal, protein, kolhydrater, fett, kategori, namn) == slot


def test_drycker_utesluts_aven_utan_naringsvarden():
    assert klassificera(None, None, kategori="Dryck / Läsk", namn="Fanta") == "utesluten"


def test_utan_kolhydratvarde_klassas_bara_protein():
    assert klassificera(110, 26.0, kategori="Skafferiet / Konserver") == "protein"
    assert klassificera(350, 7.0, kategori="Skafferiet / Pasta, ris & mos") is None

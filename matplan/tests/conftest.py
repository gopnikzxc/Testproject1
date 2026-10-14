from matplan.butiker import Produkt, matchar
from matplan.katalog import STARTKATALOG


class FalskButik:
    """Butik i minnet. `fel` kastas vid varje sökning."""

    def __init__(self, namn, produkter, fel=None):
        self.namn = namn
        self._produkter = produkter
        self._fel = fel

    def sok(self, sokord):
        if self._fel:
            raise self._fel
        return [p for p in self._produkter if matchar(p.namn, (sokord,))]


def produkt(butik, pid, namn, kr_per_kg, forpackning_g=1000.0, erbjudande=False):
    pris = kr_per_kg * forpackning_g / 1000 if forpackning_g else kr_per_kg
    return Produkt(butik, pid, namn, "Märke", forpackning_g, pris, kr_per_kg, erbjudande)


def hel_butik(namn, faktor=1.0, undantag=None, forpackning_g=1000.0):
    """En butik med en 1 kg-produkt per katalogingrediens, prissatt som
    platshållarpriset gånger `faktor`. `undantag` ger egna kr/kg per ingrediens
    (None = saknas i butiken)."""
    undantag = undantag or {}
    produkter = []
    for i in STARTKATALOG:
        kr = undantag.get(i.namn, i.kr_per_kg * faktor)
        if kr is None:
            continue
        produkter.append(produkt(namn, f"{namn[:3]}-{i.namn}", f"{i.sokord[0].capitalize()} {namn}", kr, forpackning_g))
    return FalskButik(namn, produkter)

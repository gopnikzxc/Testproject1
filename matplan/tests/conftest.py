import pytest

from matplan.butiker import Produkt, matchar
from matplan.katalog import STARTKATALOG


class FalskButik:
    """Butik i minnet. `fel` kastas vid varje sökning."""

    def __init__(self, namn, produkter, fel=None):
        self.namn = namn
        self._produkter = produkter
        self._fel = fel

    def sok(self, sokord, butikskategori=()):
        if self._fel:
            raise self._fel
        return [p for p in self._produkter if matchar(p.namn, (sokord,))]


def produkt(butik, pid, namn, kr_per_kg, forpackning_g=1000.0, erbjudande=False):
    pris = kr_per_kg * forpackning_g / 1000 if forpackning_g else kr_per_kg
    return Produkt(butik, pid, namn, "Märke", forpackning_g, pris, kr_per_kg, erbjudande)


def hel_butik(namn, faktor=1.0, undantag=None, forpackning_g=1000.0, katalog=STARTKATALOG, erbjudande=()):
    """En butik med en 1 kg-produkt per katalogingrediens, prissatt som
    platshållarpriset gånger `faktor`. `undantag` ger egna kr/kg per ingrediens
    (None = saknas i butiken). `erbjudande` är ingredienser vars produkt har
    butikens erbjudandeflagga."""
    undantag = undantag or {}
    produkter = []
    for i in katalog:
        kr = undantag.get(i.namn, i.kr_per_kg * faktor)
        if kr is None:
            continue
        produkter.append(
            produkt(namn, f"{namn[:3]}-{i.namn}", f"{i.sokord[0].capitalize()} {namn}", kr, forpackning_g, i.namn in erbjudande)
        )
    return FalskButik(namn, produkter)


@pytest.fixture(autouse=True)
def inga_riktiga_butiker(monkeypatch):
    """CLI-tester får aldrig anropa riktiga butiker; tester som vill ha butiker sätter egna."""
    import matplan.cli

    monkeypatch.setattr(matplan.cli, "_butiker", lambda: ())
    monkeypatch.setattr(matplan.cli, "_naringskallor", lambda: (None, None))


def katalogvara(pid, namn, marke="GARANT", besk="", kr=50.0, kcal=100.0, protein=20.0,
                kategori="Skafferiet / Konserver", butik="City Gross Ytterby", forpackning_g=400.0, erbjudande=False):
    """En produkt i butikens synkade sortiment."""
    return Produkt(butik, pid, namn, marke, forpackning_g, kr * forpackning_g / 1000 if forpackning_g else kr, kr,
                   erbjudande, kategori, besk, "", kcal, protein)


class SortimentButik:
    """Butik som listar hela sortimentet (som City Gross). Sökning per term får inte användas."""

    nyckel = "citygross"

    def __init__(self, produkter=None, fel=None, namn="City Gross Ytterby"):
        self.namn = namn
        self.produkter = produkter or []
        self.fel = fel

    def sortiment(self, framsteg=None):
        if self.fel:
            raise self.fel
        return list(self.produkter)

    def sok(self, sokord, butikskategori=()):
        raise AssertionError("butiker med synkat sortiment ska inte sökas per term")

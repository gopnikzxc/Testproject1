from datetime import date, datetime

import pytest

from matplan.butiker import ButiksFel, Produkt, matchar
from matplan.cli import main
from matplan.core import Matplan

START = date(2026, 10, 15)
NU = datetime(2026, 10, 14, 9, 30)


class FalskButik:
    def __init__(self, namn, produkter, fel=None):
        self.namn = namn
        self._produkter = produkter
        self._fel = fel
        self.sokningar = []

    def sok(self, sokord):
        self.sokningar.append(sokord)
        if self._fel:
            raise self._fel
        return [p for p in self._produkter if matchar(p.namn, (sokord,))]


def _p(butik, pid, namn, kr_per_kg, erbjudande=False):
    return Produkt(butik, pid, namn, "Märke", 1000, kr_per_kg, kr_per_kg, erbjudande)


def _city(*extra, fel=None):
    return FalskButik(
        "City Gross Ytterby",
        [
            _p("City Gross Ytterby", "cg-1", "Kycklingfilé Fryst 1kg", 89.0),
            _p("City Gross Ytterby", "cg-2", "Kycklingfilé Färsk 900g", 129.0),
            _p("City Gross Ytterby", "cg-3", "Kycklingkorv 800g", 49.0),
            _p("City Gross Ytterby", "cg-4", "Potatis Fast 2kg", 12.5),
            *extra,
        ],
        fel=fel,
    )


def _ica(fel=None):
    return FalskButik("ICA Maxi Kungälv", [_p("ICA Maxi Kungälv", "ica-1", "Kycklingfilé 1,5kg", 79.0)], fel=fel)


def _kyckling_kr_per_kg(plan):
    for block in plan.block:
        for rad in block.batch.portion("jag").rader:
            if rad.namn == "Kycklingfilé":
                return rad.kr / rad.gram * 1000
    return None


def test_utan_hamtning_anvands_platshallarpriser(tmp_path):
    plan = Matplan(tmp_path / "m.db").plan(START)

    assert plan.priser_hamtade is None
    assert plan.utan_butikspris == ()


def test_refresh_sparar_priser_och_planen_anvander_billigaste_kr_per_kg(tmp_path):
    app = Matplan(tmp_path / "m.db", butiker=(_city(), _ica()))

    resultat = app.refresh(nu=NU)
    plan = app.plan(START)

    assert resultat.fel == {}
    assert resultat.antal_produkter == {"City Gross Ytterby": 3, "ICA Maxi Kungälv": 1}
    assert plan.priser_hamtade == NU
    assert _kyckling_kr_per_kg(plan) == pytest.approx(79.0)
    assert "Kycklingfilé" not in plan.utan_butikspris
    assert "Potatis" not in plan.utan_butikspris
    assert "Vitkål" in plan.utan_butikspris


def test_produkter_som_inte_matchar_hela_ord_ignoreras(tmp_path):
    app = Matplan(tmp_path / "m.db", butiker=(_city(),))

    app.refresh(nu=NU)

    # Kycklingkorv (49 kr/kg) får inte bli kycklingfiléns pris.
    assert _kyckling_kr_per_kg(app.plan(START)) == pytest.approx(89.0)


@pytest.mark.parametrize("fel", [ButiksFel("Sidan har ändrats"), KeyError("products")])
def test_trasig_butik_stoppar_inte_ovriga(tmp_path, fel):
    app = Matplan(tmp_path / "m.db", butiker=(_city(fel=fel), _ica()))

    resultat = app.refresh(nu=NU)

    assert "City Gross Ytterby" in resultat.fel
    assert resultat.antal_produkter == {"ICA Maxi Kungälv": 1}
    assert _kyckling_kr_per_kg(app.plan(START)) == pytest.approx(79.0)


def test_varje_hamtning_sparas_i_historiken_och_senaste_galler(tmp_path):
    db = tmp_path / "m.db"
    Matplan(db, butiker=(_city(),)).refresh(nu=NU)
    billigare = _p("City Gross Ytterby", "cg-1", "Kycklingfilé Fryst 1kg", 69.0)
    app = Matplan(db, butiker=(FalskButik("City Gross Ytterby", [billigare]),))

    app.refresh(nu=datetime(2026, 10, 21, 9, 0))

    assert app._lagring.antal_hamtningar() == 2
    assert _kyckling_kr_per_kg(app.plan(START)) == pytest.approx(69.0)


def test_butik_som_fallerar_behaller_sina_senaste_priser(tmp_path):
    db = tmp_path / "m.db"
    Matplan(db, butiker=(_city(), _ica())).refresh(nu=NU)
    app = Matplan(db, butiker=(_city(), _ica(fel=ButiksFel("nere"))))

    app.refresh(nu=datetime(2026, 10, 21, 9, 0))
    plan = app.plan(START)

    assert _kyckling_kr_per_kg(plan) == pytest.approx(79.0)
    assert plan.priser_hamtade == NU  # äldsta av de priser som används


def test_ingen_butik_sparar_ingen_hamtning(tmp_path):
    app = Matplan(tmp_path / "m.db")

    resultat = app.refresh(nu=NU)

    assert resultat.antal_produkter == {} and resultat.fel == {}
    assert app._lagring.antal_hamtningar() == 0


def test_matchning_kraver_hela_ord():
    assert matchar("Kycklingfilé Fryst 1kg", ("kycklingfilé",))
    assert matchar("Ris Jasmin 1kg", ("jasminris", "ris"))
    assert not matchar("Risifrutti Original", ("ris",))
    assert not matchar("Äggnudlar 250g", ("ägg",))


def test_cli_plan_visar_platshallarpriser(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MATPLAN_DB", str(tmp_path / "cli.db"))

    assert main(["plan"]) == 0

    assert "Platshållarpriser" in capsys.readouterr().out


def test_cli_refresh_utan_butiker(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MATPLAN_DB", str(tmp_path / "cli.db"))

    assert main(["refresh"]) == 0

    assert "Inga butiker" in capsys.readouterr().out

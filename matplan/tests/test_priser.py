from datetime import date, datetime

import pytest

from conftest import FalskButik

from matplan.butiker import ButiksFel, Produkt, matchar
from matplan.cli import main
from matplan.core import Matplan

START = date(2026, 10, 15)
NU = datetime(2026, 10, 14, 9, 30)


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


def _coop(fel=None):
    return FalskButik("Coop Kungälv", [_p("Coop Kungälv", "coop-1", "Kycklingfilé 1,5kg", 79.0)], fel=fel)


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
    app = Matplan(tmp_path / "m.db", butiker=(_city(), _coop()))

    resultat = app.refresh(nu=NU)
    plan = app.plan(START)

    assert resultat.fel == {}
    assert resultat.antal_produkter == {"City Gross Ytterby": 3, "Coop Kungälv": 1}
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
    app = Matplan(tmp_path / "m.db", butiker=(_city(fel=fel), _coop()))

    resultat = app.refresh(nu=NU)

    assert "City Gross Ytterby" in resultat.fel
    assert resultat.antal_produkter == {"Coop Kungälv": 1}
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
    Matplan(db, butiker=(_city(), _coop())).refresh(nu=NU)
    app = Matplan(db, butiker=(_city(), _coop(fel=ButiksFel("nere"))))

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


def test_butikskategori_sorterar_bort_fel_sorts_produkter(tmp_path):
    butik = FalskButik(
        "City Gross Ytterby",
        [
            Produkt("City Gross Ytterby", "katt", "Nötfärs 10% i Gelé", "", 400, 20.0, 50.0, kategori="Husdjur / Katt"),
            Produkt("City Gross Ytterby", "farser", "Nötfärs 10%", "", 1000, 110.0, 110.0, kategori="Kött & fågel / Färser"),
            Produkt("City Gross Ytterby", "yoghurt", "Blåbär Yoghurt", "", 1000, 20.0, 20.0, kategori="Mejeri, ost & ägg / Yoghurt"),
            Produkt("City Gross Ytterby", "frysta", "Blåbär Vilda", "", 2500, 189.0, 75.6, kategori="Fryst / Frysta bär & frukt"),
        ],
    )
    app = Matplan(tmp_path / "m.db", butiker=(butik,))

    app.refresh(nu=NU)

    assert [p.produkt_id for p in app.produkter("Nötfärs 10–12 %")] == ["farser"]
    assert [p.produkt_id for p in app.produkter("Blåbär, frysta")] == ["frysta"]


def test_ratt_kategori():
    from matplan.butiker import ratt_kategori

    assert ratt_kategori("Fryst / Frysta grönsaker & kryddor", ("frysta grönsaker",))
    assert not ratt_kategori("Frukt & grönt / Grönsaker", ("frysta grönsaker",))
    assert ratt_kategori("", ("frysta grönsaker",))  # butiken anger ingen kategori
    assert ratt_kategori("Vad som helst", ())


def test_refresh_rapporterar_framsteg(tmp_path):
    steg = []
    app = Matplan(tmp_path / "m.db", butiker=(_city(),))

    app.refresh(nu=NU, framsteg=lambda butik, namn: steg.append((butik, namn)))

    assert ("City Gross Ytterby", "Kycklingfilé") in steg


def test_matchning_med_beskrivning():
    assert matchar("Keso Mini Naturell", ("keso naturell 1,5",), "500G 1,5% KESO")
    assert not matchar("Keso Naturell", ("keso naturell 1,5",), "500G 4% KESO")
    assert matchar("Naturell Grekisk Yoghurt", ("grekisk yoghurt naturell 0",), "1KG 0% ARLA")
    assert not matchar("Grekisk Yoghurt Naturell", ("grekisk yoghurt naturell 0",), "1KG 10% ARLA")
    # Första ordet måste stå i namnet, inte bara i beskrivningen.
    assert not matchar("Smoothie Jordgubb Banan", ("blåbär",), "750G JORDGUBB BANAN BLÅBÄR")


def test_uteslutna_ord_sorterar_bort_blandprodukter(tmp_path):
    butik = FalskButik(
        "Coop Kungälv",
        [
            Produkt("Coop Kungälv", "smoothie", "Smoothie Jordgubb Banan Blåbär Fryst", "", 500, 27.9, 55.8, kategori="Frukt & Bär"),
            Produkt("Coop Kungälv", "blabar", "Blåbär Odlade Fryst", "", 500, 34.9, 69.8, kategori="Frukt & Bär"),
        ],
    )
    app = Matplan(tmp_path / "m.db", butiker=(butik,))

    app.refresh(nu=NU)

    assert [p.produkt_id for p in app.produkter("Blåbär, frysta")] == ["blabar"]

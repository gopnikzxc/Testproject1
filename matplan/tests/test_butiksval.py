"""Välja vilka butiker som hämtas och planeras mot."""

from datetime import date, datetime

from conftest import hel_butik

from matplan.core import Matplan

START = date(2026, 10, 15)
NU = datetime(2026, 10, 14, 9, 0)


def _butiker():
    city = hel_butik("City Gross Ytterby")
    willys = hel_butik("Willys Kungälv", faktor=0.5)  # billigare, så den skulle vinna om den räknades
    city.nyckel, willys.nyckel = "citygross", "willys"
    return city, willys


def test_bara_city_gross_som_standard(tmp_path):
    app = Matplan(tmp_path / "m.db", butiker=_butiker())

    resultat = app.refresh(nu=NU)

    assert set(resultat.antal_produkter) == {"City Gross Ytterby"}
    assert {t.butik for t in app.inkopslista(START).butiker} == {"City Gross Ytterby"}
    assert {p.butik for p in app.produkter("Kycklingfilé")} == {"City Gross Ytterby"}


def test_avstangd_butiks_sparade_priser_ignoreras(tmp_path):
    db = tmp_path / "m.db"
    app = Matplan(db, butiker=_butiker())
    app.satt_installning("butik_willys", 1)
    app.refresh(nu=NU)
    assert app.inkopslista(START).basta_butik.butik == "Willys Kungälv"

    app.satt_installning("butik_willys", 0)

    lista = app.inkopslista(START)
    assert {t.butik for t in lista.butiker} == {"City Gross Ytterby"}
    assert all(set(r.alternativ) <= {"City Gross Ytterby"} for r in lista.rader)


def test_butik_kan_slas_pa_igen(tmp_path):
    app = Matplan(tmp_path / "m.db", butiker=_butiker())
    app.satt_installning("butik_willys", 1)

    resultat = app.refresh(nu=NU)

    assert set(resultat.antal_produkter) == {"City Gross Ytterby", "Willys Kungälv"}


def test_avstangd_butik_ignoreras_aven_utan_adaptrar(tmp_path):
    db = tmp_path / "m.db"
    app = Matplan(db, butiker=_butiker())
    app.satt_installning("butik_willys", 1)
    app.refresh(nu=NU)
    app.satt_installning("butik_willys", 0)

    utan_adaptrar = Matplan(db)

    assert {t.butik for t in utan_adaptrar.inkopslista(START).butiker} == {"City Gross Ytterby"}
